# D36 — SR Run Scoping (schema v2: một SR = một run_id)

**Trạng thái:** thiết kế đóng băng 2026-07-19 (PM Fable 5). Thi công theo mandate
riêng; PM thẩm định theo `pm-succession.md` §3. **Không thiết kế lại.**
**Giải quyết:** premortem B4 (queued quá tải ngữ nghĩa) + FL-1 F3 (PRISMA cộng
dồn mọi run: "Screened 30" trong khi run chỉ screen 10).

## §0. Vấn đề gốc (không phải triệu chứng)

Hệ có HAI vòng đời dùng chung một DB nhưng chỉ MỘT trục trạng thái (`status`):
1. **Triage đơn-tài-liệu** (AnesthOS-lite): queued → người Approve/Reject → Notion.
2. **Tuyến SR**: một *chiến dịch* có mở đầu (query+protocol) và kết thúc (consensus),
   trải nhiều ngày, nhiều batch, nhiều cổng người.

Mọi bug lớn gần đây đều là hệ quả của việc vòng đời 2 không có danh tính riêng:
gate sai chỗ (PR #21), TTL nuốt corpus (PR #23), extract gặm doc tồn (PR #26),
PRISMA trộn lịch sử (FL-1 F3). Vá từng chỗ là chữa triệu chứng; D36 chữa gốc:
**cho tuyến SR một danh tính — `run_id` — mà không đập vòng đời 1.**

## §1. Quyết định kiến trúc (đã cân nhắc, chốt)

**Một điểm gắn thẻ duy nhất: cột `run_id` trên bảng `events`.**
- KHÔNG thêm run_id vào screening/extraction/rob_assessment (3 bảng × migration
  × N call-site = churn lớn vào code đã hiệu chuẩn). Mọi chuyển trạng thái stage
  ĐỀU đã phát event (SCREENED, SCREEN_INCLUDED/EXCLUDED, ELIG_*, EXTRACT_*,
  ROB_*) — events là nhật ký đầy đủ, chỉ cần nó mang run_id là PRISMA/membership/
  gate đều scope được.
- Hệ quả bắt buộc: PRISMA v2 đếm HOÀN TOÀN từ events (bỏ các query đếm trực
  tiếp bảng screening/documents hiện tại trong `prisma_report.py`) — events trở
  thành nguồn sự thật duy nhất cho số liệu flow. Sidecar tables giữ vai trò
  chứa DỮ LIỆU (verdict, quote), events chứa DÒNG CHẢY.

**Truyền run_id bằng env `SR_RUN_ID`, stamp tự động trong `log_event`.**
- Các runner con (`screen_run`, `eligibility_run`, …) mở StagingStore RIÊNG bên
  trong `main(argv)` của chúng — truyền tham số xuyên 5 CLI là churn lan rộng.
  Thay vào đó: orchestrator set `os.environ["SR_RUN_ID"]` trước khi gọi runner;
  `StagingStore.log_event` đọc env tại thời điểm ghi:
  ```python
  def log_event(self, uid, event_type, detail="", run_id=None):
      rid = run_id if run_id is not None else os.getenv("SR_RUN_ID") or None
      ...INSERT INTO events (uid, event_type, detail, run_id, created_at)...
  ```
- Tradeoff ghi nhận tường minh: env là kênh ngầm (hidden coupling). Đổi lại:
  0 dòng churn trong 5 runner đã hiệu chuẩn; tham số `run_id=` tường minh vẫn
  tồn tại cho UI/console (D37) — chỗ nào biết run_id thì truyền thẳng, env chỉ
  là đường mặc định cho tiến trình orchestrator.

## §2. Schema (additive + migration)

```sql
-- bảng mới (không đụng bảng `runs` heartbeat M4 đã có)
CREATE TABLE IF NOT EXISTS sr_runs (
    run_id         TEXT PRIMARY KEY,   -- "sr-YYYYMMDD-HHMMSS-<4hex>"
    query          TEXT NOT NULL,
    protocol_path  TEXT NOT NULL,
    protocol_sha256 TEXT NOT NULL,     -- chốt integrity: protocol đổi giữa chừng = phát hiện được
    state          TEXT NOT NULL,      -- OPEN | CONSENSUS_READY | CLOSED | ABANDONED
    created_at     TEXT NOT NULL,
    closed_at      TEXT
);
-- cột mới trên events (nullable — mọi row cũ giữ NULL, không mất dữ liệu)
ALTER TABLE events ADD COLUMN run_id TEXT;
CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id);
```
Migration trong `StagingStore.__init__`: `PRAGMA table_info(events)` thiếu
`run_id` → ALTER. Idempotent, chạy trên DB cũ lẫn mới. Test bắt buộc: mở DB
tạo bằng schema cũ (dựng tay trong test) → init → cột tồn tại, data cũ nguyên.

**Membership là VIEW dẫn xuất, không phải bảng:**
doc thuộc run R ⟺ `EXISTS (SELECT 1 FROM events WHERE uid=? AND run_id=R)`.
Không có bảng membership để đồng bộ = không có bug lệch đồng bộ.

## §3. Thay đổi hành vi từng thành phần

| Thành phần | Thay đổi |
|---|---|
| `sr_run.py` | `run` không có `--run` ⇒ tạo run mới (ghi sr_runs, set env). `run --run <id>` ⇒ resume (kiểm state=OPEN + protocol_sha256 khớp file hiện tại, lệch ⇒ rc=2 fail-closed). `status --run <id>`; `runs` subcommand mới liệt kê sr_runs. |
| Gate `consensus_review` | predicate per-run: `EXISTS events(run_id=<current>, event_type='CONSENSUS_APPROVED')` — thay `satisfied=lambda: False` hiện tại. Event này CHỈ do UI console (D37) ghi. |
| `prisma_report.py` | `--run <id>` ⇒ mọi count từ events có run_id=id. Không cờ ⇒ hành vi cũ (global, backward-compat, đánh dấu "legacy/all-history" trong output để hết mập mờ). |
| `ui/app.py` (triage) | Hàng đợi WIP loại trừ doc thuộc run OPEN: `uid NOT IN (SELECT DISTINCT uid FROM events WHERE run_id IN (SELECT run_id FROM sr_runs WHERE state='OPEN'))` — nút Reject không còn cắt cụt corpus SR im lặng (đóng nốt B4-interim). |
| `purge_expired` | thêm miễn trừ: uid có event thuộc run OPEN (phòng thủ 2 lớp cùng miễn trừ sidecar hiện có). |
| Stage runners | **0 thay đổi** (đó là mục tiêu của §1). |

## §4. Vòng đời run (state machine)

`OPEN` —(người bấm consensus-approve trên D37, điều kiện: 0 escalation chưa xử)→
`CONSENSUS_READY` —(BS4 chạy xong, CONSENSUS_COMPLETED)→ `CLOSED`.
`OPEN` —(người bấm hủy trên D37, ghi lý do)→ `ABANDONED` (doc của run được thả
về vòng đời triage: hết miễn trừ TTL/WIP).
Chỉ D37/BS4 đổi state; orchestrator chỉ ĐỌC state (bất biến #6 giữ nguyên).

## §5. Test offline bắt buộc (`tests/test_run_scoping.py`)

(a) migration DB cũ → có cột, data nguyên; (b) log_event stamp env đúng +
tham số tường minh thắng env; (c) hai run song song không nhìn thấy event của
nhau qua view membership; (d) resume sai protocol_sha256 ⇒ rc=2; (e) gate
consensus per-run: approve run A không mở gate run B; (f) PRISMA --run chỉ đếm
event của run; (g) WIP triage loại doc thuộc run OPEN; (h) purge miễn trừ doc
run OPEN; (i) ABANDONED thả miễn trừ. Ratio assert/test ≥ 2.

## §6. Ngoài phạm vi
Multi-DB per run (bị bác: mất lịch sử chéo run + phá mọi tool hiện có) ·
run_id trên sidecar tables (bị bác: churn, xem §1) · UI console (D37 riêng).
