# BS4 — Consensus Generator (spec thi công)

**Trạng thái:** spec đóng băng 2026-07-19 (PM Fable 5, phần thiết kế khó nhất
làm trước khi chuyển giao). Executor thi công theo mandate trỏ vào spec này;
PM kế nhiệm thẩm định theo `pm-succession.md` §3 — **không thiết kế lại**.

**Điều kiện kích hoạt:** CHỈ thi công sau khi FL-1 (Pipeline First Light) merge
— phân bố verdict/escalation thật từ FL-1 là dữ liệu nghiệm thu của BS4.

## §0. Vị trí & vì sao đây là mắt xích nhạy nhất

`consensus` là phase cuối tuyến SR (sau cổng người `consensus_review`), sinh
**báo cáo tổng hợp** từ evidence đã trích + trọng số RoB. Đây là nơi duy nhất
LLM viết văn xuôi dài về số liệu y văn → nơi duy nhất hallucination có thể
thành khuyến cáo sai. Toàn bộ thiết kế xoay quanh một câu: **LLM không bao giờ
là nguồn của bất kỳ con số hay claim nào — nó chỉ tường thuật một bảng đã
được code tất định dựng sẵn.** (Pattern Layer A của D32, đã có tiền lệ chạy.)

## §1. Bất biến CỨNG (ngoài bộ CLAUDE.md chung)

1. **Claim-ledger bắt buộc:** mọi claim trong báo cáo phải là một hàng trong
   `consensus_claim` với ≥1 nguồn `(uid, quote, verified=1)`. Claim không nguồn
   không tồn tại — không render.
2. **Số qua firewall:** toàn văn báo cáo phải qua
   `tools/guard/firewall.check_output(report, source_texts, strict=True)` với
   `source_texts` = tập quote đã verify trong `extraction` + `rob_assessment`.
   Verdict fail → báo cáo bị chặn, event `CONSENSUS_BLOCKED`, KHÔNG retry-sửa-số.
3. **Weighting tất định (pure function):**
   `weight(uid) = f(rob_overall)` với f cố định: `Low→1.0`, `Some concerns→0.5`,
   `High→0.25`, `VOID/ESCALATED-chưa-phân-xử→0.0` (loại khỏi tổng hợp, ghi rõ
   trong phần "Excluded from synthesis" của báo cáo). Đọc từ protocol JSON key
   `consensus.rob_weights` nếu có; key lạ/thiếu giá trị nào → **raise** (luật
   Fail-Closed, không default).
4. **LLM chỉ prose:** input LLM = bảng claim đã dựng (uid, field, value, quote,
   weight); nhiệm vụ = nối văn. Temperature 0 + structured output
   `{narrative: str}`. Schema sai → VOID → dùng **fallback template tất định**
   (báo cáo dạng bảng thuần, không văn xuôi) — hệ không bao giờ kẹt vì LLM.
5. **Cổng người đứng TRƯỚC:** BS4 chỉ chạy trên doc đã qua `consensus_review`.
   Vị ngữ gate (sửa trong `sr_run.py` cùng PR): tồn tại event
   `CONSENSUS_APPROVED` cho run hiện hành, event này CHỈ được ghi bởi đường UI
   (bất biến #6). v1 nếu UI tab chưa có: gate giữ `satisfied=False` — người
   chạy `consensus` thủ công qua CLI riêng sau khi tự xác nhận; KHÔNG thêm
   lệnh CLI ghi CONSENSUS_APPROVED.
6. **Topic-blind:** mọi ngữ nghĩa (tên outcome, cách nhóm claim) từ protocol
   JSON + dữ liệu extraction; `tools/consensus_run.py` không chứa từ vựng miền.

## §2. Kiến trúc & dữ liệu

**Input query (tập doc đủ điều kiện):**
```sql
SELECT uid FROM documents WHERE status='queued'
  AND uid IN (SELECT uid FROM events WHERE event_type='ROB_COMPLETED')
  AND uid IN (SELECT uid FROM extraction WHERE verified=1 GROUP BY uid)
```
(doc `ROB_ESCALATED` chưa có phân xử `agent='human'` → tự động vào nhóm
weight 0.0 "Excluded", không chặn cả batch.)

**Bảng mới (additive, `staging.py`):**
```sql
CREATE TABLE IF NOT EXISTS consensus_claim (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,          -- nhóm claim theo lần tổng hợp
    field TEXT NOT NULL,           -- PICO field / outcome key từ protocol
    value TEXT NOT NULL,           -- giá trị đồng thuận (từ extraction, nguyên văn)
    support_json TEXT NOT NULL,    -- [{uid, quote, weight}] — ledger
    agreement REAL NOT NULL,       -- tổng weight ủng hộ / tổng weight có mặt
    conflict INTEGER NOT NULL,     -- 1 nếu tồn tại giá trị đối nghịch weight>0
    created_at TEXT NOT NULL
);
```

**Pure functions (thi công + test trước, LLM sau):**
- `build_claim_table(store, protocol, uids) -> list[Claim]` — gom extraction
  theo field; giá trị khác nhau cho cùng field → mỗi giá trị một claim, đánh
  `conflict=1` cho cả nhóm; agreement = Σweight(ủng hộ)/Σweight(tất cả).
- `rob_weight(overall: str, weights: dict) -> float` — fail-closed (bất biến 3).
- `render_report(claims, narrative | None) -> str` — markdown: bảng claim +
  ledger phụ lục + mục Excluded + mục Conflicts (conflict KHÔNG được hòa giải
  bằng LLM — liệt kê cả hai phía kèm nguồn, người đọc phân xử; tinh thần S5
  của D32: từ chối tổng hợp thỏa hiệp).
- PRISMA: gọi `tools/prisma_report` để nhúng flowchart cuối báo cáo.

**Luồng `main(argv)`:** `--protocol --run-id [--limit] [--db]` → build claims
→ ghi `consensus_claim` (idempotent: DELETE theo run_id trước) → LLM narrative
(1 call, có fallback) → firewall check → ghi file
`docs/runs/<date>-consensus-<run_id>.md` + event `CONSENSUS_COMPLETED`
(hoặc `CONSENSUS_BLOCKED`).

## §3. Test offline BẮT BUỘC (`tests/test_consensus.py`, mock Ollama)

(a) `rob_weight` đủ 4 nhánh + raise khi key lạ; (b) claim không quote
verified không bao giờ vào bảng; (c) hai study xung đột giá trị → conflict=1,
cả hai phía đều trong báo cáo, không bên nào bị LLM xóa; (d) doc ESCALATED
chưa phân xử → weight 0 + xuất hiện trong Excluded; (e) firewall bắt số bịa:
narrative chứa số không có trong source_texts → CONSENSUS_BLOCKED; (f) LLM
sai schema → fallback template vẫn sinh báo cáo đầy đủ ledger; (g) idempotent
theo run_id. Ratio assert/test ≥ 2.

## §4. Ngoài phạm vi

UI tab cho CONSENSUS_APPROVED (BS4.1 riêng) · meta-analysis thống kê (effect
size pooling — KHÔNG làm, chỉ đồng thuận định tính có trọng số) · sửa
firewall/guard (zero-touch) · nối warehouse.

## §5. Nghiệm thu (PM chạy, không tin khai)

Checklist `pm-succession.md` §3 + riêng BS4: chạy bộ đề nghiệm thu PM-Owned
(PM tự dựng ≥5 doc giả lập trong tmp DB với phân bố lấy từ số liệu FL-1: có
conflict, có escalated, có VOID) — báo cáo sinh ra phải: đủ ledger, đúng
Excluded, conflict hai phía, firewall xanh. Bộ đề này KHÔNG giao executor
(luật PM-Owned).
