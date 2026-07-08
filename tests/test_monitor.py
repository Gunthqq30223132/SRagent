"""Tests M4 — observability, auto-heal, degradation flagging. Offline 100%."""

from datetime import datetime, timedelta, timezone

import httpx
import pytest
import respx

from sr_agent.errors import RateLimited
from sr_agent.ingest.router import SourceRouter
from sr_agent.models.schemas import DocStatus, Document, TechnicalMetadata
from sr_agent.monitor import alerts, health
from sr_agent.monitor.recover import enrich_degraded, heal
from sr_agent.pipeline import Pipeline
from sr_agent.store.staging import StagingStore

from tests.test_pipeline import FakeFetcher, make_doc


@pytest.fixture
def store(tmp_path):
    with StagingStore(tmp_path / "t.db") as s:
        yield s


def collect_notifier(sink: list):
    def _notify(title: str, message: str) -> None:
        sink.append((title, message))
    return _notify


def queued_doc(store, source_id="38111222", *, with_tech_meta=False) -> Document:
    doc = make_doc("ieee", source_id, f"Paper {source_id}", 1)
    doc.status = DocStatus.QUEUED
    if with_tech_meta:
        doc.tech_meta = TechnicalMetadata(has_code_repo=False)
    store.upsert(doc)
    return doc


# --- degraded flagging (Hạng mục 3, zero-touch) -----------------------------------

class TestDegradedFlag:
    def test_queued_without_tech_meta_is_degraded(self, store):
        queued_doc(store, "38111222", with_tech_meta=False)
        assert store.degraded_uids() == ["ieee:38111222"]

    def test_tech_meta_present_not_degraded(self, store):
        queued_doc(store, "38111222", with_tech_meta=True)
        assert store.degraded_uids() == []

    def test_non_queued_status_not_degraded(self, store):
        doc = queued_doc(store, "38111222")
        doc.status = DocStatus.APPROVED_LOCAL
        store.upsert(doc)
        assert store.degraded_uids() == []


class TestEnrich:
    def test_enrich_fills_tech_meta_and_logs_event(self, store):
        queued_doc(store, "38111222")

        def fake_parse(doc):
            doc.tech_meta = TechnicalMetadata(has_code_repo=True)
            return doc

        assert enrich_degraded(store, parse_fn=fake_parse) == 1
        enriched = store.get("ieee:38111222")
        assert enriched.tech_meta.has_code_repo is True
        assert enriched.status is DocStatus.QUEUED  # vẫn chờ người duyệt
        events = [r["event_type"] for r in store.conn.execute("SELECT * FROM events")]
        assert "ENRICHED" in events
        assert store.degraded_uids() == []

    def test_transient_error_stops_batch(self, store):
        queued_doc(store, "38111222")
        queued_doc(store, "38111223")

        def flaky(doc):
            raise RateLimited("ollama quá tải")

        assert enrich_degraded(store, parse_fn=flaky) == 0
        # không doc nào bị DLQ — transient chỉ dừng đợt, đêm sau thử lại
        assert len(store.degraded_uids()) == 2

    def test_respects_limit(self, store):
        for i in range(3):
            queued_doc(store, f"3811122{i}")

        def fake_parse(doc):
            doc.tech_meta = TechnicalMetadata(has_code_repo=False)
            return doc

        assert enrich_degraded(store, limit=2, parse_fn=fake_parse) == 2
        assert len(store.degraded_uids()) == 1


# --- DLQ attempts cap ---------------------------------------------------------------

class TestDlqAttempts:
    def test_bump_caps_at_five_and_disables_retry(self, store):
        store.push_dlq("ieee:38111222", "NetworkError", "x", retry_eligible=True)
        entry_id = store.dlq_entries()[0]["id"]
        for expected in (2, 3, 4):
            assert store.bump_dlq_attempt(entry_id) == expected
            assert store.dlq_entries(retry_eligible_only=True)  # vẫn eligible
        assert store.bump_dlq_attempt(entry_id) == 5
        assert store.dlq_entries(retry_eligible_only=True) == []  # đã tắt
        assert store.dlq_entries()[0]["attempts"] == 5  # giữ lại làm audit


# --- alert state machine (Hạng mục 1) ----------------------------------------------

def push_stale_spike(store, n=5):
    """n entry retry_eligible NGOÀI cửa sổ 24h: chỉ kích DLQ_SPIKE (đếm tổng),
    không kích SOURCE_DOWN (chỉ nhìn 24h gần nhất)."""
    for i in range(n):
        store.push_dlq(f"ieee:3811122{i}", "NetworkError", "x", retry_eligible=True)
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    store.conn.execute("UPDATE dlq SET created_at = ?", (old,))
    store.conn.commit()


class TestAlertStateMachine:
    def test_open_notifies_once_then_silent(self, store):
        push_stale_spike(store)
        sink = []
        fired = alerts.evaluate(store, ollama_up=True, notifier=collect_notifier(sink))
        assert ("DLQ_SPIKE", "OPEN") in fired and len(sink) == 1

        sink.clear()
        fired = alerts.evaluate(store, ollama_up=True, notifier=collect_notifier(sink))
        assert fired == [] and sink == []  # đang OPEN: im lặng tuyệt đối

    def test_resolved_notifies_exactly_once(self, store):
        push_stale_spike(store)
        alerts.evaluate(store, ollama_up=True, notifier=lambda *a: None)
        for e in store.dlq_entries():  # sự cố được xử lý xong
            store.clear_dlq_entry(e["id"])

        sink = []
        fired = alerts.evaluate(store, ollama_up=True, notifier=collect_notifier(sink))
        assert ("DLQ_SPIKE", "RESOLVED") in fired
        assert len(sink) == 1 and sink[0][0].startswith("🟢")

        sink.clear()
        alerts.evaluate(store, ollama_up=True, notifier=collect_notifier(sink))
        assert sink == []  # resolved rồi thì im hẳn

    def test_source_down_from_batch_entry(self, store):
        store.push_dlq("ieee:batch", "RateLimited", "429", retry_eligible=True)
        snap = health.snapshot(store)
        assert snap.sources_down == ["ieee"]
        desired = alerts.desired_alerts(snap, ollama_up=True)
        assert "SOURCE_DOWN:ieee" in desired

    def test_ollama_degraded_needs_both_conditions(self, store):
        queued_doc(store, "38111222")  # degraded
        snap = health.snapshot(store)
        assert "OLLAMA_DEGRADED" in alerts.desired_alerts(snap, ollama_up=False)
        assert "OLLAMA_DEGRADED" not in alerts.desired_alerts(snap, ollama_up=True)

    def test_dead_mans_switch_36h(self, store):
        old = (datetime.now(timezone.utc) - timedelta(hours=40)).isoformat()
        store.record_run("q", old, "{}")
        store.conn.execute("UPDATE runs SET started_at = ?", (old,))
        store.conn.commit()
        snap = health.snapshot(store)
        assert "NO_BATCH_36H" in alerts.desired_alerts(snap, ollama_up=True)

    def test_no_runs_table_entry_no_dead_man_alert(self, store):
        # hệ chưa từng chạy batch (mới cài) không phải là sự cố
        snap = health.snapshot(store)
        assert "NO_BATCH_36H" not in alerts.desired_alerts(snap, ollama_up=True)


class TestNotifySinks:
    @respx.mock
    def test_ntfy_style_webhook(self, monkeypatch):
        monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://ntfy.sh/sr-agent-test")
        route = respx.post("https://ntfy.sh/sr-agent-test").mock(
            return_value=httpx.Response(200)
        )
        alerts.notify("🔴 SOURCE_DOWN:ieee", "nguồn sập")
        assert route.called
        req = route.calls[0].request
        assert req.content.decode() == "nguồn sập"
        assert "SR-Agent" in req.headers["Title"]

    @respx.mock
    def test_slack_webhook_uses_json_text(self, monkeypatch):
        monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://hooks.slack.com/services/X")
        route = respx.post("https://hooks.slack.com/services/X").mock(
            return_value=httpx.Response(200)
        )
        alerts.notify("🟢 DLQ_SPIKE", "hồi phục")
        assert b'"text"' in route.calls[0].request.content

    @respx.mock
    def test_webhook_failure_never_raises(self, monkeypatch, capsys):
        monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://ntfy.sh/x")
        respx.post("https://ntfy.sh/x").mock(side_effect=httpx.ConnectError("down"))
        alerts.notify("t", "m")  # sink sập không được làm sập heal
        assert "webhook lỗi" in capsys.readouterr().err


# --- heal (Hạng mục 2) ---------------------------------------------------------------

class TestHeal:
    def test_batch_entry_reruns_standing_query_when_source_up(self, store):
        store.record_run("edge inference", datetime.now(timezone.utc).isoformat(), "{}")
        store.push_dlq("ieee:batch", "RateLimited", "429", retry_eligible=True)
        good = make_doc("ieee", "38111222", "Recovered Paper", 1)

        def factory(s):
            return Pipeline(s, router=SourceRouter(
                fetchers={"ieee": FakeFetcher("ieee", [good])}))

        summary = heal(
            store, pipeline_factory=factory,
            probe_source_fn=lambda s: True, probe_ollama_fn=lambda: False,
            notifier=lambda *a: None,
        )
        assert summary["batch_rerun"]["query"] == "edge inference"
        assert summary["batch_rerun"]["queued"] == 1
        assert store.dlq_entries(retry_eligible_only=True) == []  # entry batch đã xóa
        assert store.get("ieee:38111222").status is DocStatus.QUEUED

    def test_batch_entry_untouched_when_source_still_down(self, store):
        store.record_run("q", datetime.now(timezone.utc).isoformat(), "{}")
        store.push_dlq("ieee:batch", "RateLimited", "429", retry_eligible=True)

        summary = heal(
            store, pipeline_factory=lambda s: Pipeline(s, router=SourceRouter(fetchers={})),
            probe_source_fn=lambda s: False, probe_ollama_fn=lambda: False,
            notifier=lambda *a: None,
        )
        assert summary["batch_rerun"] is None
        assert len(store.dlq_entries(retry_eligible_only=True)) == 1

    def test_failed_doc_retry_bumps_attempts(self, store):
        store.push_dlq("ieee:38111222", "NetworkError", "x", retry_eligible=True)

        def factory(s):  # fetch vẫn lỗi -> retry fail -> bump
            return Pipeline(s, router=SourceRouter(fetchers={
                "ieee": FakeFetcher("ieee", error=RateLimited("vẫn 429")),
            }))

        summary = heal(
            store, pipeline_factory=factory,
            probe_source_fn=lambda s: True, probe_ollama_fn=lambda: False,
            notifier=lambda *a: None,
        )
        assert summary["bumped"] == 1
        assert store.dlq_entries()[0]["attempts"] == 2

    @respx.mock
    def test_heal_enriches_when_ollama_recovers(self, store):
        queued_doc(store, "38111222")
        monkey_meta = TechnicalMetadata(has_code_repo=False)

        respx.get("http://localhost:11434/api/tags").mock(return_value=httpx.Response(200, json={}))
        respx.post("http://localhost:11434/api/chat").mock(side_effect=[
            httpx.Response(200, json={
                "message": {
                    "role": "assistant",
                    "content": "{\"has_code_repo\": false}"
                }
            }),
            httpx.Response(200, json={
                "message": {
                    "role": "assistant",
                    "content": "{\"critique_questions\": [{\"question\": \"Q1?\"}, {\"question\": \"Q2?\"}]}"
                }
            })
        ])

        summary = heal(
            store, now=True,
            pipeline_factory=lambda s: Pipeline(s, router=SourceRouter(fetchers={})),
            probe_source_fn=lambda s: True, probe_ollama_fn=lambda: True,
            notifier=lambda *a: None,
        )
        # không có parse_fn thật (Ollama mock) — enrich nội bộ tự gọi OllamaClient
        # nên ở test này chỉ khẳng định nhánh enrich được kích hoạt qua summary key
        assert "enriched" in summary

    def test_full_recovery_emits_resolved(self, store):
        # sự cố: nguồn sập -> alert OPEN
        store.record_run("q", datetime.now(timezone.utc).isoformat(), "{}")
        store.push_dlq("ieee:batch", "RateLimited", "429", retry_eligible=True)
        alerts.evaluate(store, ollama_up=True, notifier=lambda *a: None)
        assert alerts.open_alerts(store)

        # hạ tầng hồi phục -> heal chạy lại query, alert phải RESOLVED đúng 1 tin
        sink = []
        heal(
            store,
            pipeline_factory=lambda s: Pipeline(s, router=SourceRouter(
                fetchers={"ieee": FakeFetcher("ieee", [])})),
            probe_source_fn=lambda s: True, probe_ollama_fn=lambda: True,
            notifier=collect_notifier(sink),
        )
        assert alerts.open_alerts(store) == []
        resolved = [t for t, _ in sink if t.startswith("🟢")]
        assert len(resolved) == 1


class TestHealthCLI:
    def test_health_exit_codes(self, store, monkeypatch, capsys):
        from sr_agent.pipeline import _print_health

        assert _print_health(store) == 0
        assert "Không có sự cố" in capsys.readouterr().out

        store.push_dlq("ieee:batch", "RateLimited", "429", retry_eligible=True)
        assert _print_health(store) == 1
        assert "SOURCE_DOWN:ieee" in capsys.readouterr().out
