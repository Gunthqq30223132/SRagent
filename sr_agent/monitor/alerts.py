"""Máy trạng thái alert — thiết kế chống "mệt mỏi vì báo động" (alarm fatigue).

Nguyên tắc: notify khi CHUYỂN TRẠNG THÁI, không phải khi thấy sự kiện.
- OK -> OPEN     : 1 tin "🔴 sự cố"
- OPEN (đang mở) : im lặng; re-notify chỉ sau REALERT_HOURS nếu vẫn chưa xử lý
- OPEN -> RESOLVED: 1 tin "🟢 đã hồi phục" — người vận hành biết KHÔNG cần làm gì

Sink nhẹ, local-first:
- macOS: `osascript display notification` (zero-dependency)
- Tùy chọn ALERT_WEBHOOK_URL (.env): tương thích ntfy.sh (push điện thoại,
  không cần server) / Slack / Discord — tự nhận dạng theo host.
Sink lỗi không bao giờ được làm sập heal/pipeline: nuốt lỗi + in stderr.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import httpx

from sr_agent.monitor.health import NO_BATCH_ALERT_HOURS, HealthSnapshot, snapshot
from sr_agent.store.staging import StagingStore

REALERT_HOURS = 24
DLQ_SPIKE_MIN_ENTRIES = 5
DLQ_SPIKE_BATCH_RATIO = 0.3


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- sinks ------------------------------------------------------------------------

def notify(title: str, message: str) -> None:
    sent = False
    if sys.platform == "darwin" and shutil.which("osascript"):
        try:
            subprocess.run(
                ["osascript", "-e",
                 f'display notification "{message}" with title "SR-Agent: {title}"'],
                check=False, capture_output=True, timeout=5,
            )
            sent = True
        except Exception as exc:  # sink không bao giờ được làm sập caller
            print(f"[alert] osascript lỗi: {exc}", file=sys.stderr)
    url = os.getenv("ALERT_WEBHOOK_URL", "")
    if url:
        try:
            if "slack.com" in url:
                httpx.post(url, json={"text": f"[SR-Agent] {title}: {message}"}, timeout=5)
            elif "discord.com" in url:
                httpx.post(url, json={"content": f"[SR-Agent] {title}: {message}"}, timeout=5)
            else:  # ntfy-style: body text + header Title (header phải ASCII — bỏ emoji)
                ascii_title = f"SR-Agent: {title}".encode("ascii", "ignore").decode().strip()
                httpx.post(url, content=message.encode(),
                           headers={"Title": ascii_title}, timeout=5)
            sent = True
        except httpx.HTTPError as exc:
            print(f"[alert] webhook lỗi: {exc}", file=sys.stderr)
    if not sent:
        print(f"[alert] {title}: {message}", file=sys.stderr)


# --- rules ------------------------------------------------------------------------

def desired_alerts(snap: HealthSnapshot, *, ollama_up: bool | None) -> dict[str, str]:
    """{alert_key: detail} các alert PHẢI đang mở theo trạng thái hiện tại.

    Key vắng mặt = alert đó phải đóng (resolve). ollama_up=None nghĩa là
    caller không probe (không đủ dữ kiện) -> giữ nguyên trạng thái rule Ollama.
    """
    desired: dict[str, str] = {}
    for src in snap.sources_down:
        desired[f"SOURCE_DOWN:{src}"] = (
            f"Nguồn {src} sập: batch bị skip / circuit breaker trong 24h qua. "
            f"heal sẽ tự retry khi mạng thông."
        )
    ratio_spike = False
    if snap.last_run is not None:
        import json

        report = json.loads(snap.last_run["report_json"])
        fetched = report.get("fetched", 0)
        if fetched > 0 and report.get("dlq", 0) / fetched > DLQ_SPIKE_BATCH_RATIO:
            ratio_spike = True
    if snap.dlq_retry_eligible >= DLQ_SPIKE_MIN_ENTRIES or ratio_spike:
        desired["DLQ_SPIKE"] = (
            f"DLQ tăng đột biến: {snap.dlq_retry_eligible} entry chờ retry "
            f"({snap.dlq_by_error})."
        )
    if ollama_up is False and snap.degraded_count > 0:
        desired["OLLAMA_DEGRADED"] = (
            f"Ollama không phản hồi — {snap.degraded_count} tài liệu QUEUED "
            f"chưa qua phân tích LLM (enrich sẽ tự chạy khi Ollama sống lại)."
        )
    if (
        snap.hours_since_last_run is not None
        and snap.hours_since_last_run > NO_BATCH_ALERT_HOURS
    ):
        desired["NO_BATCH_36H"] = (
            f"Không có batch nào chạy suốt {snap.hours_since_last_run:.0f}h "
            f"— kiểm tra launchd agent com.sragent.daily."
        )
    if snap.dlq_permanent > 0:
        desired["DLQ_PERMANENT"] = (
            f"{snap.dlq_permanent} bản ghi chạm trần retry (5 lần) — cần xem tay: "
            f"python -m sr_agent.pipeline status."
        )
    return desired


# --- state machine ------------------------------------------------------------------

def evaluate(
    store: StagingStore,
    *,
    ollama_up: bool | None = None,
    notifier=notify,
) -> list[tuple[str, str]]:
    """Đối chiếu trạng thái mong muốn với bảng alerts, notify đúng các CHUYỂN tiếp.

    Trả về danh sách (key, transition) đã notify — phục vụ test/log.
    ollama_up=None: chỉ probe khi thật sự cần (có doc degraded) để evaluate rẻ.
    """
    snap = snapshot(store)
    if ollama_up is None and snap.degraded_count > 0:
        from sr_agent.monitor.probes import probe_ollama

        ollama_up = probe_ollama()

    desired = desired_alerts(snap, ollama_up=ollama_up)
    fired: list[tuple[str, str]] = []
    now = _now()
    existing = {
        r["key"]: r for r in store.conn.execute("SELECT * FROM alerts")
    }

    for key, detail in desired.items():
        row = existing.get(key)
        if row is None or row["state"] == "RESOLVED":
            store.conn.execute(
                "INSERT INTO alerts (key, state, detail, first_seen, last_notified) "
                "VALUES (?, 'OPEN', ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET state='OPEN', detail=excluded.detail, "
                "first_seen=excluded.first_seen, last_notified=excluded.last_notified",
                (key, detail, now, now),
            )
            notifier(f"🔴 {key}", detail)
            fired.append((key, "OPEN"))
        else:  # đang OPEN: im lặng, trừ khi quá cooldown
            last = row["last_notified"]
            stale_h = (
                (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds()
                / 3600 if last else REALERT_HOURS + 1
            )
            if stale_h >= REALERT_HOURS:
                store.conn.execute(
                    "UPDATE alerts SET last_notified = ?, detail = ? WHERE key = ?",
                    (now, detail, key),
                )
                notifier(f"🔴 {key} (vẫn chưa xử lý)", detail)
                fired.append((key, "REALERT"))

    for key, row in existing.items():
        if row["state"] == "OPEN" and key not in desired:
            store.conn.execute(
                "UPDATE alerts SET state='RESOLVED', last_notified=? WHERE key=?",
                (now, key),
            )
            notifier(f"🟢 {key}", "Đã hồi phục — không cần thao tác gì thêm.")
            fired.append((key, "RESOLVED"))

    store.conn.commit()
    return fired


def open_alerts(store: StagingStore) -> list[dict]:
    return [
        dict(r) for r in store.conn.execute(
            "SELECT * FROM alerts WHERE state = 'OPEN' ORDER BY first_seen"
        )
    ]
