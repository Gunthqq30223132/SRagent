# D38 — Thang Full-Text (acquisition ladder) + nối Warehouse (B9)

**Trạng thái:** thiết kế đóng băng 2026-07-19 (PM Fable 5). FL-2 (arXiv PDF)
là bậc 1 và đang thi công theo mandate riêng; D38 đóng băng TOÀN BỘ cái thang
để các bậc sau không phải thiết kế lại.
**Giải quyết:** đường găng số 1 sau FL-1 (0/9 doc có toàn văn) + premortem B9
(warehouse xây xong không ai gọi).

## §0. Nguyên tắc

1. **Fail-closed về chất lượng:** text < 2000 ký tự hoặc bóc lỗi ⇒ KHÔNG ghi
   `full_text` (event FULLTEXT_TOO_SHORT / FULLTEXT_FETCH_FAILED). Thà
   ELIG_ABSTRACT_ONLY trung thực còn hơn eligibility chạy trên rác.
2. **Chỉ nguồn hợp pháp:** arXiv (mở), Europe PMC OA (mở), PDF người dùng tự
   có bản quyền bỏ vào inbox. KHÔNG scrape publisher. PDF chỉ nằm local —
   không bao giờ theo payload ra ngoài (Outbound Interceptor + bất biến #7).
3. **Provenance bắt buộc:** mọi full_text ghi kèm event FULLTEXT_FETCHED với
   detail = `rung=<n> source=<...> chars=<len>` — biết chữ đến từ đâu là điều
   kiện để tin quote trích từ nó.
4. **Một cửa ghi duy nhất:** chỉ `tools/fulltext_fetch.py` được ghi
   `doc.full_text` (upsert `touch=False` — không reset TTL triage). Warehouse
   không tự ý đẩy text vào staging.

## §1. Bốn bậc thang (thử lần lượt, dừng ở bậc đầu thành công)

| Bậc | Nguồn | Điều kiện áp dụng | Trạng thái |
|---|---|---|---|
| 1 | arXiv PDF `arxiv.org/pdf/<id>` | source=arxiv | FL-2 (đang thi công) |
| 2 | Europe PMC OA full-text XML (`/fullTextXML`) — text từ XML, KHÔNG cần PDF | source=europepmc AND isOpenAccess | FL-2.1 |
| 3 | Warehouse lookup: PDF đã có sẵn trong kho BS5 | mọi source; match theo title_normalized (exact sau normalize — cấm fuzzy) | FL-2.2 (§2) |
| 4 | Inbox thủ công `staging/fulltext_inbox/<uid>.pdf` | người tự đặt file (bài trả phí có bản quyền hợp lệ) | FL-2.2 |

Bóc text PDF (bậc 1, 3, 4): tái dùng `extract_text_from_pdf` của
`tools/warehouse/ingest_pdf.py` (pdftotext/mutool subprocess — 0 dep mới).
Bậc 2 bóc từ JATS XML bằng stdlib `xml.etree` (chỉ lấy body text, bỏ ref list).

## §2. Nối Warehouse (bậc 3) — thiết kế API đọc

Warehouse hiện chỉ có `retrieve()` trả CHUNK theo query (vai trò RAG). Bậc 3
cần đọc NGUYÊN VĂN một tài liệu:
- Thêm `tools/warehouse/read_doc.py::get_document_text(title_normalized, db_path) -> str | None`:
  match bảng docs của warehouse theo `title_normalized` (dùng CHÍNH
  `normalize_title` của `sr_agent/models/schemas.py` — một định nghĩa chuẩn
  hóa duy nhất toàn hệ); lấy mọi chunk của doc, sắp theo (page, chunk_index),
  nối bằng "\n" — KHÔNG khử trùng lặp, không tóm tắt, nguyên văn.
- Match nhiều hơn 1 doc warehouse ⇒ trả None + log warning (nhập nhằng =
  không dùng — fail-closed; con người xử lý qua bậc 4 nếu cần).
- Chiều ngược (SR PDF → warehouse) KHÔNG nằm trong D38: kho tri thức cá nhân
  và corpus SR có vòng đời khác nhau; trộn tự động = lặp lại lỗi trộn hai
  vòng đời (bài học B4). Ai muốn đưa PDF SR vào kho thì chạy ingest warehouse
  thủ công như hiện tại.

## §3. CLI & tích hợp orchestrator

- `python -m tools.fulltext_fetch --limit N [--run <id>] [--rungs 1,2,3,4]`
  — chọn doc: `status='queued'` + SCREEN_INCLUDED (run-scoped khi D36 có,
  event-scoped khi chưa) + `full_text IS NULL`.
- Orchestrator (sau D36): phase AUTO mới `fulltext` giữa `screen` và
  `eligibility` — tự nhận diện module như mọi phase (`is_available()`),
  nghĩa là merge D38 xong đồ thị tự nối, không sửa gì thêm:
  `ingest → screen → fulltext → eligibility → rob → extract → ⛔ → consensus`.
- Idempotent: doc đã có full_text không bao giờ bị fetch đè (muốn refetch:
  người xóa full_text bằng tay — không có cờ --force, tránh tay nhanh hơn não).

## §4. Test offline bắt buộc (mở rộng `tests/test_fulltext_fetch.py` của FL-2)
(a) thang dừng ở bậc đầu thành công (mock bậc 1 fail → bậc 2 ăn); (b) mọi bậc
fail ⇒ không ghi + đủ event từng bậc; (c) bậc 3: match 1 doc → text đúng thứ
tự chunk; match 2 doc → None; (d) bậc 4: file inbox đúng uid được ăn, sai tên
bỏ qua; (e) TOO_SHORT không ghi; (f) idempotent; (g) touch=False (TTL triage
không reset). Ratio ≥ 2.

## §5. Ngoài phạm vi
Unpaywall/CORE API (cần API key + chính sách riêng — cân nhắc sau khi 4 bậc
chạy) · OCR PDF scan (mutool đã cover PDF text-layer; scan y văn cổ = ca hiếm,
ghi nhận chờ nhu cầu thật) · tự động ingest chiều SR→warehouse (bị bác, §2).
