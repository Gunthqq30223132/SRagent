# D30 — Kiến trúc Multi-Agent áp cơ chế Systematic Review (PRISMA + PICO) vào SR-Agent

> **Vai trò tài liệu**: bản thiết kế kiến trúc (không phải code). Người duyệt: chủ dự án.
> **Nền tảng**: `docs/HANDOVER.md` (6 trụ cột), `docs/specs/TS-D29-search-to-id.md` (cầu nối ngữ nghĩa M5).
> **Nguyên tắc bất di bất dịch kế thừa**: mù chủ đề của core, `router.py`/`config.py` không đổi,
> Ollama ≤ 8B, con người là chốt chặn cuối, mọi tầng lọc tất định ở mức tối đa có thể.

---

## 0. Quyết định phạm vi (D30-S1) — ✅ ĐÃ CHỐT 2026-08-05: MỞ PHẠM VI Y SINH

> **Trạng thái hiện hành**: chủ dự án đã gỡ ràng buộc CS-only. Xem `docs/DECISIONS.md` mục 1.
> Mục 1.3 (dialect PubMed/Cochrane) **đã được kích hoạt**; Embase loại vì cần license trả phí.
> Ranh giới còn giữ: ngữ liệu là bài báo đã xuất bản, **không xử lý dữ liệu bệnh nhân thật**.
>
> Phần văn bản dưới đây giữ nguyên làm dấu vết lý do — không còn là ràng buộc đang hiệu lực.

Đề bài nhắc PubMed / Cochrane / Embase. Ràng buộc đứng của dự án (đặt từ pivot M1b) là:
**"Không có bất kỳ dữ liệu y sinh hoặc lâm sàng nào được xử lý trong toàn bộ dự án này."**

Hai điều này mâu thuẫn trực diện. Cách giải quyết trong tài liệu này:

- **Thiết kế ở tầng phương pháp luận** — PRISMA/PICO là *quy trình*, không phải *dữ liệu*. Toàn bộ kiến trúc
  dưới đây được ánh xạ vào 2 nguồn CS đã khóa (IEEE, arXiv) và chạy được nguyên vẹn trong phạm vi CS-only.
- **Cú pháp truy vấn cho CSDL y khoa được đặc tả như tài liệu tham chiếu** (mục 1.3) — đúng yêu cầu đề bài —
  nhưng việc **kích hoạt** nguồn y sinh là quyết định phạm vi của chủ dự án, không phải quyết định kỹ thuật.
  (Ghi nhận thực tế: môi trường hiện đã có connector PubMed — kích hoạt rẻ về kỹ thuật; đắt về chính sách.)
- Có tiền lệ: đây chính là red-team item R2 của D29.

**Mặc định của tài liệu này: CS-only. Mọi ví dụ chạy được đều trên IEEE/arXiv.**

---

## 1. Phân tích & ánh xạ chiến thuật tìm kiếm

### 1.1 PICO → Input Schema

PICO nguyên bản là khung y khoa. Bản chuyển thể chuẩn cho khoa học máy tính là **PICOC**
(Kitchenham & Charters 2007, *Guidelines for performing Systematic Literature Reviews in Software
Engineering* — chính là văn bản đã "cấy" PRISMA/PICO sang CS, nên ta không phải tự chế):

| Yếu tố | Y khoa | Bản CS (PICOC) | Ví dụ (chủ đề RAG đã trial) |
|---|---|---|---|
| **P**opulation | nhóm bệnh nhân | hệ thống/đối tượng kỹ thuật | "LLM-based question-answering systems" |
| **I**ntervention | can thiệp điều trị | kỹ thuật/công nghệ được khảo sát | "retrieval-augmented generation" |
| **C**omparison | placebo/điều trị chuẩn | baseline so sánh (tùy chọn) | "fine-tuning only / closed-book LLM" |
| **O**utcome | kết cục lâm sàng | metric đo được | "factuality, hallucination rate, EM/F1" |
| (**C**ontext) | — | bối cảnh triển khai (tùy chọn) | "production systems, on-device" |

**Input Schema** (Pydantic, tầng ngoại vi `tools/` — cùng chỗ với `topic_run.py`, KHÔNG vào core):

```python
class PicoConcept(BaseModel):
    concept: str                 # cụm chính, tiếng Anh
    synonyms: list[str] = []     # biến thể/viết tắt — OR trong cùng khối
    required: bool = True        # False = không đưa vào query, chỉ dùng khi screening

class ReviewProtocol(BaseModel):
    """Giao thức SR — BẤT BIẾN sau khi chốt (tương đương đăng ký PROSPERO).
    File JSON nằm cạnh profile query; mọi agent chỉ ĐỌC, không agent nào được sửa."""
    topic_vi: str                        # ý định gốc của người dùng (chỉ là nhãn/audit)
    population: PicoConcept
    intervention: PicoConcept
    comparison: PicoConcept | None = None
    outcome: PicoConcept | None = None
    year_range: tuple[int, int] | None = None
    languages: list[str] = ["en"]
    study_types_excluded: list[str] = ["editorial", "poster", "thesis"]
    exclusion_criteria: list[str]        # ID tham chiếu bộ tiêu chí mục 3.1
```

Chuyển ngôn ngữ tự nhiên → `ReviewProtocol`: chính là điểm mà M5 đã chính thức hóa (`--expand` qua
`OllamaClient.generate_structured`, temperature 0, suy giảm êm khi Ollama tắt). Khác biệt duy nhất:
schema đầu ra từ `list[str]` phẳng nâng thành PICO có cấu trúc. **Người dùng duyệt và chốt protocol
trước khi tìm kiếm** — LLM chỉ đề xuất bản nháp. Đây là ánh xạ 1-1 của nguyên tắc SR "protocol trước,
tìm kiếm sau" (chống HARKing/cherry-picking) vào triết lý sẵn có "AI truy xuất — Con người duyệt".

### 1.2 PICO → chuỗi truy vấn (quy tắc dựng query tất định)

Thuật toán dựng query là **pure function** trên protocol (không LLM ở bước này):

1. **Trong một khối PICO**: nối synonyms bằng `OR`, bọc ngoặc. `("retrieval augmented generation" OR "RAG")`
2. **Giữa các khối**: nối bằng `AND`. Thực hành chuẩn của thủ thư y khoa: **chỉ đưa P AND I vào query**;
   C và O gần như không bao giờ xuất hiện ổn định trong title/abstract → đưa vào query làm recall sập.
   C/O dùng ở vòng screening (mục 2), không dùng ở vòng tìm.
3. **Giới hạn (year/language)**: dùng filter của từng CSDL, không nhét vào chuỗi boolean.
4. **Dialect từng nguồn nằm trong profile khai báo** — đúng cơ chế `tools/profiles/*.json` +
   `ProfiledFetcher` đã có từ M5 (nguyên lý Gusenbauer: mỗi CSDL một năng lực cú pháp khác nhau).

Profile mở rộng (minh họa, CS-only chạy được ngay):

```json
{
  "sources": {
    "ieee":  { "templates": ["(\"{P}\") AND (\"{I}\")"] },
    "arxiv": { "templates": ["\"{I}\" \"{P}\""],
               "note": "ArxivFetcher.search tự tiền tố all: — template chỉ là cụm từ (phát hiện M5)" }
  }
}
```

### 1.3 Tham chiếu dialect CSDL y khoa (KHÔNG kích hoạt — chờ D30-S1)

Đặc tả để trả lời trọn đề bài; cũng là bằng chứng vì sao query phải per-source:

| CSDL | Từ vựng có kiểm soát | Cú pháp field | Ví dụ khối I |
|---|---|---|---|
| PubMed | **MeSH** | `[mh]`, `[tiab]`, boolean | `("machine learning"[mh] OR "deep learning"[tiab])` |
| Cochrane CENTRAL | MeSH | `ti,ab,kw`, toán tử `NEXT/NEAR` | `[mh "machine learning"] OR (deep NEXT learning):ti,ab,kw` |
| Embase | **Emtree** (khác MeSH!) | `/exp` (explode), `:ti,ab` | `'machine learning'/exp OR 'deep learning':ti,ab` |

Ba điểm kiến trúc rút ra (áp dụng được ngay cho CS): (a) mỗi nguồn một *từ vựng có kiểm soát* riêng —
tương đương IEEE Thesaurus vs arXiv category (`cat:cs.CL`); (b) bản dịch concept→syntax phải là dữ liệu
khai báo (profile), không phải code; (c) query dùng cho CSDL nào phải được lưu lại nguyên văn cho CSDL đó —
PRISMA 2020 yêu cầu báo cáo full search string per database → trường `expansion.queries` của manifest M5
đã đáp ứng sẵn.

### 1.4 Giải cấu trúc PRISMA 4 giai đoạn → ánh xạ vào pipeline

Phát hiện quan trọng nhất của bản phân tích: **SR-Agent hiện tại đã LÀ một cỗ máy PRISMA khuyết 2 vị trí**.
Ánh xạ từng giai đoạn:

| PRISMA | Bản chất | Trong SR-Agent hiện tại | Trạng thái |
|---|---|---|---|
| **1. Identification** | tìm trên n CSDL, gỡ trùng | `tools/topic_run.py` (query per-source, provenance) → fetchers → **D34 dedup** (exact ID → fuzzy 93 → authority tier) | ✅ ĐÃ CÓ — D34 chính là hộp "duplicates removed" của PRISMA, tất định 100% |
| **2. Screening** (title/abstract) | 2 người duyệt độc lập loại theo tiêu chí | Rubric gate 60 (tất định) — nhưng rubric đo *chất lượng*, KHÔNG đo *tính hợp lệ so với câu hỏi nghiên cứu* | 🟡 KHUYẾT — cần cặp Screening Agent (mục 2.2), đặt SAU rubric |
| **3. Eligibility** (full-text) | đọc toàn văn, loại kèm lý do ghi sổ | StructuralParser đã tách section + trích metadata, nhưng không có verdict include/exclude theo protocol | 🟡 KHUYẾT — Eligibility Agent (mục 2.3), chỉ chạy trên doc có `full_text` |
| **4. Included** | danh sách cuối vào tổng hợp | QC UI (WIP 5, người approve) → Notion | ✅ ĐÃ CÓ — và PRISMA cũng yêu cầu con người là người chốt |

Số liệu cho **sơ đồ dòng chảy PRISMA** (records identified → duplicates removed → screened → excluded
(n, theo lý do) → full-text assessed → excluded with reasons → included) suy được **hoàn toàn từ dữ
liệu sẵn có**: bảng `runs` (report_json đã có fetched/deduped/rejected/queued), bảng `events`, bảng
`dlq`, cộng bảng sidecar `screening` mới (mục 2.5). Đề xuất subcommand ngoại vi
`tools/prisma_report.py --run <id>` in sơ đồ dạng text/markdown — thuần SELECT, zero-touch core.

---

## 2. Kiến trúc Multi-Agent

### 2.1 Nguyên tắc nền (trước khi kể tên agent)

1. **"Agent" ở đây = vai trò + prompt + schema đầu ra trên CÙNG một Ollama local**, chạy tuần tự
   (máy 16GB không chạy song song 2 model 7B). Không thêm framework đa tác tử nào — orchestration là
   vòng lặp Python tất định, đúng tinh thần codebase.
2. **Tầng nào tất định được thì không giao cho LLM.** Trong danh sách dưới, Identification và Quality
   gate là code thuần (đã có); LLM chỉ đứng ở đúng 3 chỗ mà bản chất công việc là đọc-hiểu:
   screening, eligibility, extraction.
3. **Mọi thứ là lớp additive** — module ngoại vi + bảng SQLite sidecar + tab UI, đúng pattern M4/M5.
   `DocStatus`, class `Pipeline`, `router.py`, `config.py`: không đổi một dòng.

### 2.2 Danh sách agent, vai trò và ranh giới

| # | Agent | Loại | Vai trò | Ranh giới cứng (được/không được) |
|---|---|---|---|---|
| A1 | **Protocol Builder** (Query Builder) | LLM đề xuất + người chốt | NL tiếng Việt → nháp `ReviewProtocol`; render query per-source từ protocol (pure function) | CHỈ ghi file protocol/manifest ở `tools/`; không chạm DB; query cuối do người duyệt |
| A2 | **Identification** | tất định (đã có) | fetch theo query profile, D34 dedup, provenance | chính là fetchers + `d34.py` — cấm thay bằng LLM |
| A3a | **Screener-α** | LLM | verdict INCLUDE/EXCLUDE trên title+abstract theo protocol | chỉ đọc title/abstract/protocol; KHÔNG thấy điểm rubric, KHÔNG thấy verdict của A3b |
| A3b | **Screener-β** | LLM | như A3a, cấu hình độc lập (mục 2.3) | như A3a; hai screener không chia sẻ bất kỳ context nào |
| A4 | **Tie-breaker** | LLM | phân xử khi A3a ≠ A3b | chỉ nhận: doc + protocol + 2 bản (criterion, quote) mâu thuẫn; verdict không chắc → BẮT BUỘC đẩy người |
| A5 | **Eligibility** (full-text) | LLM | duyệt toàn văn theo bộ EF (mục 3.1), chỉ doc có `full_text` | doc không có full_text (IEEE metadata-only) → gắn nhãn `abstract_only=true`, KHÔNG giả vờ đã đọc toàn văn |
| A6 | **Data Extraction** | LLM + verifier tất định | trích trường dữ liệu kèm exact quote (mục 3.2) | field không có quote khớp verbatim → field bị hủy, không thương lượng |
| A7 | **Quality Assessment** | tất định (đã có) + LLM tư vấn | rubric 5 tiêu chí giữ nguyên làm gate; LLM chỉ sinh ghi chú risk-of-bias *tham khảo* cho người duyệt | LLM QA KHÔNG có quyền đổi điểm rubric, không có quyền loại doc |
| — | **Con người** | — | giai đoạn Included: approve/reject trong QC UI | chốt chặn cuối, giữ nguyên WIP 5 / TTL 72h |

Vị trí trong dòng chảy (giữ "rẻ trước, đắt sau" — screening LLM đặt SAU gate rubric để LLM chỉ đụng
hàng đã qua lọc rẻ):

```
A1 protocol → A2 fetch+dedup → rubric gate 60 (tất định)
  → A3a ∥ A3b screening (title/abstract) ──┬─ đồng thuận EXCLUDE → REJECTED (lý do ghi sổ)
                                           ├─ đồng thuận INCLUDE → A5 eligibility (nếu có full_text)
                                           └─ bất đồng → A4 tie-breaker → (vẫn kẹt) → người
  → A6 extraction có minh chứng → QUEUED → người duyệt (Included) → Notion
```

### 2.3 Cross-check độc lập giữa 2 Screening Agent — và cái bẫy phải né

**Cái bẫy (red-team tự khai, quan trọng nhất tài liệu):** toàn hệ chạy temperature 0. Nếu A3a và A3b
là *cùng model + cùng prompt*, hai đầu ra **giống hệt nhau theo định nghĩa** — "hai người duyệt độc lập"
thành sân khấu kịch, Cohen's κ = 1.0 vô nghĩa. Độc lập phải đến từ **đa dạng cấu hình có chủ đích**:

- **Trục 1 — khác model**: A3a = `qwen2.5:7b-instruct`, A3b = `gemma3:4b` (cả hai đã trong tầm máy và
  đã có sẵn harness so sánh `tests/bench_parser.py`). Chạy tuần tự, không cần RAM gấp đôi.
- **Trục 2 — khác khung lập luận** (mô phỏng đúng thiên kiến lệch nhau của 2 reviewer người):
  - A3a mang khung **thiên-giữ**: "INCLUDE trừ khi chỉ ra được một tiêu chí loại trừ áp dụng rõ ràng,
    kèm quote" (burden of proof nằm ở việc loại).
  - A3b mang khung **thiên-loại**: đi qua checklist từng tiêu chí ET như công tố viên, tiêu chí nào
    dính phải quote được bằng chứng.
- Khuyến nghị dùng **cả hai trục cùng lúc**. Đo **Cohen's κ mỗi batch**, ghi vào `runs.report_json`;
  κ < 0.6 → rule alert mới `SCREEN_DISAGREEMENT` cắm thẳng vào máy trạng thái alert M4 (kế thừa
  chống alarm-fatigue: chỉ notify khi chuyển trạng thái). κ thấp kéo dài nghĩa là protocol mơ hồ —
  tín hiệu để con người sửa *protocol*, không phải sửa agent.

**Hợp đồng đầu ra của mỗi screener** (structured output, Pydantic):

```python
class ScreenVerdict(BaseModel):
    verdict: Literal["include", "exclude"]
    criterion_id: str | None      # BẮT BUỘC khi exclude (ET1..ET7, mục 3.1)
    evidence_quote: str | None    # BẮT BUỘC khi exclude — trích verbatim từ title/abstract
    confidence: Literal["high", "low"]
```

Verdict `exclude` thiếu criterion/quote, hoặc quote không khớp verbatim (verifier mục 3.2) →
**verdict vô hiệu → tính là abstain → xử lý như bất đồng**. Không bao giờ "sửa giúp" đầu ra của agent.

### 2.4 Giao thức xử lý bất đồng (discrepancy protocol)

Mô phỏng đúng SR thật (2 reviewer bất đồng → thảo luận → reviewer thứ 3 phân xử → vẫn kẹt thì
nguyên tắc bảo thủ):

1. **A3a = A3b**: chốt theo đồng thuận. EXCLUDE → status `REJECTED` (tái dùng trạng thái sẵn có,
   lý do + quote ghi bảng sidecar — audit vĩnh viễn đúng triết lý hiện hành). INCLUDE → đi tiếp.
2. **A3a ≠ A3b** → **A4 Tie-breaker** (model thứ ba về cấu hình: dùng qwen nhưng prompt trọng tài,
   nhận cả hai bộ (criterion, quote) mâu thuẫn — KHÔNG nhận nhãn "α nói/β nói" để tránh thiên vị
   theo tên): phải chọn một phía và chỉ ra quote quyết định.
3. **Tie-breaker trả `confidence="low"` hoặc đầu ra không qua validation** → **nguyên tắc bảo thủ
   của SR ở vòng title/abstract: nghi ngờ thì GIỮ** — doc đi tiếp vào hàng đợi với huy hiệu 🔶
   "Screening bất đồng — cần người phân xử" trong QC UI (cùng cơ chế badge ⚠️ degraded của M4).
   Người duyệt là reviewer thứ 3 thật sự. KHÔNG bao giờ âm thầm loại một doc mà 1/2 agent muốn giữ.
4. Mọi bước 1–3 ghi `screening` sidecar (mục 2.5) — tỷ lệ bất đồng, tỷ lệ tie-breaker giải quyết
   được, tỷ lệ đẩy người = 3 chỉ số sức khỏe mới của tab 🩺.

### 2.5 Chạm hệ thống hiện tại ở đâu (tổng kết additive)

| Thành phần mới | Loại | Ghi chú |
|---|---|---|
| `tools/protocol_build.py` + schema `ReviewProtocol` | ngoại vi | mở rộng tự nhiên của `topic_run.py --expand` |
| `tools/screen_run.py` (A3a/A3b/A4 orchestration) | ngoại vi | đọc doc QUEUED/SCORED từ store, ghi sidecar |
| bảng `screening(uid, agent, model, verdict, criterion_id, quote, confidence, created_at)` | DDL additive | pattern y hệt `runs`/`alerts` của M4 |
| rule alert `SCREEN_DISAGREEMENT` (κ < 0.6) | additive | cắm vào `monitor/alerts.py` như 5 rule sẵn có |
| badge 🔶 + 3 metric screening trong UI | additive | pattern badge ⚠️ M4 |
| `tools/prisma_report.py` | ngoại vi | SELECT thuần → sơ đồ dòng chảy PRISMA |
| `sr_agent/` core | **0 file đổi** | tiêu chí nghiệm thu giống M5: `git diff sr_agent/ingest/ sr_agent/pipeline.py sr_agent/config.py` rỗng (trừ DDL additive trong `store/staging.py` + rule alert additive trong `monitor/alerts.py`) |

---

## 3. Quản lý chất lượng & giảm thiểu hallucination

### 3.1 Bộ tiêu chí loại trừ (Exclusion Criteria) — hai vòng

Tiêu chí là **dữ liệu trong protocol** (agent đọc, không tự chế thêm). Mỗi verdict exclude phải trỏ
đúng 1 mã tiêu chí. Bộ mặc định cho phạm vi CS:

**Vòng Title/Abstract (ET — dùng bởi A3a/A3b/A4):**

| Mã | Tiêu chí | Ghi chú vận hành |
|---|---|---|
| ET1 | Sai Population — đối tượng nghiên cứu không khớp `protocol.population` | quote phần title/abstract mô tả đối tượng |
| ET2 | Không có Intervention — kỹ thuật khảo sát không xuất hiện/chỉ được nhắc lướt qua | phân biệt "paper VỀ RAG" với "paper NHẮC ĐẾN RAG" |
| ET3 | Loại xuất bản ngoài phạm vi — editorial/opinion/poster/thesis/tutorial slide | theo `study_types_excluded` |
| ET4 | Ngôn ngữ ngoài `protocol.languages` | |
| ET5 | Ngoài `year_range` | thực tế nên lọc tất định ở query filter trước; ET5 chỉ là lưới an toàn |
| ET6 | Bản trùng/bản cũ của công trình đã có trong tập | **đã do D34 xử lý tất định** — screener chỉ bắt trùng ngữ nghĩa lọt lưới fuzzy 93 (cùng thí nghiệm, khác title) |
| ET7 | Loại nghiên cứu không khớp protocol (vd protocol yêu cầu primary study mà đây là survey, hoặc ngược lại) | protocol phải khai rõ chiều nào |

**Vòng Full-text (EF — dùng bởi A5; chỉ doc có `full_text`):**

| Mã | Tiêu chí | Ghi chú |
|---|---|---|
| EF1 | Không có đánh giá thực nghiệm/metrics trong khi protocol yêu cầu Outcome đo được | đối chiếu `protocol.outcome` |
| EF2 | Outcome quan tâm không được báo cáo (có thí nghiệm nhưng đo thứ khác) | |
| EF3 | Full-text không truy xuất được | KHÔNG phải exclude ngữ nghĩa — hộp riêng "not retrieved" trong sơ đồ PRISMA; với IEEE metadata-only: gắn `abstract_only=true` và để người quyết |
| EF4 | Trùng dữ liệu — cùng nhóm tác giả, cùng bộ thí nghiệm đã có trong tập (salami slicing) | tie vào `alternate_uids` sẵn có |

Quy tắc chung không thương lượng: **EXCLUDE nào cũng phải kèm (mã tiêu chí, exact quote)**;
INCLUDE phải kèm xác nhận đã rà đủ danh sách tiêu chí. Thiếu → verdict vô hiệu (mục 2.3).

### 3.2 Trích xuất dữ liệu có minh chứng — "LLM đề xuất, verifier tất định định đoạt"

Nâng cấp học thuyết extract-only hiện có của `TechnicalMetadata` (docstring: *"LLM trích xuất
NGHIÊM NGẶT, không suy diễn"*) từ **quy ước trong prompt** thành **cơ chế cưỡng chế bằng code**:

```python
class EvidencedField(BaseModel):
    value: str
    quote: str          # trích VERBATIM từ văn bản nguồn — hợp đồng chống hallucination
    section: str        # section id nơi quote nằm (context/method/result/...)

class EvidencedExtraction(BaseModel):
    fields: dict[str, EvidencedField]   # has_code_repo, dataset_spec, baselines, metrics...
```

**Verifier tất định** (pure function, không LLM — đúng triết lý "tất định ở mọi tầng lọc"):

1. Chuẩn hóa nhẹ hai phía (case-fold, gộp whitespace, thống nhất dấu nháy/gạch) — KHÔNG fuzzy match,
   KHÔNG chỉnh sửa quote.
2. `quote` chuẩn hóa phải là **substring đúng nguyên văn** của văn bản nguồn chuẩn hóa
   (abstract hoặc section được khai trong `section`).
3. Khớp → field được nhận, lưu kèm quote + vị trí. Không khớp → **field bị hủy** và ghi event
   `EXTRACT_UNVERIFIED` — doc mang cờ suy giảm, tái dùng nguyên cơ chế M4 (badge ⚠️ + `enrich`
   thử lại ban đêm). Không bao giờ giữ value mà vứt quote.
4. **Grounding score** = số field có quote khớp / tổng field — hiển thị cạnh điểm rubric trong QC UI.
   Người duyệt thấy từng quote ngay dưới từng giá trị → đối chiếu bằng mắt trong một lần nhìn.

Cơ chế này đóng cả hai cửa hallucination: (a) bịa giá trị — không có quote thì không có field;
(b) bịa quote — substring check verbatim làm quote bịa không thể khớp. Cửa còn lại (quote đúng chữ
nhưng sai ngữ cảnh) là việc của người duyệt — và vì quote + section hiển thị sẵn, chi phí kiểm tra
của con người giảm từ "đọc lại cả paper" xuống "đọc 1 câu trong đúng section".

### 3.3 Tie vào giám sát M4

- κ mỗi batch + tỷ lệ verdict vô hiệu + grounding score trung bình → thêm vào `HealthSnapshot`.
- `SCREEN_DISAGREEMENT` (κ < 0.6) và `EXTRACT_UNGROUNDED` (grounding trung bình < 0.8 trong 24h)
  là 2 rule alert mới — cùng máy trạng thái, cùng kỷ luật chỉ-notify-khi-chuyển-trạng-thái.

---

## 4. Lộ trình hiện thực đề xuất (M6, theo pha — mỗi pha tự đứng được)

| Pha | Nội dung | Rủi ro | Phụ thuộc |
|---|---|---|---|
| M6a | `ReviewProtocol` + render query từ PICO + bảng `screening` + **1** screening agent + `prisma_report` | thấp | không |
| M6b | Screener thứ 2 (khác model + khác khung) + κ + Tie-breaker + badge 🔶 + alert mới | vừa | M6a; cần bench gemma3:4b trên máy thật |
| M6c | `EvidencedExtraction` + verifier + grounding score trong UI | vừa | không (song song M6b được) |
| M6d | Profile PubMed/Cochrane/Embase | **chặn bởi D30-S1** — quyết định phạm vi của chủ dự án | M6a |

Phân công phù hợp tiền lệ D29/M5: M6a/M6c nhiều bẫy kiến trúc — làm in-house; M6b phần cơ khí
(prompt thứ hai, bảng, badge) spec-able cho Antygravity sau khi M6a chốt hợp đồng dữ liệu.

---

## 5. Phụ lục nghiệm thu

### 5.1 Checklist nhị phân

| # | Yêu cầu đề bài | Đáp ứng | Vị trí |
|---|---|---|---|
| 1 | PICO ngôn ngữ tự nhiên → Input Schema | ✅ | §1.1 `ReviewProtocol` |
| 2 | PICO → search syntax tối ưu, kể cả PubMed/Cochrane/Embase | ✅ (đặc tả; kích hoạt chờ D30-S1) | §1.2, §1.3 |
| 3 | Giải cấu trúc PRISMA 4 giai đoạn → agent/task trong pipeline | ✅ | §1.4 |
| 4 | Danh sách agent cốt lõi + vai trò + ranh giới | ✅ | §2.2 |
| 5 | Cross-check ≥2 Screening Agent độc lập | ✅ (kèm phân tích bẫy giả-độc-lập ở temp 0) | §2.3 |
| 6 | Tie-breaker giải quyết discrepancy | ✅ | §2.4 |
| 7 | Exclusion criteria nghiêm ngặt 2 vòng | ✅ | §3.1 |
| 8 | Extraction bắt buộc Exact Quote đối chiếu được | ✅ (verifier tất định, không chỉ prompt) | §3.2 |
| 9 | Không phá mù chủ đề / không đổi `router.py`, core hard-code | ✅ | §2.5 (0 file core) |
| 10 | Không xuất code thực thi | ✅ (chỉ schema/hợp đồng minh họa) | toàn văn |

### 5.2 Red-team tự phản biện

- **R1 — Giả độc lập ở temperature 0** (nghiêm trọng nhất): 2 screener cùng model + cùng prompt cho
  κ = 1.0 rỗng nghĩa. Thiết kế đã cưỡng chế đa dạng 2 trục (§2.3), nhưng ngay cả khác model, hai LLM
  cùng huấn luyện trên phân phối tương tự vẫn tương quan lỗi cao hơn 2 con người — **κ của cặp agent
  không so sánh được trực tiếp với κ 0.6–0.8 của reviewer người trong văn liệu SR**. Phải hiệu chuẩn
  ngưỡng trên dữ liệu thật của chính hệ.
- **R2 — Phạm vi y sinh**: đề bài nhắc CSDL y khoa; ràng buộc dự án cấm dữ liệu y sinh. Đã cô lập
  thành quyết định D30-S1 (§0) — mọi thứ hiện thực được đều CS-only.
- **R3 — Quote đúng chữ, sai ngữ cảnh**: verifier chỉ chứng minh quote *tồn tại*, không chứng minh
  quote *ủng hộ* value. Giảm thiểu: hiển thị section + quote cho người duyệt; không nhận quote từ
  section khác với trường khai báo. Không có cách đóng hoàn toàn cửa này bằng máy — và không nên
  giả vờ là có.
- **R4 — Chi phí trên máy 16GB**: screening kép + tie-breaker ≈ 2–3 lần gọi LLM/doc *sau* gate rubric.
  Với WIP 5/ngày và batch ~20 doc, bounded (~40–60 call/batch, vài phút với 7B) — nhưng nếu nới
  `max_results`, chi phí tuyến tính theo doc. Trần cứng phải nằm trong config của tool ngoại vi.
- **R5 — Eligibility "toàn văn" trên nguồn không có toàn văn**: IEEE trả metadata-only → A5 với các
  doc này thực chất chỉ là vòng 2 trên abstract. Hệ phải nói thật điều đó (`abstract_only=true` trong
  sổ sách + sơ đồ PRISMA) thay vì báo cáo như đã thẩm định full-text.
- **R6 — Rubric ≠ Screening**: giữ rubric làm gate trước screening nghĩa là paper hợp lệ về câu hỏi
  nghiên cứu nhưng điểm rubric thấp (paper kinh điển không repo — đúng thiên kiến đã đo được ở 2 lần
  trial: Lewis 2020 bị loại 49.63) sẽ **không bao giờ tới vòng screening**. Trong SR thật, đây là lỗi
  phương pháp (thiếu sót nghiên cứu hợp lệ = selection bias). Kéo lại brainstorm topic #3 (hiệu chuẩn
  ngưỡng/trọng số rubric) thành **tiền đề của M6**, hoặc cho phép protocol hạ gate rubric riêng cho
  chế độ SR.
