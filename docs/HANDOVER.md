# SR-Agent — Tài liệu bàn giao hệ thống

> **Mục đích tài liệu**: bàn giao toàn bộ thiết kế + hiện trạng cho nhóm để tiếp tục brainstorm.
> Đọc xong tài liệu này, bạn nắm được: hệ thống làm gì, tại sao thiết kế như vậy,
> cái gì đã chạy được, và những câu hỏi nào còn mở.
>
> **Trạng thái**: M0–M3 hoàn tất, 75 tests pass offline, nhánh `claude/sr-agent-pipeline-design-rqtctp`.

---

## 1. Tầm nhìn & Triết lý

**"AI truy xuất & lọc nhiễu — Con người duyệt & phân tích sâu."**

SR-Agent là pipeline ingestion tự động cho tài liệu khoa học **Computer Science**, chạy hoàn toàn local (MacBook Air M4 16GB, không phụ thuộc cloud LLM). Máy làm phần việc lặp lại và tốn thời gian: thu thập, gỡ trùng, chấm điểm, bóc tách cấu trúc, sinh câu hỏi phản biện. Con người chỉ làm phần việc có giá trị: **duyệt 5 tài liệu tốt nhất mỗi ngày** và phân tích sâu trên Notion.

Ba nguyên tắc xuyên suốt mọi quyết định thiết kế:

1. **Rẻ trước, đắt sau** — mọi bước tất định (regex, RapidFuzz, rubric thuần Python) chạy TRƯỚC bước LLM. Trên máy 16GB với model 7B, LLM là nút cổ chai thật sự; chỉ tài liệu đã qua gate rubric mới được tốn LLM.
2. **Tất định ở mọi tầng lọc** — ID regex tĩnh, threshold cố định, rubric là pure functions, LLM chạy temperature 0 + constrained decoding, output vẫn phải qua Pydantic lần cuối. Cùng input → cùng output, mọi quyết định lọc đều giải thích được.
3. **Con người là chốt chặn cuối** — không tài liệu nào tự động vào Notion. WIP limit 5/ngày chống quá tải người duyệt; TTL 72h tự giải phóng hàng tồn không ai đụng đến.

**Ràng buộc phạm vi** — ⚠️ ĐÃ THAY ĐỔI 2026-08-05, xem `docs/DECISIONS.md` mục 1:

> ~~Chỉ xử lý tài liệu Computer Science. Không có bất kỳ dữ liệu y sinh hoặc lâm sàng nào
> được xử lý trong toàn bộ dự án.~~ *(ràng buộc gốc từ pivot M1b — đã được chủ dự án gỡ)*

Phạm vi hiện hành: **được phép xử lý chủ đề y sinh/lâm sàng**. Ngữ liệu là **bài báo đã
xuất bản** — ranh giới còn giữ nguyên là **không xử lý dữ liệu bệnh nhân thật (PHI)**.

---

## 2. Cấu hình khóa cứng (M0–M2)

Tập trung toàn bộ tại `sr_agent/config.py` — các module khác **không** tự định nghĩa threshold riêng.

| Hằng số | Giá trị | Ý nghĩa |
|---|---|---|
| Nguồn A — IEEE Xplore | ID khớp `^\d{8}$` | CS Transactions, document ID 8 chữ số, tier 1 (peer-reviewed) |
| Nguồn B — arXiv | ID khớp `^arxiv:\d{4}\.\d{4,5}$` | preprint, tier 2 |
| `WIP_LIMIT` | 5 | tài liệu/ngày hiển thị ở QC UI, xếp theo điểm rubric giảm dần |
| `TTL_HOURS` | 72 | bản ghi staging không được Approve/Reject quá 72h → tự purge |
| `FUZZY_TITLE_THRESHOLD` | 93.0 | RapidFuzz ratio cho dedup mờ theo title |
| `RUBRIC_PASS_THRESHOLD` | 60.0 | dưới ngưỡng → loại trước khi tốn LLM |
| `MAX_RETRIES` | 4 | backoff 2/4/8/16s + jitter (tenacity) |
| `CIRCUIT_BREAKER_FAILURES` | 3 | N lỗi transient liên tiếp → skip nguồn trong batch |
| `OLLAMA_MODEL` | `qwen2.5:7b-instruct` | mặc định (bám JSON schema tốt nhất phân khúc ≤8B); `gemma3:4b` là profile nhanh |

Mọi nguồn dữ liệu khác **hoãn đến sau M2** để giữ staging đồng nhất tuyệt đối.

---

## 3. Kiến trúc — 6 trụ cột

```
Fetch (IEEE Xplore + arXiv)                 ── rẻ, tất định
  └─> D34 Dedup (exact ID → fuzzy title → authority tier)
        └─> Rubric Score (gate 60 điểm, JSON khai báo)
              └─> Structural Parser (Ollama 7B, structured output)   ── đắt, chạy cuối
                    └─> SQLite Staging (WIP 5/ngày · TTL 72h · DLQ)
                          └─> QC UI (Streamlit) ── Approve → Notion / Reject
```

> Trụ cột thứ 6 (SQLite staging) là bổ sung so với thiết kế ban đầu 5 trụ: không có state
> store thì không làm được WIP limit, TTL, DLQ, idempotency — nó là xương sống của cả 5 trụ kia.

### 3.1 Multi-source Router — `sr_agent/ingest/`

- `router.py` — `classify(raw_id)` phân loại bằng 2 regex tĩnh; ID không khớp → `UnsupportedFormat` (không đoán mò).
- `ieee.py` — gọi IEEE Xplore Metadata API (`ieeexploreapi.ieee.org/api/v1/search/articles`, cần `IEEE_API_KEY` miễn phí). Bài thiếu title hoặc article_number không đúng 8 chữ số → bỏ qua/`LayoutParseError`.
- `arxiv.py` — Atom feed qua `feedparser`; `normalize_arxiv_id()` quy mọi biến thể (URL, version `v2`, prefix) về `arxiv:YYMM.NNNNN`.
- `base.py` — retry dùng chung: 429 → `RateLimited` (đọc header `Retry-After`), 5xx → `NetworkError`, tenacity backoff 2/4/8/16s + jitter, tối đa 4 lần.

### 3.2 Dedup D34 — `sr_agent/dedup/d34.py`

3 tầng, chạy tuần tự, tất định 100%:

| Tầng | Cơ chế | Kết quả |
|---|---|---|
| 1. Exact ID | uid (`ieee:38111222` / `arxiv:2401.12345`) đã tồn tại? | `DUPLICATE_ID` → drop |
| 2. Fuzzy title | RapidFuzz `fuzz.ratio` trên title đã chuẩn hóa (NFKD, lowercase, bỏ dấu câu), cutoff **93** | `DUPLICATE_FUZZY` → drop + log event |
| 3. Authority tier | Trùng mờ nhưng bản mới tier cao hơn (IEEE=1 > arXiv=2) | `SUPERSEDES` → bản IEEE thay bản arXiv, **merge** metadata còn thiếu (abstract, authors, full_text), giữ uid cũ trong `alternate_uids` |

Ví dụ thực tế: preprint arXiv vào staging trước, bản chính thức IEEE về sau → bản IEEE thay thế nhưng không mất dữ liệu bản preprint đã có.

### 3.3 Rubric lọc tự động — `sr_agent/quality/rubric.py`

Rubric là **JSON khai báo** (có JSON Schema kèm theo để validate), engine là 5 pure functions trong `RULE_REGISTRY`:

| Tiêu chí | Trọng số | Rule |
|---|---|---|
| `source_authority` | 30 | tier 1 → điểm tối đa, tier 2 → một phần |
| `artifact_availability` | 25 | có link code repo / dataset trong abstract |
| `recency` | 20 | linear decay theo năm xuất bản |
| `abstract_completeness` | 15 | độ dài abstract trong khoảng lý tưởng |
| `metadata_integrity` | 10 | đủ các field bắt buộc |

Tổng ≥ **60** mới được đi tiếp vào LLM. Kết quả lưu breakdown từng tiêu chí + lý do — QC UI hiển thị để người duyệt hiểu vì sao tài liệu được xếp hạng cao.

### 3.4 Structural Parser — `sr_agent/parser/`

Xử lý 2 lớp, rẻ trước:

1. **Heuristic** (`heuristic.py`) — regex nhận diện heading (có số mục lục, ngắn, không kết thúc bằng dấu câu), map từ khóa (`introduction`→CONTEXT, `method*`→METHOD…) với confidence 1.0. Không tốn LLM.
2. **LLM** (`ollama_client.py` + `evaluator.py` + `structural.py`) — chỉ 2 việc:
   - **Structural CS Quality Analyzer**: trích `TechnicalMetadata` — `has_code_repo` (+ URL nguyên văn), `dataset_specification`, `evaluated_benchmarks`, `declared_limitations`. System prompt extract-only 8 luật: cấm suy diễn, không thấy bằng chứng → null/false/[].
   - **Sinh đúng 2 câu hỏi phản biện** (critique questions) cho phần Q&A trên Notion.

   Cả 2 gọi Ollama `/api/chat` với `format=<Pydantic JSON schema>` (constrained decoding — model **không thể** sinh sai schema), `temperature=0`. Output vẫn qua Pydantic validate lần cuối; fail → `SchemaValidationError` (Permanent, vào DLQ — retry cùng input ở temperature 0 là vô ích).

**Đa cấu trúc tài liệu** giải bằng Pydantic discriminated union: nguồn A → `IMRADSections` (Intro/Methods/Results/Discussion), nguồn B → `PAECSections` (Problem/Approach/Evaluation/Conclusion). Cả hai map về **4 vai trò chuẩn** (CONTEXT / METHOD / FINDINGS / IMPLICATIONS) qua `to_canonical()` — mọi module downstream (evaluator, Notion, UI) chỉ đọc vai trò chuẩn, không bao giờ đụng union trực tiếp. Thêm loại tài liệu mới = thêm 1 model + 1 mapping, downstream không đổi.

### 3.5 SQLite Staging Store — `sr_agent/store/staging.py`

State machine của một tài liệu:

```
FETCHED → DEDUPED → SCORED → PARSED → QUEUED ──Approve──> APPROVED (Notion thật)
                       │                 │  └──Approve───> APPROVED_LOCAL (dry-run)
                       │                 └────Reject─────> REJECTED
                       └── rubric < 60 ──────────────────> REJECTED
   (lỗi bất kỳ bước nào) ────────────────────────────────> DLQ
   (QUEUED quá 72h không ai đụng) ───────────────────────> EXPIRED (purge)
```

3 bảng: `documents` (toàn bộ Document JSON + status + `notion_page_id` + `last_interaction_at`), `dlq` (uid, error_type, error_detail, raw_path, retry_eligible), `events` (audit log mọi quyết định dedup/reject/approve).

- `get_wip_queue()` — top-5 theo rubric giảm dần (hàng đợi duyệt).
- `purge_expired()` — TTL 72h, **miễn trừ** APPROVED / APPROVED_LOCAL / REJECTED (giữ vĩnh viễn làm audit + làm nguồn cho dedup tương lai).

### 3.6 Notion Publisher — `sr_agent/publish/notion_page.py`

Trang Notion 3 phần cố định:

1. **Metadata** — đổ toàn bộ: uid, nguồn, tier, điểm rubric + breakdown, tech_meta (repo link, dataset, benchmarks, limitations).
2. **Q&A — Critical Review** — 2 câu hỏi phản biện dạng **toggle**, trong mỗi toggle 3 ô tick tĩnh `[CONFIRMED]` / `[INFERRED]` / `[UNKNOWN]` + chỗ ghi câu trả lời.
3. **My Notes** — heading + paragraph trống cho ghi chú cá nhân.

Tính chất quan trọng:
- **Idempotent** — đã có `notion_page_id` trong store thì Approve lần 2 không tạo trang trùng.
- **Nguyên tử** — toàn bộ blocks gửi trong 1 lệnh `pages.create` duy nhất (<100 blocks), không có trang dựng dở.
- **Dry-run** — thiếu `NOTION_TOKEN` → in JSON payload ra console, status `APPROVED_LOCAL`, không bao giờ crash. Cho phép chạy thử toàn pipeline mà chưa cần Notion.

### QC UI — `ui/app.py` (Streamlit)

Hàng đợi top-5, panel chi tiết (rubric breakdown, tech_meta, abstract, canonical sections), nút **Approve** (gọi publisher) / **Reject** (kèm lý do). TTL purge chạy mỗi lần load.

---

## 4. Xử lý lỗi & DLQ

Phân loại lỗi quyết định hành vi:

| Loại | Ví dụ | Hành vi |
|---|---|---|
| `TransientError` | `RateLimited` (429), `NetworkError` (5xx, timeout) | tenacity retry 4 lần backoff+jitter; hết lượt → DLQ `retry_eligible=1` |
| `PermanentError` | `LayoutParseError`, `SchemaValidationError`, `UnsupportedFormat` | DLQ ngay + quarantine raw payload `staging/quarantine/{uid}.raw` để debug tay |

Nguyên tắc cách ly:
- **Document-level isolation** — try/except quanh TỪNG bản ghi; 1 bản lỗi chỉ rơi vào DLQ (status document cũng hạ xuống `DLQ`), batch vẫn chạy tiếp.
- **Circuit breaker** — 3 lỗi transient liên tiếp từ 1 nguồn → skip nguồn đó trong batch hiện tại, nguồn kia vẫn chạy bình thường.
- **Suy giảm êm (graceful degradation)** — Ollama không chạy → pipeline tự chuyển chế độ tất định thuần (không LLM parse); thiếu Notion token → dry-run; thiếu IEEE key → báo rõ, arXiv vẫn chạy.
- `python -m sr_agent.pipeline retry-dlq` tái xử lý hàng `retry_eligible`.

---

## 5. Vận hành trên MacBook Air M4 (M3)

```bash
make setup                        # venv + deps + tạo .env
ollama pull qwen2.5:7b-instruct   # ~4.7GB Q4; gemma3:4b ~3.3GB (profile nhanh) — đều vừa 16GB
make doctor                       # preflight: phải "sẵn sàng chạy pipeline" mới đi tiếp
make run QUERY="efficient transformer inference"
make ui                           # duyệt top-5
make schedule QUERY="..."         # lịch 7:00 hằng ngày qua launchd
```

- **`doctor`** (`sr_agent/doctor.py`) phân 2 mức: check **BẮT BUỘC** (Python, deps, storage ghi được — fail → exit 1) và **TÙY CHỌN** (Ollama/model/IEEE/Notion — fail chỉ tắt tính năng tương ứng, kèm lệnh khắc phục từng mục).
- **launchd thay cron** — trên macOS cron **không chạy khi máy ngủ/gập nắp** (MacBook Air gần như luôn vậy lúc 7h sáng); LaunchAgent `com.sragent.daily` chạy bù ngay khi máy thức dậy. Installer tự chạy doctor trước, idempotent, XML-escape query an toàn.
- Benchmark chọn model: `make bench` so `qwen2.5:7b-instruct` vs `gemma3:4b` trên cùng fixture — đo tỉ lệ pass schema, độ đúng 5 trường trích xuất, giây/lần gọi. (Lưu ý đã kiểm chứng: "Gemma 4" chưa tồn tại; bản mới nhất là Gemma 3.)

---

## 6. Kiểm thử & Chất lượng

**75 tests, chạy hoàn toàn offline** — không cần mạng, Ollama, hay Notion:

| Vùng | Cách test |
|---|---|
| Ingest/Router | fixtures tĩnh `tests/fixtures/ieee_search.json` + `arxiv_atom.xml` |
| Ollama | `respx` mock HTTP — assert request mang đúng JSON schema + temperature 0 |
| Notion | `MagicMock` client — assert idempotency (`pages.create` gọi đúng 1 lần) |
| Pipeline/DLQ | fake fetchers giả lập 429, layout hỏng, circuit breaker |
| Doctor | mock `/api/tags`, monkeypatch env, storage không ghi được → exit 1 |

Đã chạy E2E dry-run: fetch giả → dedup → rubric 100 điểm → QUEUED → Approve → payload in console → `APPROVED_LOCAL`.

---

## 7. Hiện trạng bàn giao

| Sprint | Nội dung | Trạng thái |
|---|---|---|
| M0 | Config khóa cứng, Pydantic schemas đa cấu trúc, SQLite staging, error hierarchy | ✅ commit |
| M1 | IEEE + arXiv fetchers, router, D34 dedup, rubric, pipeline + DLQ | ✅ commit |
| M2 | Ollama structured parser, Notion idempotent publisher, Streamlit UI | ✅ commit |
| M3 | doctor CLI, launchd agent, Makefile, README vận hành macOS | ✅ commit |

Nhánh: `claude/sr-agent-pipeline-design-rqtctp`. Việc còn lại phía người dùng: điền `IEEE_API_KEY` / `NOTION_TOKEN` / `NOTION_PARENT_PAGE_ID` vào `.env`, pull model Ollama, chạy `make bench` trên máy thật để chốt model mặc định.

---

## 8. Chủ đề mở để nhóm brainstorm

Những quyết định **cố ý để lại** cho giai đoạn sau — mỗi mục kèm trade-off cần cân nhắc:

1. **Vòng phản hồi từ Approve/Reject về rubric.** Hiện rubric là hằng số. Có nên log lý do Reject thành dữ liệu huấn luyện để tinh chỉnh trọng số (thủ công hay tự động)? Rủi ro: mất tính tất định — nguyên tắc nền của hệ thống.
2. **Nguồn thứ 3+.** ACM DL, Semantic Scholar, DBLP, Papers With Code? Mỗi nguồn mới cần: quy tắc ID tĩnh, authority tier, mapping section. Kiến trúc đã sẵn (thêm fetcher + 1 dòng regex + 1 dòng tier) — câu hỏi là *chọn nguồn nào* và tier xếp thế nào.
3. **Tuning threshold trên dữ liệu thật.** Cutoff fuzzy 93, gate rubric 60, trọng số 5 tiêu chí — đều là giá trị khởi điểm hợp lý nhưng chưa calibrate. Đề xuất: chạy 2–4 tuần, xem tỉ lệ Reject-tại-UI (nếu cao → gate 60 quá lỏng) và số DUPLICATE_FUZZY sai (nếu có → 93 quá thấp).
4. **Chốt model LLM.** `make bench` trên M4 sẽ trả lời qwen2.5:7b vs gemma3:4b. Câu hỏi tiếp: có đáng chạy 2 model (4b sàng lọc nhanh, 7b phân tích kỹ tài liệu đã QUEUED)?
5. **Full-text PDF.** Hiện parser chỉ ăn abstract + metadata (API không trả full text). Thêm tầng tải + trích PDF (GROBID? marker?) là bước nhảy lớn về giá trị nhưng cũng về độ phức tạp và thời gian xử lý trên M4.
6. **Đồng bộ ngược từ Notion.** Người duyệt tick `[CONFIRMED]`/ghi notes trên Notion — có nên đọc ngược về SQLite để thống kê chất lượng câu hỏi phản biện LLM sinh ra?
7. **Multi-user.** Thiết kế hiện tại là single-user single-machine. Nếu nhóm cùng duyệt: cần queue phân công, tránh 2 người duyệt 1 bài — SQLite đủ hay cần chuyển Postgres?
8. **Câu hỏi phản biện sâu hơn.** Hiện 2 câu/bài từ abstract. Có nên cho người duyệt "hỏi tiếp" trong UI (chat với model về bài đang duyệt)?

---

*Tài liệu tự động sinh từ codebase tại commit M3. Chi tiết kỹ thuật từng module: đọc docstring đầu file tương ứng — mọi file đều có phần giải thích thiết kế bằng tiếng Việt.*
