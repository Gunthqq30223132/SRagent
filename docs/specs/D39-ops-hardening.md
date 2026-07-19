# D39 — Ops Hardening: digest pinning · outbound-Notion · backup · single-writer

**Trạng thái:** thiết kế đóng băng 2026-07-19 (PM Fable 5). Bốn gói nhỏ độc
lập, mỗi gói tự trọn vẹn — có thể giao Antigravity thành 1 mandate chung
(D39.1–D39.4) hoặc lẻ từng gói. Đóng các nợ premortem **B3, B2, B10, B6**.

## D39.1 — Model digest pinning + giao thức tái hiệu chuẩn (B3)

**Vấn đề:** tag Ollama mutable. Một `ollama pull` đổi weights ⇒ κ=0.9042
(M7.2) thành số vô nghĩa, không ai biết vì test offline vẫn xanh (mock).
FL-1 đã ghi digest lần đầu — D39.1 biến nó thành cơ chế.

**Thiết kế:**
- File lock mới `tools/profiles/models.lock.json` (PM-owned, đổi qua PR):
  ```json
  {"llama3.1:8b": {"digest": "46e0c10c…", "calibrated_at": "2026-07-19",
                    "calibration_ref": "docs/runs/2026-07-11-m72-calibration.md"},
   "gemma4:e4b": {…}, "qwen2.5:7b-instruct": {…}}
  ```
- `doctor.py` thêm check OPTIONAL `Model digests`: gọi `/api/tags` (đã gọi
  sẵn — response có digest), so với lock. Lệch ⇒ trạng thái CẢNH BÁO kèm
  fix_hint: "model drift — chạy tái hiệu chuẩn trước khi tin verdict; xem
  D39.1 §giao-thức". Không chặn pipeline (OPTIONAL) — nhưng:
- `screen_run`/`rob_run`: đầu batch, nếu digest hiện tại lệch lock ⇒
  event `MODEL_DRIFT` (uid="screening:batch"/"rob:batch", detail ghi digest
  cũ→mới). Console D37 Tab 2 hiển thị. Fail-loud, không fail-stop.
- **Giao thức tái hiệu chuẩn (runbook, nằm cuối file lock dạng comment
  không được — JSON không comment; ghi trong spec này):** (1) chạy lại bộ
  hiệu chuẩn M7.2 (PM-owned) trên model mới; (2) κ ≥ 0.75 ⇒ PR cập nhật
  lock + hồ sơ docs/runs mới; κ < 0.75 ⇒ ở lại digest cũ
  (`ollama pull model@<digest>` ghim lại), mở điều tra.
- Test: doctor với tags mock lệch lock ⇒ cảnh báo; khớp ⇒ OK; thiếu file
  lock ⇒ check skip êm (không crash máy chưa setup).

## D39.2 — Nối Outbound Interceptor vào Notion publish (B2)

**Vấn đề:** bất biến #7 hứa "Interceptor áp lên mọi luồng ra ngoài" nhưng
`notion_page.py` không import guard nào — lời hứa chưa là code.

**Thiết kế:**
- Trong `NotionPublisher.publish`, SAU `build_page_payload` và TRƯỚC mọi call
  client: serialize payload (`json.dumps`, ensure_ascii=False) → đưa qua
  API check của `tools/guard/outbound.py`. Phát hiện ⇒ KHÔNG publish,
  event `OUTBOUND_BLOCKED` (uid, detail = loại pattern match — KHÔNG chép
  giá trị bị bắt vào event, tránh secret lọt vào audit log), UI hiện lỗi rõ.
  Dry-run cũng check (payload in ra console cũng là một dạng xuất).
- Zero-touch `tools/guard/` (gate D2): chỉ IMPORT, không sửa guard. Nếu API
  guard hiện tại không nhận chuỗi đơn — viết adapter mỏng TRONG notion_page.
- Test: payload chứa pattern secret giả ⇒ publish bị chặn + event đúng +
  status doc KHÔNG đổi (không thành APPROVED khi bị chặn); payload sạch ⇒
  publish như cũ (mock client).

## D39.3 — Backup staging DB xoay vòng (B10)

**Vấn đề:** staging DB là hồ sơ audit của cả SR; chưa có backup nào.

**Thiết kế:**
- `scripts/backup_staging.sh`: `sqlite3 <db> ".backup '<dir>/staging-YYYYMMDD-HHMMSS.db'"`
  (WAL-safe, không cần dừng writer) vào `staging/backups/`; giữ 7 bản mới
  nhất (xóa cũ hơn); chạy được tay + launchd template mới
  `com.sragent.backup.plist.template` (đêm, sau nightly warehouse để tránh
  chồng I/O). `.gitignore` thêm `staging/backups/`.
- Restore = copy file đè + chạy doctor — ghi thành 3 dòng hướng dẫn trong
  header script (runbook tại chỗ, không tài liệu riêng dễ lạc).
- Test: script chạy trên DB tmp tạo ≥1 file backup mở được bằng sqlite3 và
  đếm đúng số bản giữ lại (bash test qua pytest subprocess, offline).

## D39.4 — Single-writer lock (B6, luật Single-Writer thành cơ chế)

**Vấn đề:** orchestrator batch + 2 UI + heal job có thể cùng GHI một file DB.
WAL làm hệ không hỏng, nhưng interleaving người-máy giữa batch tạo trạng
thái khó đoán (Reject giữa batch, adjudicate giữa rob…).

**Thiết kế (cộng tác, không cưỡng chế OS — đủ cho single-machine):**
- `sr_agent/store/writer_lock.py`: `acquire(role) -> bool` tạo
  `staging/.sr_writer.lock` (JSON: role, pid, started_at) bằng
  `open(..., "x")` (atomic); `release()`; `holder() -> info | None` tự dọn
  lock mồ côi (pid chết — check `os.kill(pid, 0)`).
- `sr_run.py run`: acquire("orchestrator") đầu, release cuối (kể cả trên
  exception — finally). Không acquire được ⇒ in holder + rc=2.
- Hai UI: mỗi rerun gọi `holder()`; có holder khác ⇒ banner đỏ + mọi nút
  ghi disable (read-only mode). UI KHÔNG acquire lock (thao tác người là
  click lẻ, không phải phiên ghi dài — tránh người quên release).
- Heal/nightly job: acquire("heal") với timeout bỏ qua êm nếu bận.
- Test: acquire đôi ⇒ False; lock mồ côi pid chết ⇒ tự dọn + acquire được;
  release trong finally khi runner con raise.

## Thứ tự thi công đề xuất
D39.2 (nợ bất biến, nhỏ nhất) → D39.4 (điều kiện an toàn cho console D37)
→ D39.1 → D39.3. Cả bốn không phụ thuộc D36/D37/D38 — chạy song song được
với FL-2.
