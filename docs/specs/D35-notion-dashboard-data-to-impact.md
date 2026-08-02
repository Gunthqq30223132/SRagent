# D35 — Notion Dashboard Schema & Data-to-Impact Pipeline

> **Trạng thái**: thiết kế (chưa implement). Nhánh `claude/arxiv-notion-pipeline-optimization-dxs67q`.
> **Phạm vi**: lớp xuất bản (publish layer) của SR-Agent + `notion-mcp-server` + quy trình chuyển hóa tri thức sang AnesthOS / Agent Harnessing / PKM.
> **Không đụng tới**: core pipeline (`ingest/`, `dedup/`, `quality/rubric.py`, `store/`) — mọi thay đổi nằm ở tầng ngoại vi, đúng nguyên tắc D29/M5.

---

## 0. Chẩn đoán: ba vấn đề, một nguyên nhân gốc

Ba vấn đề trong đề bài (UI vỡ định dạng / không có Properties / không tự động hóa được) **không phải ba vấn đề độc lập**. Chúng là ba triệu chứng của cùng một nguyên nhân: **bề mặt tool của `notion-mcp-server` quá hẹp so với Notion API.**

Bằng chứng nguyên văn từ `notion-mcp-server/index.js`:

| Dòng | Code hiện tại | Hệ quả |
|---|---|---|
| 161–173 | `notion_append_block_children` hardcode `children: [{ type: 'paragraph', paragraph: { rich_text: [{ text: { content: args.text }}]}}]` | **Vấn đề 1.** Mọi nội dung gửi lên đều bị bọc vào **đúng 1 block paragraph**. Markdown `##`, `-`, `>` chỉ là ký tự thường bên trong paragraph đó. Không có prompt nào sửa được điều này. |
| 184–194 | `notion_create_page` chỉ set `properties = { Name: { title: [...] } }` | **Vấn đề 2.** Không thể ghi bất kỳ property nào ngoài tiêu đề ⇒ metadata buộc phải nhét vào body ⇒ không Filter/Sort/Group được. |
| 175 | `notion_query_database` chỉ truyền `database_id` + `page_size: 10` | **Vấn đề 3.** Không có `filter`/`sorts` ⇒ không truy vấn được "các bài P0 chưa xử lý" ⇒ không có action trigger, không có auto-archive. |

Kiểm chứng trên dữ liệu thật — trang `2606.01435` trong DB `SR-Agent Dashboard` hiện có nội dung:

```
## Metadata<br>- arXiv ID: 2606.01435<br>- Tags: [Tag A: ...]<br>...
```

Toàn bộ là **text thô trong paragraph**, đúng như dự đoán từ code. Và data source `collection://39a64a33-c832-80e4-bd8a-000bc09809c7` hiện có **duy nhất 1 property: `Name` (title)**.

**Kết luận thứ tự thi công**: sửa `index.js` là **bước chặn (blocking step)**. Làm schema đẹp hay quy trình hay đến mấy mà không mở rộng tool schema thì không ghi được xuống Notion. Mọi việc khác phụ thuộc vào bước này.

---

## PHẦN 1 — Notion Database Schema & Naming Rules

### 1.1 Bộ Properties

Nguyên tắc chọn: **mỗi property phải phục vụ ít nhất một View hoặc một Filter tự động**. Property không dùng để lọc/nhóm thì để trong body — tránh phình schema.

#### Nhóm CORE (P0 — làm ngay, 11 property)

| Property | Kiểu | Options / Ràng buộc | Vì sao cần |
|---|---|---|---|
| `Name` | Title | Xem §1.2 | Định danh người đọc |
| `SR UID` | Text | `arxiv:YYMM.NNNNN` \| `ieee:NNNNNNNN` | **Khóa idempotency.** Khớp `uid` trong SQLite `documents`. Trước khi tạo trang: query theo property này; có rồi thì update, không tạo trùng. Đây là cột quan trọng nhất về mặt kỹ thuật. |
| `arXiv ID` | Text | `\d{4}\.\d{4,5}` | Tra cứu nhanh bằng con người, hiển thị gọn |
| `Source` | Select | `arXiv` · `IEEE` · `ACM` · `Manual` | Nhóm theo độ tin cậy nguồn |
| `Link` | URL | — | Mở bài gốc 1 click |
| `Published` | Date | ISO date | Filter "6 tháng gần nhất" |
| `Relevance` | Select | `P0 — Cấp thiết` · `P1 — Quan trọng` · `P2 — Tham khảo` · `P3 — Lưu trữ` | Trục ưu tiên chính (§3.2) |
| `Target Project` | Multi-select | `AnesthOS` · `Agent Harnessing` · `PKM Vault` · `SR-Agent` · `Chưa gắn` | Trục nhóm chính của Board view |
| `Core Tags` | Multi-select | Từ vựng đóng, §1.3 | Tìm theo chủ đề kỹ thuật |
| `Status` | Status | `New` → `Analyzed` → `PoC Proposed` → `Integrated`; nhánh phụ: `Rejected` · `Archived` | Vòng đời — trục của Kanban |
| `Rubric Score` | Number | 0–100 | Điểm từ `quality/rubric.py`, để sort trong hàng đợi |

#### Nhóm EXTENDED (P1 — thêm sau khi CORE chạy ổn, 5 property)

| Property | Kiểu | Options | Vì sao cần |
|---|---|---|---|
| `Impact Type` | Select | `Guardrail` · `Architecture` · `Algorithm` · `Eval/Benchmark` · `Ops/Tooling` | Trả lời "bài này biến thành **loại** hành động gì" — bắt buộc phải chọn thì mới lên được `Analyzed` |
| `Evidence Grade` | Select | `Peer-reviewed` · `Preprint + benchmark` · `Preprint only` · `Position paper` | **Bắt buộc cho AnesthOS.** Preprint không phải bằng chứng lâm sàng. |
| `Clinical Gate` | Select | `N/A` · `Engineering-only` · `Cần thẩm định lâm sàng` · `Blocked` | Chốt an toàn, xem §1.4 |
| `Code Repo` | URL | — | Suy ra từ `tech_meta.code_repo_url`; có repo ⇒ chi phí PoC thấp hơn hẳn |
| `PoC` | Relation → `PoC Backlog` | — | **Đóng vòng lặp tri thức → hành động.** Không có cột này thì hệ thống vẫn là nghĩa địa dữ liệu. |

> **Lưu ý API**: Notion API **không tạo được** property kiểu `status` (chỉ `select` mới tạo được qua API). ⇒ Tạo bộ property này **một lần bằng UI Notion** (khuyến nghị, giữ được kiểu `Status` với UI Kanban đẹp), hoặc tạo qua official connector rồi dùng `select` thay cho `status`. Sau khi tạo xong, `notion-mcp-server` chỉ cần **ghi giá trị**, không cần tạo property.

### 1.2 Naming Convention

**Hiện trạng**: `2606.01435 - Don't Ask the LLM to Track Freshness: A Deterministic Recipe for Memory Conflict Resolution` (118 ký tự, ID đứng đầu).

Ba nhược điểm: (a) 10 ký tự đầu tiên — phần đắt giá nhất trong cột hẹp, sidebar, backlink, `@mention` — bị ID chiếm; (b) tiêu đề tiếng Anh nguyên văn không cho biết **tại sao mình lưu bài này**; (c) khi ID đã thành property riêng thì để ở đầu là dư thừa.

**Quy ước đề xuất:**

```
<Luận điểm hành động, ≤ 60 ký tự> — arXiv <ID>
```

Ví dụ chuyển đổi:

| Trước | Sau |
|---|---|
| `2606.01435 - Don't Ask the LLM to Track Freshness: A Deterministic...` | `Lọc freshness tất định thay vì để LLM tự xử — arXiv 2606.01435` |
| `2602.01086 - MedBeads: An Agent-Native, Immutable Data Substrate...` | `Merkle DAG append-only cho audit trail y tế — arXiv 2602.01086` |

**Luật cứng** (kiểm được bằng regex trong CI):

1. Độ dài tổng ≤ 80 ký tự.
2. Phần luận điểm ≥ 10 ký tự, viết bằng **tiếng Việt** nếu là kỹ thuật ứng dụng được ngay; giữ **thuật ngữ EN nguyên văn** cho tên kiến trúc/benchmark (`Merkle DAG`, `RAG`, `KV-cache`) — không dịch bừa.
3. Dấu phân cách là `—` (em dash), có khoảng trắng hai bên. Không dùng `-` (trùng với dấu nối trong tiêu đề gốc).
4. **Không** nhét `[P0]`, `[ANES]`, emoji trạng thái vào tiêu đề — đó là việc của Properties. Nhét vào tiêu đề tạo hai nguồn sự thật, và khi Relevance đổi thì tiêu đề thành sai.
5. Tiêu đề gốc tiếng Anh đầy đủ **không mất đi** — nó nằm trong Callout đầu trang (§2.2).

```
^.{10,80} — arXiv \d{4}\.\d{4,5}$
```

### 1.3 Từ vựng đóng cho `Core Tags` — và cái bẫy im lặng

**Cảnh báo vận hành quan trọng**: Notion API **tự động tạo option mới** khi bạn ghi một giá trị `select`/`multi_select` chưa tồn tại. Không có lỗi, không có cảnh báo. Hệ quả: LLM gõ `RAG` lần này, `Retrieval-Augmented Generation` lần sau, `rag` lần nữa ⇒ sau 3 tháng bạn có 40 tag, filter vô dụng, và **không có cách nào phát hiện ngoài mở mắt ra nhìn**.

**Chốt chặn**: validate ở phía client trước khi gọi API, và **throw khi gặp giá trị lạ** — cùng triết lý fail-loud của `ClinicalValidationError` bên AnesthOS, và cùng nguyên tắc "tất định ở mọi tầng lọc" của SR-Agent.

```python
# sr_agent/publish/vocabulary.py
CORE_TAGS: frozenset[str] = frozenset({
    # Kiến trúc & bộ nhớ
    "RAG", "Memory Systems", "Vector DB", "Context Engineering", "Long Context",
    # Hệ đa tác tử
    "Multi-Agent", "Agent Verification", "Planning", "Tool Use", "Orchestration",
    # Độ tin cậy
    "Hallucination Control", "Determinism", "Guardrails", "Evaluation", "Uncertainty",
    # Vận hành
    "Local LLM", "Quantization", "Latency", "Structured Output", "Fine-tuning",
    # Miền ứng dụng
    "Clinical Decision Support", "Privacy/Compliance", "Time-Series", "Provenance",
})

class VocabularyError(ValueError):
    """Giá trị nằm ngoài từ vựng đóng — chặn trước khi Notion âm thầm tạo option rác."""

def assert_tags(tags: list[str]) -> list[str]:
    unknown = [t for t in tags if t not in CORE_TAGS]
    if unknown:
        raise VocabularyError(
            f"Tag ngoài từ vựng: {unknown}. Thêm vào CORE_TAGS có chủ đích "
            f"(kèm commit) hoặc map về tag gần nhất — không để API tự tạo."
        )
    return tags
```

Áp dụng y hệt cho `Target Project`, `Relevance`, `Impact Type`, `Evidence Grade`, `Clinical Gate`.

### 1.4 `Clinical Gate` — chốt chặn giữa arXiv và mã lâm sàng

Đây là property quan trọng nhất về mặt an toàn, sinh trực tiếp từ `AnesthOS-app/CLAUDE.md`.

Rủi ro cụ thể: một preprint arXiv đề xuất công thức liều thuốc → được gắn `Target Project: AnesthOS` → ai đó (người hoặc agent) copy con số vào `src/domain/calculators/` → **BS-C bị vi phạm**: `ClinicalProvenance.issuingOrganization` bị điền tên một preprint chưa peer-review như thể nó là guideline của hội chuyên ngành.

| Giá trị | Nghĩa | Luật |
|---|---|---|
| `N/A` | Không liên quan AnesthOS | — |
| `Engineering-only` | Chỉ đụng hạ tầng: retrieval, caching, schema, latency, audit log | Được phép đi thẳng tới `Integrated` |
| `Cần thẩm định lâm sàng` | Chạm tới liều lượng, ngưỡng sinh hiệu, khuyến cáo điều trị | **Chặn ở `PoC Proposed`.** Chỉ mở khi có nguồn guideline chính thức (không phải bài báo này) điền được đủ 5 trường `ClinicalProvenance` |
| `Blocked` | Mâu thuẫn guideline hiện hành, hoặc yêu cầu vi phạm BS-F (network/`Date.now()` trong `src/domain/`) | Không bao giờ `Integrated` |

**Luật bất biến**: `Target Project` chứa `AnesthOS` **AND** `Status = Integrated` ⇒ `Clinical Gate ∈ {N/A, Engineering-only}`. Cài thành một filtered view "🚨 Vi phạm cổng lâm sàng" — trống là đúng, có hàng nào là sự cố.

**Về ràng buộc phạm vi của SR-Agent**: `docs/HANDOVER.md` §1 khóa cứng "không xử lý dữ liệu y sinh hoặc lâm sàng". Thiết kế này **không** phá ràng buộc đó: SR-Agent vẫn chỉ nạp **metadata công khai của bài báo CS**. `Target Project: AnesthOS` có nghĩa là *"kỹ thuật này áp dụng được cho phần engineering của AnesthOS"*, **không** phải *"bài này là bằng chứng lâm sàng cho AnesthOS"*. `Clinical Gate` chính là thứ giữ cho hai nghĩa đó không lẫn vào nhau.

### 1.5 Views cần tạo

| View | Kiểu | Filter / Group |
|---|---|---|
| 🔥 **P0 Queue** | Table | `Relevance = P0` AND `Status ≠ Integrated`, sort `Rubric Score` desc |
| 🧭 **Theo dự án** | Board | Group by `Target Project` |
| 🔄 **Vòng đời** | Board | Group by `Status` — Kanban chính |
| 🪦 **Nghĩa địa** | Table | `Status = New` AND `Created < 14 ngày trước` — hàng đợi auto-archive (§3.4) |
| 🚨 **Vi phạm cổng lâm sàng** | Table | `Target Project` chứa `AnesthOS` AND `Status = Integrated` AND `Clinical Gate` là `Cần thẩm định lâm sàng`/`Blocked` |
| 📅 **Tuần này** | Gallery | `Created` trong 7 ngày |

---

## PHẦN 2 — Page Template & API Payload

### 2.1 Ba ràng buộc cứng của Notion API (thiết kế phải nằm gọn bên trong)

1. **≤ 100 block/request.** Template dưới đây ~34 block ⇒ gửi trọn trong 1 lệnh `pages.create` (nguyên tử, không có trang dựng dở — giữ đúng tính chất hiện có của `notion_page.py`).
2. **≤ 2 cấp lồng nhau trong một request.** `children` của page = cấp 1; `children` của một block = cấp 2; sâu hơn ⇒ API từ chối. ⇒ **Không lồng toggle trong toggle.** Cấu trúc hiện tại `heading (L1) → toggle (L1) → to_do (L2)` là hợp lệ; giữ nguyên khuôn đó.
3. **≤ 2000 ký tự / rich_text object.** Abstract dài phải cắt thành nhiều text object hoặc nhiều paragraph. Helper `_rt()` hiện tại cắt cụt ở 2000 — cần sửa thành **chia nhỏ** thay vì cắt mất chữ.

### 2.2 Cấu trúc trang

Vì metadata đã lên Properties (Phần 1), body **không lặp lại metadata** nữa. Body chỉ chứa thứ Properties không chứa nổi: văn bản dài, phân tích, checklist.

```
┌─ [1] Callout 💡  — TL;DR + tiêu đề gốc EN                     (1 block)
├─ [2] Callout 🏥  — Cảnh báo cổng lâm sàng (CHỈ khi AnesthOS)   (0–1)
├─ [3] Toggle 📄  "Abstract song ngữ"                            (1 + 3)
│     ├─ Paragraph EN
│     ├─ Divider
│     └─ Paragraph VI
├─ [4] Heading 2 "🎯 Phân tích ứng dụng"                          (1)
├─ [5] Quote      — cơ chế cốt lõi, 1–3 câu                       (1)
├─ [6] Bulleted   — ánh xạ vào dự án cụ thể                       (1–3)
├─ [7] Toggle 🔬  "Cơ chế kỹ thuật & artifact"                    (1 + 4)
│     └─ 4 bullet: repo / dataset / benchmarks / limitations
├─ [8] Heading 2 "❓ Q&A phản biện"                                (1)
├─ [9] Toggle Q1  → 3 to_do [CONFIRMED]/[INFERRED]/[UNKNOWN] + ô trả lời   (1 + 4)
├─ [10] Toggle Q2 → tương tự                                      (1 + 4)
├─ [11] Divider                                                   (1)
├─ [12] Heading 2 "🚀 Đề xuất PoC"                                (1)
├─ [13] to_do ×3  — việc cụ thể, có repo đích                     (3)
├─ [14] Heading 2 "📝 My Notes"                                   (1)
├─ [15] Paragraph trống                                           (1)
└─ [16] Callout ⚙️ — provenance: SR-Agent version, model, rubric, timestamp  (1)
```

Thiết kế có chủ đích:
- **Callout đầu trang** trả lời "tại sao tôi lưu bài này" trong 1 dòng — thứ duy nhất bạn đọc khi lướt lại sau 3 tháng.
- **Toggle cho abstract** thay vì Table: table cell không xuống dòng tốt, một abstract 200 từ nhét vào cell sẽ vỡ layout trên mobile. Toggle mặc định đóng ⇒ trang gọn. *(Nếu vẫn muốn Table song ngữ cạnh nhau, payload có ở §2.4 — dùng cho abstract ngắn < 80 từ.)*
- **Quote cho phân tích ứng dụng** đúng như yêu cầu: quote block có border trái, nổi bật thị giác, tách bạch "lời của tác giả bài báo" (abstract) khỏi "lời của tôi" (phân tích).
- **Callout provenance cuối trang** là bản sao tinh thần của `ClinicalProvenance` bên AnesthOS: mọi trang do máy sinh đều phải khai báo máy nào sinh, lúc nào, bằng model gì.

### 2.3 Payload mẫu (rút gọn — bản đầy đủ do `notion_blocks.py` sinh)

```jsonc
{
  "parent": { "database_id": "39a64a33-c832-80dc-a3c1-e331745188cf" },
  "properties": {
    "Name":           { "title": [{ "text": { "content": "Lọc freshness tất định thay vì để LLM tự xử — arXiv 2606.01435" }}] },
    "SR UID":         { "rich_text": [{ "text": { "content": "arxiv:2606.01435" }}] },
    "arXiv ID":       { "rich_text": [{ "text": { "content": "2606.01435" }}] },
    "Source":         { "select": { "name": "arXiv" } },
    "Link":           { "url": "https://arxiv.org/abs/2606.01435" },
    "Published":      { "date": { "start": "2026-06-03" } },
    "Relevance":      { "select": { "name": "P0 — Cấp thiết" } },
    "Target Project": { "multi_select": [{ "name": "AnesthOS" }, { "name": "Agent Harnessing" }] },
    "Core Tags":      { "multi_select": [{ "name": "Memory Systems" }, { "name": "Determinism" }, { "name": "Hallucination Control" }] },
    "Status":         { "status": { "name": "Analyzed" } },
    "Rubric Score":   { "number": 87.5 },
    "Impact Type":    { "select": { "name": "Guardrail" } },
    "Evidence Grade": { "select": { "name": "Preprint + benchmark" } },
    "Clinical Gate":  { "select": { "name": "Engineering-only" } },
    "Code Repo":      { "url": "https://github.com/example/freshness" }
  },
  "children": [
    { "object": "block", "type": "callout", "callout": {
        "icon": { "type": "emoji", "emoji": "💡" },
        "color": "blue_background",
        "rich_text": [
          { "type": "text", "text": { "content": "TL;DR — " }, "annotations": { "bold": true }},
          { "type": "text", "text": { "content": "Đừng bắt LLM tự phân xử dữ liệu nào mới hơn; dùng bộ lọc timestamp tất định ở tầng truy xuất. Giảm lỗi prior-override mà không tốn thêm token." }},
          { "type": "text", "text": { "content": "\n\nDon't Ask the LLM to Track Freshness: A Deterministic Recipe for Memory Conflict Resolution" },
            "annotations": { "italic": true, "color": "gray" }}
        ]}},

    { "object": "block", "type": "callout", "callout": {
        "icon": { "type": "emoji", "emoji": "🏥" },
        "color": "yellow_background",
        "rich_text": [{ "type": "text", "text": { "content":
          "CỔNG LÂM SÀNG: Engineering-only. Kỹ thuật này chỉ áp dụng cho tầng truy xuất/lưu trữ. KHÔNG dùng bài báo này làm nguồn cho bất kỳ giá trị liều lượng, ngưỡng sinh hiệu hay khuyến cáo điều trị nào (BS-C: preprint không phải guideline)." }}]}},

    { "object": "block", "type": "toggle", "toggle": {
        "rich_text": [{ "type": "text", "text": { "content": "📄 Abstract song ngữ" }, "annotations": { "bold": true }}],
        "children": [
          { "object": "block", "type": "paragraph", "paragraph": {
              "rich_text": [
                { "type": "text", "text": { "content": "EN — " }, "annotations": { "bold": true, "color": "gray" }},
                { "type": "text", "text": { "content": "Recent advances in LLM memory systems rely on the model itself to resolve conflicting information across time…" }}
              ]}},
          { "object": "block", "type": "divider", "divider": {} },
          { "object": "block", "type": "paragraph", "paragraph": {
              "rich_text": [
                { "type": "text", "text": { "content": "VI — " }, "annotations": { "bold": true, "color": "gray" }},
                { "type": "text", "text": { "content": "Các tiến bộ gần đây trong hệ thống bộ nhớ LLM dựa vào chính mô hình để giải quyết mâu thuẫn dữ liệu theo thời gian…" }}
              ]}}
        ]}},

    { "object": "block", "type": "heading_2", "heading_2": {
        "rich_text": [{ "type": "text", "text": { "content": "🎯 Phân tích ứng dụng" }}]}},

    { "object": "block", "type": "quote", "quote": {
        "color": "purple",
        "rich_text": [{ "type": "text", "text": { "content":
          "Cơ chế cốt lõi: tách quyết định \"bản ghi nào mới hơn\" ra khỏi LLM và đẩy xuống tầng truy vấn tất định. LLM chỉ đọc kết quả đã được sắp xếp, không tự suy luận thứ tự thời gian." }}]}},

    { "object": "block", "type": "bulleted_list_item", "bulleted_list_item": {
        "rich_text": [
          { "type": "text", "text": { "content": "AnesthOS: " }, "annotations": { "bold": true }},
          { "type": "text", "text": { "content": "áp vào lớp truy vấn SQLite cục bộ — hàm chọn bản ghi sinh hiệu mới nhất viết bằng SQL thuần, đặt trong src/domain/ (thuần, tất định, không network — hợp BS-F)." }}
        ]}},

    { "object": "block", "type": "heading_2", "heading_2": {
        "rich_text": [{ "type": "text", "text": { "content": "🚀 Đề xuất PoC" }}]}},
    { "object": "block", "type": "to_do", "to_do": { "checked": false,
        "rich_text": [{ "type": "text", "text": { "content": "SRagent · viết selector timestamp tất định + test bảng chân trị mâu thuẫn (~0.5 ngày)" }}]}},

    { "object": "block", "type": "callout", "callout": {
        "icon": { "type": "emoji", "emoji": "⚙️" },
        "color": "gray_background",
        "rich_text": [{ "type": "text", "text": { "content":
          "Sinh tự động bởi SR-Agent · rubric 87.5/100 · parser qwen2.5:7b-instruct (temp 0) · 2026-08-02T06:26Z · Nội dung VI do máy dịch, chưa qua người soát." }}]}}
  ]
}
```

### 2.4 Biến thể Table song ngữ (cho abstract ngắn)

```jsonc
{ "object": "block", "type": "table", "table": {
    "table_width": 2, "has_column_header": true, "has_row_header": false,
    "children": [
      { "object": "block", "type": "table_row", "table_row": { "cells": [
          [{ "type": "text", "text": { "content": "English" }, "annotations": { "bold": true }}],
          [{ "type": "text", "text": { "content": "Tiếng Việt" }, "annotations": { "bold": true }}]
      ]}},
      { "object": "block", "type": "table_row", "table_row": { "cells": [
          [{ "type": "text", "text": { "content": "<abstract EN>" }}],
          [{ "type": "text", "text": { "content": "<abstract VI>" }}]
      ]}}
    ]}}
```

Lưu ý: `table` là block cấp 1, `table_row` là cấp 2 ⇒ vừa đủ giới hạn 2 cấp. `cells` là **mảng của mảng rich_text**, số phần tử phải khớp `table_width`.

### 2.5 Thay đổi cần thiết ở `notion-mcp-server/index.js`

Giữ nguyên 6 tool (không tăng số tool — mỗi tool thêm là chi phí context cho mọi client), chỉ **nới input schema**:

```js
// notion_create_page: thêm 2 field
properties: {
  type: "object",
  description: "Notion properties object nguyên bản. VD: {\"Relevance\":{\"select\":{\"name\":\"P0 — Cấp thiết\"}}}. Gộp với 'title' nếu cả hai cùng có."
},
children: {
  type: "array",
  description: "Mảng Notion block object nguyên bản (tối đa 100, lồng tối đa 2 cấp). Ưu tiên hơn 'content' nếu cả hai cùng có."
}

// executeNotionTool — case "notion_create_page":
const props = parent_type === "database_id"
  ? { Name: { title: [{ text: { content: title } }] }, ...(args.properties || {}) }
  : { title: { title: [{ text: { content: title } }] }, ...(args.properties || {}) };
const blocks = Array.isArray(args.children) && args.children.length
  ? args.children
  : (content ? [ /* paragraph fallback như cũ */ ] : []);
return await notion.pages.create({ parent, properties: props, children: blocks });

// notion_append_block_children: thêm 'children' (array), giữ 'text' làm fallback
const blocks = Array.isArray(args.children) && args.children.length
  ? args.children
  : [{ object:'block', type:'paragraph', paragraph:{ rich_text:[{ type:'text', text:{ content: args.text }}]}}];
return await notion.blocks.children.append({ block_id: args.block_id, children: blocks });

// notion_query_database: thêm filter / sorts / page_size (passthrough thẳng vào SDK)
return await notion.databases.query({
  database_id: args.database_id,
  ...(args.filter ? { filter: args.filter } : {}),
  ...(args.sorts  ? { sorts:  args.sorts  } : {}),
  page_size: args.page_size ?? 10,
});
```

**Tương thích ngược tuyệt đối**: mọi field mới đều optional, mọi lời gọi cũ chạy y như trước.

**Hai việc nên làm kèm** (nợ kỹ thuật đang lộ ra trong `index.js`):
- Trả lỗi Notion kèm `error.code` + `error.body`, không chỉ `error.message` — hiện debug property sai kiểu gần như mù.
- Thêm `notion_update_page` **hoặc** cho `notion_create_page` nhận `page_id` để update — nếu không, không có cách nào đổi `Status` từ `New` sang `Analyzed`, và toàn bộ Phần 3 không chạy được. **Đây là tool thứ 7 duy nhất thực sự cần.**

---

## PHẦN 3 — Data-to-Impact Workflow

### 3.1 Bảy chặng

```
[0] BLOCKER REGISTRY  — người duy trì, 5–10 nút thắt đang mở/dự án (file YAML trong repo)
        │  ← đây là thứ biến "bài hay" thành "bài cần"
        ▼
[1] SCAN     · pipeline run (launchd 07:00) → dedup D34 → rubric ≥ 60 → Ollama parse
[2] SCORE    · Impact Rubric (§3.2) chấm trên blocker registry → P0/P1/P2/P3
[3] SYNTH    · dịch song ngữ + sinh "Phân tích ứng dụng" + 3 việc PoC ứng viên
[4] DECIDE   · QC UI (WIP 5/ngày) — người bấm Approve/Reject       ← chốt chặn người
[5] PUBLISH  · tạo trang Notion đầy đủ properties + blocks; Status = Analyzed
[6] SPAWN    · nếu P0: tạo hàng trong PoC Backlog + Relation ngược + ntfy push
[7] INTEGRATE· PoC → spec bàn giao Antygravity → commit → Status = Integrated
                                                              │
        └───────────────── CLOSE LOOP ─────────────────────────┘
             commit message chứa SR UID → cron tuần đối chiếu → auto set Integrated
```

**Chặng [0] là chặng bị bỏ quên nhất và cũng là chặng quyết định.** Không có danh sách nút thắt đang mở, mọi bài báo đều "thú vị" như nhau và P0 mất nghĩa. Blocker registry là file phẳng, người tự sửa:

```yaml
# blockers.yaml
anesthos:
  - id: ANES-B1
    text: "Độ trễ truy vấn RAG offline > 800ms trên thiết bị phòng mổ"
    keywords: [latency, quantization, local llm, retrieval, caching, kv-cache]
    weight: 1.0
  - id: ANES-B2
    text: "Ảo giác liều thuốc — LLM sinh số không có trong nguồn"
    keywords: [hallucination, grounding, constrained decoding, numeric verification]
    weight: 1.0
  - id: ANES-B3
    text: "Phân tách đa bệnh viện trong Qdrant"
    keywords: [multitenancy, isolation, vector db, access control]
    weight: 0.7
agent_harnessing:
  - id: AGENT-B1
    text: "Agent-V thiếu tiêu chí đối chiếu tất định giữa output LLM và nguồn"
    keywords: [verification, fact-checking, provenance, numeric firewall]
    weight: 1.0
  - id: AGENT-B2
    text: "Chưa có bộ eval hồi quy cho Agent-R"
    keywords: [evaluation, benchmark, regression, llm-as-judge]
    weight: 0.8
```

### 3.2 Impact Rubric — P0/P1/P2 tất định

Tái dùng nguyên khuôn `quality/rubric.py` (rubric khai báo + `RULE_REGISTRY` pure functions + JSON Schema). Đây là **rubric thứ hai**, chạy **sau** rubric chất lượng:

- Rubric 1 (`rubric.py`, đã có): *"Bài này có phải bài tử tế không?"* → gate 60, chạy **trước** LLM.
- Rubric 2 (`impact_rubric.py`, mới): *"Bài này có giải quyết vấn đề TÔI đang mắc không?"* → gán P0/P1/P2, chạy **sau** LLM parse (cần `tech_meta`).

| Tiêu chí | Trọng số | Cách chấm (tất định) |
|---|---|---|
| `blocker_match` | **35** | Max độ phủ keyword của bất kỳ blocker nào × `weight` của blocker đó |
| `actionability` | 25 | có `code_repo` (+40) · khớp stack Python/SQLite/Qdrant/Ollama (+30) · có `dataset_specification` (+30) |
| `risk_reduction` | 20 | tag ∈ {Hallucination Control, Determinism, Guardrails, Provenance, Privacy/Compliance} → 100; ×1.25 nếu `Target Project` chứa AnesthOS (trần 100) |
| `integration_cost` | 10 | nghịch đảo: ≤1 ngày=100 · ≤1 tuần=60 · ≤1 tháng=25 · >1 tháng=0 |
| `evidence_strength` | 10 | Peer-reviewed=100 · Preprint+benchmark=70 · Preprint only=40 · Position=20 |

**Ngưỡng phân loại — hai điều kiện, không phải một:**

| Mức | Điều kiện |
|---|---|
| **P0 — Cấp thiết** | `impact ≥ 75` **AND** `blocker_match ≥ 70` |
| **P1 — Quan trọng** | `impact ≥ 55` |
| **P2 — Tham khảo** | `impact ≥ 35` |
| **P3 — Lưu trữ** | còn lại — **không tạo trang Notion**, chỉ giữ trong SQLite |

Điều kiện kép ở P0 là có chủ đích: nó chặn trường hợp một bài xuất sắc về mọi mặt (repo đẹp, peer-reviewed, chi phí thấp) nhưng **không chạm vào nút thắt nào của bạn** vẫn leo lên P0 và cướp sự chú ý. P0 phải nghĩa là *"khẩn với TÔI"*, không phải *"hay với thế giới"*.

**Trần P0**: tối đa **2 bài P0/tuần**. Vượt trần ⇒ bài điểm thấp nhất trong nhóm tự hạ xuống P1. Không có trần này thì sau 2 tháng P0 lạm phát và trở thành vô nghĩa — đúng cơ chế đã được xử lý cho alert trong `monitor/alerts.py` (chống alarm fatigue), nay áp cho tri thức.

### 3.3 Action Trigger cho P0

Khi `Relevance = P0` và người đã Approve ở QC UI:

1. **Tạo trang phân tích** trong `SR-Agent Dashboard` (Phần 2), `Status = Analyzed`.
2. **Tạo hàng trong `PoC Backlog`** (database thứ hai — xem §3.5) với `Relation` hai chiều về trang bài báo, body là **khung spec sẵn**: Bối cảnh / Blocker liên quan / Giả thuyết / Tiêu chí nghiệm thu / Repo đích / Ước lượng.
3. **Cập nhật** trang bài báo → `Status = PoC Proposed` (cần tool update, §2.5).
4. **Push tóm tắt**: tái dùng **hạ tầng đã có** — `ALERT_WEBHOOK_URL` trong `.env.example` + `sr_agent/monitor/alerts.py` đã bắn ntfy.sh/Slack/Discord. Không dựng gì mới.

   ```
   🔴 P0 — Lọc freshness tất định thay vì để LLM tự xử
   Blocker: AGENT-B1 (Agent-V thiếu đối chiếu tất định) · impact 82
   → Selector timestamp SQL thuần, ~0.5 ngày, có repo
   notion.so/…  ·  arxiv.org/abs/2606.01435
   ```
5. **Bàn giao thi công**: nội dung PoC page map 1-1 sang skill `handoff-antygravity` (spec 11 mục) ⇒ P0 đi thẳng từ Notion sang Executor mà không phải gõ lại.

### 3.4 Chống "nghĩa địa dữ liệu" — ba cơ chế

Đây là phần trả lời trực tiếp cho lo ngại lớn nhất của đề bài. Một cơ chế là không đủ.

| # | Cơ chế | Cấu hình | Nguyên lý |
|---|---|---|---|
| 1 | **TTL tri thức** | `Status = New` quá **14 ngày** → tự chuyển `Archived` kèm comment "hết hạn, chưa ai đọc" | Copy nguyên tắc `TTL_HOURS = 72` của staging lên tầng tri thức. Hàng đợi phải tự dọn, nếu không nó chỉ dài ra. |
| 2 | **WIP limit** | Tối đa **5** hàng ở `PoC Proposed` cùng lúc. Đầy ⇒ P0 mới bị giữ ở `Analyzed` + cảnh báo | Copy `WIP_LIMIT = 5`. Đọc thì rẻ, **làm** mới đắt — nghẽn thật nằm ở đây. |
| 3 | **Định luật bảo toàn** | Mỗi bài lên `Integrated` phải có **ít nhất 1 artifact**: commit SHA, file spec, hoặc dòng trong `blockers.yaml` chuyển sang `resolved` | Không có artifact thì "Integrated" chỉ là nút bấm cho vui. Đây là điều kiện *thoát* của toàn hệ thống. |

Thêm một **chỉ số sức khỏe** hiển thị ở tab "🩺 Sức khỏe hệ thống" (Streamlit UI đã có sẵn):

```
Impact Ratio = số bài Integrated / số bài Ingested   (cửa sổ 30 ngày)
```

< 5% ⇒ hệ thống đang là nghĩa địa: hoặc siết rubric, hoặc giảm tần suất quét. Đây là **dead-man's switch cho tri thức**, song song với dead-man's switch cho batch đã có trong `monitor/health.py`.

### 3.5 Database thứ hai: `PoC Backlog`

| Property | Kiểu | Options |
|---|---|---|
| `Name` | Title | `<Động từ> <đối tượng> — <repo đích>` (VD: `Thêm selector timestamp tất định — SRagent`) |
| `Source Paper` | Relation → SR-Agent Dashboard | ← khóa đóng vòng lặp |
| `Blocker` | Select | ID từ `blockers.yaml` |
| `Repo` | Select | `SRagent` · `AnesthOS-app` · `notion-mcp-server` |
| `Effort` | Select | `≤0.5d` · `≤2d` · `≤1w` · `>1w` |
| `State` | Status | `Backlog` → `Spec'd` → `Building` → `Merged` → `Dropped` |
| `Commit` | Text | SHA — bằng chứng của §3.4 #3 |

---

## PHẦN 4 — Kế hoạch triển khai

### Sprint N0 — Mở khóa hạ tầng (bắt buộc trước mọi thứ)

| # | Việc | Repo | Ước lượng | Phụ thuộc |
|---|---|---|---|---|
| 1 | Nới schema 3 tool (`create_page` + `properties`/`children`, `append_block_children` + `children`, `query_database` + `filter`/`sorts`) | notion-mcp-server | 2h | — |
| 2 | Thêm tool `notion_update_page` (đổi properties của trang có sẵn) | notion-mcp-server | 1h | 1 |
| 3 | Trả lỗi kèm `error.code` + `error.body` | notion-mcp-server | 20m | — |
| 4 | Deploy lại Render + smoke test `/health`, `/mcp` | notion-mcp-server | 30m | 1–3 |

**Tiêu chí nghiệm thu N0**: một lệnh `notion_create_page` duy nhất tạo được trang có ≥ 5 property và ≥ 1 callout hiển thị đúng icon.

### Sprint N1 — Schema Notion (một lần, làm tay)

| # | Việc | Nơi làm | Ước lượng |
|---|---|---|---|
| 5 | Tạo 11 property CORE trong `SR-Agent Dashboard` | Notion UI | 30m |
| 6 | Tạo 6 View (§1.5) | Notion UI | 20m |
| 7 | Tạo database `PoC Backlog` + Relation hai chiều | Notion UI | 20m |
| 8 | Backfill ~N trang cũ: parse text body → điền property | script 1 lần | 1h |
| 9 | Ghi `NOTION_DASHBOARD_DB_ID` / `NOTION_POC_DB_ID` vào `.env.example` + `config.py` | SRagent | 15m |

> Làm bằng UI chứ không bằng API vì kiểu `status` không tạo được qua API, và đây là việc chỉ làm một lần.

### Sprint N2 — Publisher mới (phần code chính)

| # | Việc | File | Ước lượng |
|---|---|---|---|
| 10 | `publish/vocabulary.py` — từ vựng đóng + `VocabularyError` fail-loud | mới | 1h |
| 11 | `publish/notion_blocks.py` — pure builders (`callout/toggle/quote/table/todo`), sửa `_rt()` từ **cắt cụt** sang **chia nhỏ** 2000 ký tự | mới | 3h |
| 12 | `publish/notion_props.py` — `Document` + `ImpactAssessment` → properties object, có validate | mới | 2h |
| 13 | Viết lại `build_page_payload()` dùng 11+12; giữ chữ ký hàm & tính idempotent qua `SR UID` | `publish/notion_page.py` | 2h |
| 14 | Test offline: snapshot payload, xác nhận ≤100 block, ≤2 cấp lồng, không rich_text >2000, tag lạ → raise | `tests/test_notion.py` | 2h |

Tất cả builder là **pure function** ⇒ test không cần mạng, giữ đúng tính chất "75 tests chạy offline".

### Sprint N3 — Impact & tự động hóa

| # | Việc | File | Ước lượng |
|---|---|---|---|
| 15 | `blockers.yaml` — người điền 5–10 nút thắt thật | repo root | 45m (người) |
| 16 | `quality/impact_rubric.py` — rubric khai báo + `IMPACT_RULE_REGISTRY` | mới | 3h |
| 17 | Mở rộng `models/schemas.py`: `ImpactAssessment` (relevance, target_projects, core_tags, impact_type, clinical_gate, blocker_ids, poc_tasks) | sửa | 1h |
| 18 | Prompt LLM sinh bản dịch VI + "phân tích ứng dụng" + 3 PoC ứng viên (structured output, temp 0, cùng khuôn `structural.py`) | `parser/` | 3h |
| 19 | Trigger P0 → tạo PoC page + ntfy qua `alerts.py` | `publish/` + `monitor/alerts.py` | 2h |
| 20 | Cron tuần: query `Status=New` & >14 ngày → `Archived`; tính Impact Ratio | `monitor/` | 2h |
| 21 | Hiện Impact Ratio + đếm P0 tuần ở tab Sức khỏe | `ui/app.py` | 1h |

### Sprint N4 — Cổng an toàn AnesthOS

| # | Việc | Ước lượng |
|---|---|---|
| 22 | Luật `Clinical Gate` trong `impact_rubric.py`: chạm liều/ngưỡng/khuyến cáo → auto `Cần thẩm định lâm sàng` | 1h |
| 23 | View "🚨 Vi phạm cổng lâm sàng" + kiểm tra tuần; có hàng ⇒ alert đỏ | 45m |
| 24 | Ghi luật vào `AnesthOS-app/CLAUDE.md` §2: "không nguồn tri thức nào từ SR-Agent được điền `ClinicalProvenance` — provenance chỉ đến từ guideline của tổ chức chuyên ngành" | 30m |

**Tổng: ~32h công việc code + ~2h thao tác tay.** Đường găng: `1 → 2 → 5 → 11 → 13 → 16 → 19`.

### Thứ tự khuyến nghị nếu muốn thấy kết quả sớm

Làm **N0 + N1 + hạng mục 11/13** trước (khoảng 10h). Ngay sau đó trang Notion đã đẹp và filter được — đó là 80% cảm giác "hệ thống đã hoạt động". N3 (impact rubric) chỉ có giá trị sau khi `blockers.yaml` đã có nội dung thật, mà nội dung đó cần bạn ngồi viết ra, không code thay được.

---

## 5. Giả định đã dùng & rủi ro còn mở

Mục 3 của đề bài để trống placeholder. Tôi suy hiện trạng **từ chính codebase** thay vì từ ví dụ trong template:

| Giả định | Căn cứ |
|---|---|
| AnesthOS đang ở P0 scaffold (`src/domain/calculators/` mới có `index.ts`, chưa có calculator thật; 3 commit) | `git log`, cây thư mục `AnesthOS-app/src` |
| Nút thắt AnesthOS là độ trễ + ảo giác liều — **chưa có mã nào chứng minh**, đây là điểm cần bạn xác nhận | suy từ `CLAUDE.md` §2 (BS-B, BS-C, BS-F) |
| Agent Harnessing đã có khung V/E/R + guard tất định | `tools/guard/firewall.py` (Numeric Firewall V24), `outbound.py`, `docs/specs/D31` |
| Action trigger mong muốn = tạo PoC page + push tóm tắt | nêu trong ví dụ của đề bài; hạ tầng ntfy đã sẵn trong `alerts.py` |

**Rủi ro còn mở:**

1. **Chất lượng bản dịch VI**: qwen2.5:7b dịch thuật ngữ CS sang tiếng Việt ở mức khá, nhưng sẽ sai ở thuật ngữ hiếm. Callout provenance đã ghi rõ "máy dịch, chưa qua người soát" — đừng bỏ dòng đó.
2. **`blocker_match` bằng keyword là thô**: dùng embedding sẽ chính xác hơn nhưng **mất tính tất định** — nguyên tắc nền của SR-Agent. Đề xuất giữ keyword; nếu tỷ lệ bỏ sót cao, thêm bước người review danh sách "gần P0" hàng tuần thay vì đổi sang embedding.
3. **Backfill trang cũ**: các trang hiện có nhét metadata trong body dạng `## Metadata<br>- arXiv ID: ...`. Parse ngược được nhưng dễ vỡ; nếu số trang < 50, sửa tay nhanh và an toàn hơn viết script.
4. **Rate limit Notion ~3 req/s**: publish 5 bài/ngày thì vô hại, nhưng script backfill phải tự throttle.
5. **Chưa calibrate ngưỡng impact (75/55/35) và trần 2 P0/tuần**: giống cutoff fuzzy 93 và gate rubric 60 — là điểm khởi đầu hợp lý, cần 3–4 tuần dữ liệu thật để chỉnh.
