# TASK SPEC TS-M7.3 — Eligibility Agent (PRISMA giai đoạn 3: duyệt toàn văn)

> **Dành cho**: Antygravity. Copy nguyên văn làm đề bài. **Nền**: M6 đã merge
> (`tools/screen_run.py`, bảng `screening`, criteria, gate). Thiết kế gốc: D30 §2.2 (A5), §3.1 (EF).
> **Có thể làm SONG SONG với First Light (runbook M7.1)** — hai việc không đụng file nhau;
> nhưng KHÔNG chạy eligibility trên DB thật trong lúc First Light đang chạy.

## A. Bối cảnh & nhánh

- Nhánh nguồn: `claude/sr-agent-pipeline-design-rqtctp` (176 tests — không được làm đỏ).
- Nhánh làm việc: `feat/m7-eligibility`. **MỘT PR duy nhất** về nhánh nguồn.
- Baseline trước khi code: `.venv/bin/python -m pytest` → 176 passed; `bash scripts/gate_m6.sh` → PASS.

## B. Mục tiêu (một câu)

Lấp giai đoạn PRISMA còn khuyết cuối cùng: sau khi screening kép INCLUDE, duyệt **toàn văn**
theo bộ tiêu chí EF — trung thực tuyệt đối với giới hạn "nguồn không có toàn văn".

## C. Vùng cấm (kế thừa nguyên văn TS-D30 mục C)

Không sửa `router.py`/`config.py`/class `Pipeline`/schemas/`DocStatus`; không dependency mới;
không đưa ngữ nghĩa vào core; **ZERO DDL** — tái dùng bảng `screening` với `agent='eligibility'`;
tests offline 100%; mọi lệnh Ollama temp 0 + structured; đầu ra không qua validation = vô hiệu.

## D. Hợp đồng

### D1. Bổ sung criteria (tools/criteria/default.json — thêm, không sửa ET)

| Mã | label_vi | description_en (viết đầy đủ khi hiện thực) |
|---|---|---|
| EF1 | Không có đánh giá thực nghiệm | no empirical evaluation while protocol requires measurable outcome |
| EF2 | Outcome không được báo cáo | experiments exist but the protocol outcome is not measured/reported |
| EF4 | Trùng dữ liệu (salami slicing) | same authors + same experiments already in the included set |

(EF3 "không truy xuất được toàn văn" KHÔNG phải verdict LLM — nó là nhánh dữ liệu, xem D3.)

### D2. `tools/eligibility_run.py`

- CLI: `--protocol <path> [--limit N] [--db PATH] [--criteria PATH]` — mirror `screen_run.py`.
- Tập đầu vào: doc `status='queued'` CÓ event `SCREEN_INCLUDED` và CHƯA có event `ELIG_*`.
- **Import tái dùng** từ `tools/screen_run.py`: `verify_quote`, `ScreenVerdict` (criterion_id
  giờ nhận EF1/EF2/EF4), pattern invoke + Transient discipline (T3) — không chép lại code.
- Văn bản nguồn cho verifier: toàn bộ sections + abstract (pattern `full_text_context`
  trong `evidence_extract.py`).

### D3. Luồng quyết định (mỗi doc)

```
không có full_text/sections đáng kể → log_event ELIG_ABSTRACT_ONLY, GIỮ NGUYÊN doc
   (trung thực: không giả vờ đã đọc toàn văn; KHÔNG gọi LLM)
có toàn văn → 1 agent LLM (model chính) verdict theo EF kèm quote:
   exclude hợp lệ (EF + quote khớp verifier) → set_status REJECTED + ELIG_EXCLUDED(criterion)
   include                                   → ELIG_INCLUDED
   invalid (thiếu/bịa quote, EF lạ)          → ELIG_ESCALATED, GIỮ NGUYÊN (bảo thủ)
ghi verdict vào bảng screening với agent='eligibility', model=<tag thật>
```

(Một agent là đủ ở giai đoạn này — dual+tie-breaker chỉ ở Screening; đúng D30.)

### D4. `tools/prisma_report.py` — thay hard-code

Thay `full_text_excluded = 0` bằng đếm event: assessed = `ELIG_INCLUDED + ELIG_EXCLUDED`;
excluded-with-reasons group theo criterion trong detail của `ELIG_EXCLUDED`;
ô "not retrieved / abstract-only" = đếm `ELIG_ABSTRACT_ONLY`.

## E. Tests (`tests/test_eligibility.py`, mock respx theo pattern test_screening)

1. Doc không toàn văn → ELIG_ABSTRACT_ONLY, status nguyên, KHÔNG có HTTP call nào tới Ollama.
2. Exclude EF1 quote khớp → REJECTED + event đúng criterion.
3. Quote bịa → verdict vô hiệu → ELIG_ESCALATED, status nguyên.
4. Doc chưa SCREEN_INCLUDED → không được đụng tới.
5. Transient giữa batch → dừng, không event rác (mirror test T3).
6. prisma_report: DB dàn dựng → ô Eligibility ra đúng số.

## F. Nghiệm thu (dán output vào PR)

1. `.venv/bin/python -m pytest` → 176 + mới, toàn xanh. 2. `bash scripts/gate_m6.sh` → PASS.
3. `git diff origin/claude/... -- sr_agent/` → RỖNG HOÀN TOÀN (spec này không có ngoại lệ additive).
4. PR mô tả 4 phần như tiền lệ PR #2, kèm URL dạng `/pull/<số>` — không link wizard.
