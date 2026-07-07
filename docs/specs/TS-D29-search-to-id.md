# TASK SPEC TS-D29-01 — `tools/search_to_id.py` (Cầu nối ngữ nghĩa → ID tất định)

> **Quyết định D29**: tác tử thực thi Antygravity đảm nhận toàn bộ coding. Tài liệu này là bản đặc tả giao việc — copy nguyên văn cho Antygravity.
> **Người duyệt nghiệm thu**: chủ dự án (con người). **Kiến trúc nền**: xem `docs/HANDOVER.md`.

---

## A. Bối cảnh repo

- Repo: `gunthqq30223132/9router`. **Toàn bộ SR-Agent nằm trên nhánh `claude/sr-agent-pipeline-design-rqtctp`** (main chỉ có template).
- Nhánh làm việc: tạo `feat/search-to-id` từ nhánh trên. Mọi thay đổi merge qua Pull Request có người duyệt.
- Môi trường: macOS (MacBook Air M4 16GB), Python 3.11, venv tại `.venv`, test bằng `.venv/bin/python -m pytest` (hiện 97 pass — không được làm đỏ).

## B. Mục tiêu (một câu)

Xây công cụ ngoại vi đứng **ngoài** package `sr_agent/`, nhận **chủ đề ngôn ngữ tự nhiên** (Việt/Anh) từ con người, tra cứu các nguồn học thuật và xuất ra **manifest danh sách ID tất định** (khớp regex tĩnh) để core pipeline nạp — ngữ nghĩa dừng lại ở biên, core giữ nguyên tính "mù chủ đề".

## C. Vùng cấm (forbidden zones — vi phạm là fail nghiệm thu)

- **KHÔNG sửa** `sr_agent/ingest/router.py` (logic phân loại ID hard-code), **KHÔNG sửa** class `Pipeline` trong `sr_agent/pipeline.py`, **KHÔNG sửa** hằng số `sr_agent/config.py`.
- **KHÔNG ghi** vào staging DB từ tool này (tool chỉ sinh file manifest).
- **KHÔNG thêm** dependency mới ngoài các gói sẵn có trong `pyproject.toml` (httpx, pydantic, tenacity, feedparser…).
- **KHÔNG đưa** ngữ nghĩa chủ đề (topic string) vào bất kỳ trường nào của Document trong core.
- Điểm chạm core **duy nhất được phép** (T4): đăng ký tùy chọn CLI mới trong hàm `main()` của `pipeline.py` + module mới `sr_agent/ingest/manifest.py` (additive).

## D. Kiến trúc & Hợp đồng I/O

### D1. Vị trí trong kiến trúc 3 lớp

```
L0 Con người : chủ đề ngữ nghĩa (vd "tổng hợp công nghệ RAG…")
L1 Cầu ngoại vi (TOOL NÀY): topic → query profile per-source → search() → ID manifest
L2 Core tất định (KHÔNG ĐỔI): manifest → fetch theo ID → D34 → rubric → staging → QC
   Ranh giới L1→L2: CHỈ ID khớp config.ID_PATTERNS được đi qua.
```

### D2. Hợp đồng CLI của `tools/search_to_id.py`

| Tham số | Kiểu | Bắt buộc | Mô tả |
|---|---|---|---|
| `--topic` | str | có | chủ đề ngôn ngữ tự nhiên (VN/EN) |
| `--sources` | csv | không (mặc định `arxiv,ieee`) | tập con của 2 nguồn khóa cứng |
| `--max-per-source` | int | không (mặc định 20) | trần ID mỗi nguồn |
| `--out` | path | không (mặc định `staging/inbox/<timestamp>.manifest.json`) | file manifest đầu ra |
| `--expand` | flag | không (mặc định TẮT) | bật mở rộng query bằng Ollama local (FR-5) |
| `--profile` | path | không | file profile query tùy biến (mặc định `tools/profiles/default.json`) |

Exit code: `0` = có ≥1 ID hợp lệ; `2` = không tìm được ID nào; `3` = lỗi cấu hình (vd thiếu IEEE_API_KEY khi chọn nguồn ieee); `4` = lỗi mạng sau khi hết retry.

### D3. Schema manifest đầu ra (JSON, tự mô tả để audit)

```json
{
  "spec_version": "1.0",
  "topic": "tổng hợp công nghệ RAG tính đến hiện tại",
  "generated_at": "2026-07-07T09:00:00+00:00",
  "expansion": {
    "strategy": "static-profile | ollama-expand",
    "queries": {
      "arxiv": "all:\"retrieval augmented generation\"",
      "ieee": "(\"retrieval augmented generation\" OR \"RAG\") AND \"large language model\""
    }
  },
  "items": [
    {
      "source": "arxiv",
      "id": "arxiv:2312.10997",
      "rank": 1,
      "found_by_query": "all:\"retrieval augmented generation\"",
      "title_hint": "Retrieval-Augmented Generation for LLMs: A Survey"
    }
  ],
  "rejected": [
    { "raw_id": "2312.10997v3", "reason": "không khớp ID_PATTERNS sau chuẩn hóa" }
  ]
}
```

## E. Yêu cầu chức năng (FR)

- **FR-1 — Query profile per-source (nguyên lý Gusenbauer)**: bản dịch chủ đề → query cho TỪNG nguồn nằm trong file profile khai báo (`tools/profiles/default.json`), không hard-code trong Python. Mỗi nguồn một dialect: IEEE hỗ trợ boolean đầy đủ; arXiv dùng field-prefix (`all:`, `cat:`). Profile có thể chứa nhiều query biến thể cho một chủ đề.
- **FR-2 — Tái dùng adapter sẵn có**: gọi `search()` của `IEEEXploreFetcher` / `ArxivFetcher` (import read-only từ `sr_agent.ingest.*`) để thừa hưởng retry/backoff/error taxonomy. **Cấm gọi `fetch()`** — tool chỉ lấy ID, không nạp nội dung.
- **FR-3 — Validate ID tại biên**: từng ID phải khớp `config.ID_PATTERNS` (với arXiv: chuẩn hóa qua `normalize_arxiv_id()` sẵn có trước khi so). ID không khớp → đưa vào mảng `rejected` kèm lý do; **cấm tự "sửa" ID**.
- **FR-4 — Dedupe & rank ổn định**: loại ID trùng trong manifest, giữ thứ hạng lần xuất hiện đầu.
- **FR-5 — Mở rộng query bằng LLM (tùy chọn, mặc định tắt)**: khi `--expand`, dùng `OllamaClient.generate_structured()` sẵn có (temperature 0, schema Pydantic `list[str]` tối đa 5 query biến thể). Ollama chết → **suy giảm êm** về profile tĩnh, không được crash (in cảnh báo).
- **FR-6 — Provenance đầy đủ**: mỗi ID kèm `found_by_query` + `rank`; header manifest ghi topic gốc + strategy. Đây là audit trail nối ý định con người với ID máy.
- **FR-7 — Ghi atomic**: ghi file tạm rồi rename để không bao giờ có manifest dở dang.

## F. Yêu cầu phi chức năng (NFR)

- **NFR-1**: Python 3.11, đặt tại `tools/` (ngoài package `sr_agent`), chạy được bằng `.venv/bin/python tools/search_to_id.py …`.
- **NFR-2**: docstring + thông điệp tiếng Việt, giải thích "tại sao" ở đầu file — đúng convention codebase.
- **NFR-3**: tests offline 100% (respx mock HTTP, fixtures JSON/Atom có sẵn trong `tests/fixtures/`), không cần mạng/Ollama/key.
- **NFR-4**: thời gian chạy < 60s cho 2 nguồn với max 20/nguồn (không kể retry).
- **NFR-5**: log ra stderr, manifest ra file — stdout sạch để pipe được.

## G. Phân rã công việc

| Task | Nội dung | Input | Output | DoD |
|---|---|---|---|---|
| **T1** | Khung CLI + đọc profile + schema manifest (Pydantic model riêng của tool) | spec mục D | `tools/search_to_id.py`, `tools/profiles/default.json` | chạy `--topic x` với profile tĩnh ra manifest rỗng hợp lệ, exit 2 |
| **T2** | Nối adapter search per-source + validate/dedupe/provenance (FR-2,3,4,6,7) | T1 | manifest có items thật (mock trong test) | tests offline: ID hợp lệ vào items, ID rác vào rejected |
| **T3** | Nhánh `--expand` qua Ollama + suy giảm êm (FR-5) | T2 | flag hoạt động | test: Ollama mock sống → nhiều query; mock chết → fallback, không crash |
| **T4** | Cổng nạp core: `sr_agent/ingest/manifest.py` (đọc manifest → group theo source → `fetcher_for(source).fetch(ids)` → `Pipeline.process_document` từng doc, cô lập lỗi như `retry_dlq`) + đăng ký CLI `pipeline run --ids-file <path>` trong `main()` | T2 | lệnh `python -m sr_agent.pipeline run --ids-file …` | E2E offline: manifest fixture → doc vào QUEUED; `git diff router.py` RỖNG |
| **T5** | Tests tổng hợp + cập nhật README (mục "Luồng chủ đề → ID → nạp") | T1–T4 | `tests/test_search_to_id.py`, README | toàn bộ pytest xanh (97 cũ + mới) |

## H. Tiêu chí nghiệm thu (người duyệt chạy đúng các lệnh này)

1. `.venv/bin/python -m pytest` → toàn bộ xanh.
2. `.venv/bin/python tools/search_to_id.py --topic "retrieval augmented generation" --sources arxiv --out /tmp/m.json` (có mạng) → exit 0, manifest hợp lệ, mọi `items[].id` khớp regex.
3. `.venv/bin/python -m sr_agent.pipeline run --ids-file /tmp/m.json` → báo cáo batch, doc vào staging, `pipeline status` phản ánh đúng.
4. `git diff origin/claude/sr-agent-pipeline-design-rqtctp -- sr_agent/ingest/router.py sr_agent/config.py` → **rỗng**; diff `pipeline.py` chỉ nằm trong `main()`.
5. Grep toàn repo không thấy topic string bị ghi vào payload Document.

## I. Quy ước giao nộp

- Nhánh: `feat/search-to-id` (từ `claude/sr-agent-pipeline-design-rqtctp`). Commit nhỏ theo task: `T1: ...`, `T2: ...`.
- Push xong mở PR về `claude/sr-agent-pipeline-design-rqtctp`; tiêu đề PR: `D29: tools/search_to_id — cầu nối ngữ nghĩa → ID`.
- PR mô tả phải dán output của 5 lệnh nghiệm thu mục H.
