# TASK SPEC TS-D30 — Hiện thực M6: Multi-Agent Systematic Review (PRISMA/PICO) cho SR-Agent

> **Dành cho**: tác tử thực thi **Antygravity**. Copy nguyên văn tài liệu này làm đề bài.
> **Nguồn thiết kế (source of truth)**: `docs/specs/D30-prisma-pico-multiagent.md` — ĐỌC TRƯỚC KHI CODE.
> Kiến trúc nền: `docs/HANDOVER.md`. Tiền lệ format: `docs/specs/TS-D29-search-to-id.md`.
> **Người nghiệm thu**: chủ dự án (con người). Mọi thay đổi merge qua Pull Request có người duyệt.

---

## A. Bối cảnh repo & môi trường

- Repo: `gunthqq30223132/9router`. **Toàn bộ SR-Agent nằm trên nhánh `claude/sr-agent-pipeline-design-rqtctp`** (main chỉ có template).
- Nhánh làm việc: tạo `feat/m6-prisma-agents` từ nhánh trên. **Mỗi pha một PR riêng** về nhánh gốc (mục H).
- Môi trường: macOS (MacBook Air M4 16GB), Python 3.11, venv tại `.venv`.
- Lệnh kiểm tra chuẩn: `.venv/bin/python -m pytest` — hiện **111 pass, không được làm đỏ bất kỳ test nào**.
- Setup nếu máy chưa có: `make setup && make doctor` (xem README).

## B. Mục tiêu (một câu)

Bổ sung 2 giai đoạn PRISMA còn khuyết (Screening kép độc lập + Tie-breaker; Extraction có minh chứng
bắt buộc exact quote) dưới dạng **lớp ngoại vi + bảng sidecar**, để SR-Agent trở thành một cỗ máy
Systematic Review hoàn chỉnh mà core pipeline không đổi một dòng logic.

## C. Vùng cấm (forbidden zones — vi phạm là FAIL nghiệm thu, không có ngoại lệ)

1. **KHÔNG sửa** `sr_agent/ingest/router.py`, `sr_agent/config.py`, class `Pipeline` trong
   `sr_agent/pipeline.py`, schema `Document`/`TechnicalMetadata` trong `sr_agent/models/schemas.py`,
   enum `DocStatus`.
2. Điểm chạm duy nhất được phép trong `sr_agent/`:
   - `store/staging.py`: **thêm** DDL 2 bảng mới + method mới (mục D3) — additive, không đổi bảng/method cũ.
   - `monitor/health.py` + `monitor/alerts.py`: **thêm** field snapshot + 2 rule alert mới (mục F3) — additive.
   - `ui/app.py`: thêm badge/metric (mục F4).
3. **KHÔNG thêm dependency mới** vào `pyproject.toml`. Đặc biệt: Cohen's κ tự viết bằng công thức
   (mục D4) — **CẤM scipy/sklearn/pandas**.
4. **KHÔNG đưa** chuỗi chủ đề/protocol ngữ nghĩa vào bất kỳ trường nào của `Document` — mù chủ đề của
   core là bất khả xâm phạm. Ngữ nghĩa sống ở `tools/` và bảng sidecar.
5. **KHÔNG xử lý dữ liệu y sinh/lâm sàng**: pha M6d (profile PubMed/Cochrane/Embase) trong thiết kế D30
   **bị chặn bởi quyết định D30-S1 của chủ dự án — KHÔNG hiện thực trong task này**, kể cả khi thấy
   connector PubMed có sẵn.
6. **KHÔNG bypass lỗi**: đầu ra LLM không qua validation → verdict vô hiệu (mục F2), không "sửa giúp",
   không retry đổi prompt để ép ra kết quả.
7. Credentials không bao giờ nằm trong code/prompt/commit — chỉ `.env` (đã gitignore) hoặc Keychain.
8. Mọi lệnh gọi Ollama: `temperature 0` + structured output (`OllamaClient.generate_structured`,
   `sr_agent/parser/ollama_client.py`) — cấm parse JSON tự do từ text.
9. Tests **offline 100%**: mock Ollama bằng `respx` (xem `tests/test_topic_run.py::TestExpand`),
   fetcher giả theo pattern `tests/test_pipeline.py::FakeFetcher`. Không test nào cần mạng/Ollama/key.
10. Docstring + thông điệp tiếng Việt, giải thích "tại sao" ở đầu file — đúng convention codebase.

## D. Hợp đồng dữ liệu (contracts — đúng nguyên văn, không tự biến tấu)

### D1. `ReviewProtocol` (Pydantic, đặt trong `tools/`, KHÔNG trong `sr_agent/models/`)

```python
class PicoConcept(BaseModel):
    concept: str                 # cụm chính, tiếng Anh
    synonyms: list[str] = []     # OR trong cùng khối
    required: bool = True        # False = không vào query, chỉ dùng khi screening

class ReviewProtocol(BaseModel):
    topic_vi: str                        # ý định gốc — chỉ là nhãn/audit
    population: PicoConcept
    intervention: PicoConcept
    comparison: PicoConcept | None = None
    outcome: PicoConcept | None = None
    year_range: tuple[int, int] | None = None
    languages: list[str] = ["en"]
    study_types_excluded: list[str] = ["editorial", "poster", "thesis"]
    exclusion_criteria: list[str]        # tập con của ET1..ET7, EF1..EF4
```

Quy tắc dựng query (pure function, KHÔNG LLM): synonyms nối `OR` trong khối, khối nối `AND`,
**chỉ P và I vào query** (C/O chỉ dùng khi screening); dialect per-source qua `tools/profiles/*.json`
+ `ProfiledFetcher` sẵn có (`tools/topic_run.py`). Nhớ: `ArxivFetcher.search` tự tiền tố `all:` —
template arXiv chỉ là cụm từ.

### D2. `ScreenVerdict` (đầu ra bắt buộc của mỗi screener và tie-breaker)

```python
class ScreenVerdict(BaseModel):
    verdict: Literal["include", "exclude"]
    criterion_id: str | None      # BẮT BUỘC khi exclude — một mã ET1..ET7
    evidence_quote: str | None    # BẮT BUỘC khi exclude — verbatim từ title/abstract
    confidence: Literal["high", "low"]
```

Verdict `exclude` thiếu `criterion_id`/`evidence_quote`, hoặc quote không qua verifier (D5)
→ **verdict VÔ HIỆU = abstain = xử lý như bất đồng**. Ghi sổ nguyên trạng đầu ra hỏng để audit.

### D3. DDL sidecar (thêm vào `_SCHEMA` của `store/staging.py`, theo pattern bảng `runs`/`alerts` M4)

```sql
CREATE TABLE IF NOT EXISTS screening (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT NOT NULL,              -- FK mềm sang documents.uid
  agent TEXT NOT NULL,            -- 'screener_a' | 'screener_b' | 'tiebreaker'
  model TEXT NOT NULL,
  verdict TEXT NOT NULL,          -- 'include' | 'exclude' | 'invalid'
  criterion_id TEXT,
  evidence_quote TEXT,
  confidence TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extraction (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT NOT NULL,
  field TEXT NOT NULL,            -- 'has_code_repo' | 'dataset_spec' | 'baselines' | 'metrics' | ...
  value TEXT NOT NULL,
  quote TEXT NOT NULL,
  section TEXT NOT NULL,
  verified INTEGER NOT NULL,      -- 1 = quote khớp verbatim; 0 = bị hủy (giữ để audit)
  created_at TEXT NOT NULL
);
```

Method store mới (additive): `add_screen_verdict(...)`, `screen_verdicts(uid)`,
`add_extraction(...)`, `extractions(uid, verified_only=True)`, `screening_stats(hours=24)`
(đếm đồng thuận/bất đồng/vô hiệu phục vụ κ và health).

### D4. Cohen's κ (tự viết, pure function trong `tools/` hoặc `sr_agent/monitor/health.py`)

Hai rater, hai nhãn (include/exclude), trên các doc mà CẢ HAI verdict hợp lệ:
`p_o` = tỷ lệ đồng thuận quan sát; `p_e = p_inc_a*p_inc_b + p_exc_a*p_exc_b`;
`κ = (p_o − p_e) / (1 − p_e)`; biên: `1 − p_e == 0` → κ = 1.0 nếu đồng thuận tuyệt đối, else 0.0;
< 2 doc hợp lệ → κ = None (không đủ dữ liệu, không alert).

### D5. Verifier quote tất định (pure function, dùng chung cho screening + extraction)

1. Chuẩn hóa HAI phía: casefold, gộp whitespace liên tiếp thành 1 space, thống nhất
   `'‘’` → `'`, `"“”` → `"`, `–—` → `-`.
2. Quote chuẩn hóa phải là **substring nguyên văn** của văn bản nguồn chuẩn hóa
   (screening: title + abstract; extraction: đúng section khai trong trường `section`).
3. KHÔNG fuzzy match, KHÔNG cắt sửa quote. Fail → verdict vô hiệu / field `verified=0`.

## E. Bộ tiêu chí loại trừ (dữ liệu, không hard-code trong prompt)

Định nghĩa ET1..ET7 (vòng title/abstract) và EF1..EF4 (vòng full-text) lấy **nguyên văn** từ
`docs/specs/D30-prisma-pico-multiagent.md` §3.1 — đặt thành file dữ liệu
`tools/criteria/default.json` `{id, label_vi, description_en}`; prompt của screener nạp từ file này
+ protocol, không chép cứng vào Python.

## F. Yêu cầu chức năng theo pha

### PHA M6a — Protocol + 1 screener + PRISMA report (PR #1)

- **FR-a1** `tools/protocol_build.py`: `--topic "..." [--draft-llm]` → sinh file
  `tools/protocols/<slug>.json` theo schema D1. Có `--draft-llm` thì Ollama đề xuất nháp
  (structured, temp 0); Ollama tắt → sinh skeleton rỗng kèm hướng dẫn điền tay (suy giảm êm,
  pattern `expand_terms` trong `tools/topic_run.py`). In cảnh báo rõ: **protocol phải được con
  người duyệt/sửa trước khi dùng** — tool không bao giờ tự chốt.
- **FR-a2** `tools/protocol_build.py --render <protocol.json>`: render query per-source theo D1
  (pure function) và in ra; `--run` thì chuyển thẳng cho hàm sẵn có của `tools/topic_run.py`
  (import, không duplicate code).
- **FR-a3** DDL + method store D3 (chỉ bảng `screening` ở pha này; bảng `extraction` để M6c).
- **FR-a4** `tools/screen_run.py --protocol <path> [--limit N]`: với từng doc `status='queued'`
  chưa có verdict trong `screening`: chạy **một** screener (`screener_a`, model mặc định
  `OLLAMA_MODEL`, khung thiên-giữ — xem F2), validate qua D2+D5, ghi bảng `screening` +
  `store.log_event(uid, "SCREENED", ...)`. Pha này CHƯA đổi status doc — chỉ ghi sổ (chạy song
  song an toàn với vận hành thật).
- **FR-a5** `tools/prisma_report.py [--db PATH]`: in sơ đồ dòng chảy PRISMA dạng markdown từ
  SELECT thuần: identified (bảng `runs`/report_json + events FETCHED), duplicates removed (D34,
  events/report), rubric-rejected, screened n / excluded n theo `criterion_id`, included
  (approved*). Doc thiếu full_text đếm vào ô "abstract-only". Exit 0 luôn (tool báo cáo).

### PHA M6b — Screener thứ 2 + κ + Tie-breaker + tích hợp status (PR #2)

- **FR-b1** Screener thứ 2 (`screener_b`): **khác model** (mặc định `gemma3:4b`, override qua env
  `SR_SCREEN_MODEL_B`) **và khác khung lập luận** (thiên-loại, checklist từng ET). Hai screener chạy
  tuần tự, **không chia sẻ context** — prompt của B không chứa bất kỳ dấu vết đầu ra của A.
- **FR-b2** Hợp nhất verdict trong `screen_run.py`:
  - Đồng thuận `exclude` (cùng hoặc khác criterion đều tính đồng thuận verdict):
    `store.set_status(uid, DocStatus.REJECTED)` + `log_event(uid, "SCREEN_EXCLUDED", criterion...)`.
  - Đồng thuận `include`: `log_event(uid, "SCREEN_INCLUDED", "")`, status giữ nguyên.
  - Bất đồng hoặc có verdict vô hiệu → **Tie-breaker** (`tiebreaker`, model qwen, prompt trọng tài):
    input = doc + protocol + criteria + HAI bộ (criterion, quote) **ẩn danh** (không nhãn "A nói/B nói");
    output = `ScreenVerdict`. `confidence == "high"` và qua validation → chốt theo tie-breaker.
    Ngược lại → **nguyên tắc bảo thủ: GIỮ doc** (status không đổi) + `log_event(uid,
    "SCREEN_ESCALATED", ...)` — người duyệt phân xử trong UI.
  - Doc `REJECTED` bởi screening giữ vĩnh viễn làm audit (đúng quy ước hiện hành, không xóa).
- **FR-b3** κ mỗi lần chạy `screen_run` (công thức D4) in ra + lưu vào summary; đủ dữ liệu và
  κ < 0.6 → tham gia rule alert F3.
- **FR-b4** Badge UI: doc có event `SCREEN_ESCALATED` chưa xử lý → 🔶
  "Screening bất đồng — cần người phân xử" trong tab hàng đợi (pattern badge ⚠️ M4, đọc từ bảng
  `screening`/`events`, KHÔNG thêm field vào Document).

### PHA M6c — Extraction có minh chứng (PR #3, độc lập với M6b, có thể làm song song)

- **FR-c1** Bảng `extraction` + method store (D3).
- **FR-c2** `tools/evidence_extract.py --limit N`: với doc `queued` có abstract/sections: Ollama
  trích các field (tối thiểu: `has_code_repo`, `dataset_spec`, `baselines`, `metrics`) theo schema
  `{value, quote, section}`; verifier D5 định đoạt: khớp → `verified=1`; không khớp → `verified=0`
  + `log_event(uid, "EXTRACT_UNVERIFIED", field)`. **KHÔNG ghi đè** `Document.tech_meta` — bảng
  sidecar là nguồn hiển thị mới, tech_meta cũ giữ nguyên vai trò.
- **FR-c3** Grounding score = verified/tổng field mỗi doc; hiển thị trong UI cạnh điểm rubric,
  từng field kèm quote + section ngay bên dưới (người duyệt đối chiếu trong một lần nhìn).

### F3. Giám sát (đi cùng M6b/M6c, additive vào monitor)

- `HealthSnapshot` thêm: `screen_kappa_recent`, `screen_escalated_count`, `grounding_avg_24h`.
- 2 rule alert mới trong `desired_alerts` (cùng máy trạng thái, cùng kỷ luật chỉ-notify-khi-chuyển):
  `SCREEN_DISAGREEMENT` (κ gần nhất < 0.6, ≥ 5 doc hợp lệ), `EXTRACT_UNGROUNDED`
  (grounding trung bình 24h < 0.8, ≥ 5 doc có extraction).

### F4. UI (additive vào `ui/app.py`)

Badge 🔶 (FR-b4), grounding score + quote per field (FR-c3), 3 metric screening trong tab 🩺
(đồng thuận / bất đồng đã phân xử / đẩy người).

## G. Tests (offline 100%, cộng vào 111 test hiện có)

- `tests/test_protocol.py`: schema D1 validate; render query P∧I (C/O không lọt vào query);
  draft-llm mock sống/chết (suy giảm êm).
- `tests/test_screening.py`: verifier D5 (khớp sau chuẩn hóa nháy/whitespace; không khớp → vô hiệu);
  exclude thiếu quote → vô hiệu; đồng thuận exclude → REJECTED + event; đồng thuận include → status
  nguyên; bất đồng → tie-breaker được gọi; tie-breaker low-confidence → GIỮ + SCREEN_ESCALATED;
  κ đúng công thức trên bảng 2×2 tay tính sẵn; κ với <2 doc → None; **độc lập**: assert prompt
  gửi cho screener_b không chứa đầu ra screener_a (spy transport).
- `tests/test_extraction.py`: quote khớp → verified=1; quote bịa → verified=0 + event, value KHÔNG
  xuất hiện ở đường hiển thị verified_only; quote đúng chữ nhưng khai sai section → verified=0;
  grounding score đúng số học.
- `tests/test_prisma_report.py`: DB dàn dựng nhỏ → các con số ô PRISMA khớp kỳ vọng.
- Alert mới: pattern `tests/test_monitor.py` (OPEN một lần, RESOLVED một lần, cooldown).

## H. Nghiệm thu (người duyệt chạy đúng các lệnh này trên từng PR)

1. `.venv/bin/python -m pytest` → **toàn bộ xanh** (111 cũ + mới).
2. `git diff origin/claude/sr-agent-pipeline-design-rqtctp -- sr_agent/ingest/ sr_agent/config.py sr_agent/models/schemas.py` → **RỖNG**; diff `sr_agent/pipeline.py` → **RỖNG** (kể cả `main()` — M6 không cần chạm);
   diff `sr_agent/store/staging.py` và `sr_agent/monitor/` chỉ chứa phần additive mục C2.
3. `grep -rn "population\|intervention\|topic_vi" sr_agent/` → không có kết quả nào ngoài (nếu có) comment — ngữ nghĩa không lọt vào core.
4. PR M6a: `tools/protocol_build.py --topic "retrieval augmented generation for QA" --render ...`
   ra query đúng quy tắc P∧I; `screen_run --limit 2` trên DB demo ghi verdict vào bảng `screening`;
   `prisma_report` in sơ đồ có số.
5. PR M6b: kịch bản demo offline (fetcher giả + Ollama mock): 1 doc đồng thuận exclude → REJECTED;
   1 doc bất đồng → escalated + badge 🔶; κ in ra.
6. PR M6c: 1 field quote bịa bị hủy có event; UI hiện grounding score.
7. Không dependency mới: `git diff -- pyproject.toml` rỗng.

## I. Quy ước giao nộp

- Nhánh `feat/m6-prisma-agents` từ `claude/sr-agent-pipeline-design-rqtctp`; commit nhỏ theo FR
  (`M6a-FR-a1: ...`). **3 PR theo pha, đúng thứ tự M6a → M6b → M6c** (M6c được phép song song sau
  khi M6a merge); tiêu đề `M6a: protocol + screener + PRISMA report` v.v.
- Mô tả PR dán output các lệnh nghiệm thu mục H tương ứng pha đó.
- Kẹt ở bất kỳ điểm nào mơ hồ: **DỪNG và hỏi người duyệt trong PR**, không tự quyết vượt hợp đồng
  mục D. Đặc biệt: mọi cám dỗ "sửa core cho tiện" = vi phạm mục C.
