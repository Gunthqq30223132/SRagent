# Audit toàn hệ SR-Agent — phán quyết Production-Readiness (2026-07-12)

> Auditor: Fable (Principal-level review, zero-trust). Trạng thái audit: HEAD design
> `23b6e72`, **303 passed** đo độc lập, 2 gate PASS. Mọi phát hiện dưới đây có bằng
> chứng lệnh/file cụ thể — không suy đoán.

## Executive Summary — **NO-GO**

Hệ chưa đủ điều kiện "production" trên CẢ HAI trục:

1. **Trục quản trị**: các cột mốc được khai trong đề bài audit ("M7.3 đã tích hợp và
   chạy staging", "các file tồn đọng đã commit an toàn", "304/304 test",
   "human_review_checklist.md đã ban hành", "protocol gây mê đã thiết lập") —
   **không tồn tại trên remote** tại thời điểm audit. `docs/protocols/` không có,
   protocol thuốc giãn cơ không có, notion_page.py chưa có song ngữ, staging.py chưa
   có check_same_thread. Theo luật giao nhận của dự án: chưa có trên remote = chưa
   xảy ra. Đồng thời kênh push-thẳng-nhánh-design vẫn mở (bằng chứng: `02552ee`
   "Sync backup" đã chép nhầm CLAUDE.md của app Next.js vào repo Python này).
2. **Trục kỹ thuật**: 1 lỗ hổng P1 bảo mật thật (Notion publish nằm NGOÀI vùng phủ
   Outbound Interceptor), cờ an toàn lâm sàng chỉ tồn tại trên giấy, và κ=1.0 staging
   là thống kê thoái hóa không được phép dùng làm bằng chứng "production-ready"
   (κ chính thức: **0.9042** — hồ sơ `docs/runs/2026-07-11-m72-calibration.md`).

"Production" đúng nghĩa của hệ này = một SR thật chạy trọn vòng với người duyệt thật.
Điều kiện cần: đóng các mục P0/P1 dưới đây + tái hiệu chuẩn screener trên corpus đúng
chuyên ngành trước khi chạy protocol gây mê.

## Critical (P0/P1)

### P0-1 · Kênh push thẳng nhánh design của script sync (quản trị/chuỗi cung ứng)
Script `anesthos-save`/`anesthos-sync.sh` auto-commit-push lên nhánh design, vượt mặt
toàn bộ chuỗi PR→CI→review. Hậu quả đã xảy ra: `02552ee` đưa CLAUDE.md sai stack vào
repo (đã sửa ở `23b6e72`), suýt kèm cả uv.lock/scripts không review. Khắc phục:
(a) script sync trỏ về nhánh `backup/station-sync`; (b) owner bật branch protection
trên GitHub cho nhánh design: require PR + require status check `test`.

### P0-2 · Khoảng cách khai–thực của phiên "Teamwork Multi-Agent"
Toàn bộ deliverable khai trong đề bài audit chỉ nằm trên máy Mac (uncommitted/unpushed).
Trong đó `check_same_thread=False` là thay đổi ĐÃ BỊ BÁC ở audit trước (PR #13 fix
gốc rồi; nới cờ này ở core store che race condition) — nếu nó được "commit an toàn"
thật thì một quyết định review đã bị đảo ngược không qua review. Khắc phục: tách 3
thay đổi thành PR riêng — test-fix (nhận), Notion song ngữ (nhận có điều kiện, xem
Clinical Safety), check_same_thread (bác — đã có fix gốc).

### P1-1 · Notion publish nằm ngoài vùng phủ Outbound Interceptor
`assert_sanitized` hiện chỉ được gọi ở `tools/synthesis/provider.py` và
`tools/evidence/snowball.py`. **`sr_agent/publish/notion_page.py` — luồng outbound
THƯỜNG XUYÊN duy nhất mang nội dung tài liệu — không qua chốt chặn nào.** Đây chính
là kịch bản "người dùng mở rộng đầu vào sai cách" trong đề bài: nếu ai đó ingest
tài liệu nội bộ bệnh viện, đường rò đầu tiên là nút Approve→Notion. Khắc phục
(PR nhỏ + tests): quét payload trước khi gọi API Notion; vì paper thật hay chứa email
tác giả (rule EMAIL sẽ bắn đúng thiết kế NĐ13), dùng `redact()` + hiển thị cảnh báo
trong UI thay vì assert cứng làm gãy luồng duyệt.

### P1-2 · κ=1.0 staging là thống kê thoái hóa + audit trail staging đã bị xóa tay
Include-rate 100% cả hai screener trên corpus không có negative ⇒ p_e=1, nhánh
degenerate của `compute_cohen_kappa` trả 1.0 — không đo năng lực phân biệt; event
`SCREEN_DEGENERATE` lẽ ra PHẢI phát (2 event) nhưng không được báo cáo. Đồng thời
lịch sử screening staging (chứng cứ κ=0.00 của First Light) bị reset tay — vi phạm C3.
Khắc phục: κ đối ngoại duy nhất là 0.9042; xác nhận có/không backup DB trước reset,
ghi chú vào hồ sơ run; từ nay reset = DB/namespace mới, không DELETE.

## Architectural Weaknesses (P2)

1. **Encoding RIS/BibTeX phá vỡ cô lập lỗi ở cấp file**: `parse_ris` đọc
   `encoding="utf-8-sig"` strict — MỘT file export hỏng encoding (thư viện y khoa
   xuất latin-1/UTF-16 không hiếm) ⇒ UnicodeDecodeError giết cả batch import, trái
   nguyên tắc per-record isolation của M1. Fix: try/except per-file trong
   `parse_directory` + ghi DLQ, thử fallback encoding có kiểm soát.
2. **Fuzzy-title 93 trên tiêu đề lâm sàng công thức hóa = nguy cơ gộp nhầm im lặng**:
   tiêu đề RCT gây mê rất giống nhau ("Effect of rocuronium... randomized trial").
   Bài học đã có ngay trong test benchmark (corpus template-đồng-nhất tự gộp nhầm ở
   cutoff 93). Mất một nghiên cứu vì dedup nhầm = sai lệch kết quả SR — đây đồng thời
   là lỗi an toàn lâm sàng. Fix: fuzzy-merge đòi thêm đồng thuận metadata (năm ±1,
   tác giả đầu) HOẶC mọi cặp fuzzy_title trong `dup_log` phải hiện ở UI cho người
   xác nhận mẫu (dữ liệu đã có sẵn trong DedupReport).
3. **SQLite không WAL, không busy_timeout**: hai tiến trình (pipeline launchd + UI
   Streamlit) ghi cùng lúc sẽ ăn `SQLITE_BUSY` — lỗi sẽ xuất hiện đúng lúc demo thật.
   Fix một PR nhỏ có review: `PRAGMA journal_mode=WAL` + `busy_timeout=5000` trong
   `StagingStore.__init__` — KHÔNG phải `check_same_thread=False`.
4. **Rule CCCD (12 chữ số liền) và EMAIL sẽ false-positive trên văn liệu thật** khi
   interceptor phủ đường publish — chấp nhận theo triết lý fail-closed, nhưng phải có
   đường `redact()` + xác nhận người, nếu không người dùng sẽ học thói tắt guard.
5. **Snowball/dedup trước dữ liệu nhiễu**: KHÔNG có nguy cơ vòng lặp vô hạn theo cấu
   trúc (trần max_api_calls/max_total/depth + saturation + seen-set; node lỗi HTTP bị
   cô lập). Điểm yếu còn lại: `citedPaper` thiếu externalIds → uid rơi về title-hash
   → dedup yếu hơn với record S2 nghèo metadata — chấp nhận được, ghi nhận.

## Clinical Safety Gaps

1. **`_human_review_required: true` là cam kết trên giấy**: không một dòng code nào
   đọc cờ này (grep toàn repo: 0 điểm thực thi). Fallback kỹ thuật bắt buộc: chốt
   thực thi tại publish/export — tài liệu thuộc protocol mang cờ này chỉ được
   publish/export khi tồn tại event APPROVED do người tạo từ UI; thiếu ⇒ chặn cứng.
   (Hạ tầng có sẵn: bảng events + human gate UI — chỉ thiếu phép kiểm tra nối hai đầu.)
2. **`human_review_checklist.md` chưa tồn tại trong repo** — "đã ban hành" là khai
   khống tại thời điểm audit. Khi viết thật, checklist phải hiện NGAY TRONG UI ở
   màn Approve (bác sĩ không mở file .md rời), mỗi mục tick được log thành event.
3. **Dịch song ngữ abstract = nội dung phái sinh chưa kiểm chứng**: bản dịch máy
   thuật ngữ gây mê (tên thuốc, liều, đơn vị) sai một chữ là đổi nghĩa lâm sàng.
   Điều kiện nhận PR song ngữ: nhãn cố định "Bản dịch máy — chỉ tham khảo, đối chiếu
   bản gốc"; bản dịch KHÔNG BAO GIỜ vào bất kỳ đường verification/quote/anchor nào;
   trường lưu tách khỏi abstract gốc.
4. **κ hiệu chuẩn không tự chuyển miền**: 0.9042 đo trên corpus RAG/CS tiếng Anh.
   Protocol thuốc giãn cơ (gây mê, thuật ngữ khác hẳn) phải qua đúng harness hiệu
   chuẩn (≥50 doc đúng miền + ≥15 mồi, ngưỡng spec §3) TRƯỚC khi chạy SR thật.
   Không có ngoại lệ — đây là điều kiện Go quan trọng nhất về mặt phương pháp luận.
5. **Toàn hệ chỉ được phép sản xuất "tư liệu nghiên cứu cho người duyệt"** (D30-S1):
   evidence table, PRISMA, tổng hợp có trích dẫn — không phải khuyến cáo lâm sàng.
   Mọi artifact xuất ra nên mang footer cố định nêu rõ điều này.

## Recommended Remediation Plan (thứ tự thi hành)

| # | Việc | Ai | Điều kiện đóng |
|---|---|---|---|
| 1 | Branch protection nhánh design (require PR + CI) | Owner (5 phút, GitHub Settings) | Push thẳng bị từ chối |
| 2 | Sync script trỏ `backup/station-sync` | Antigravity (B0 — từng bước, dán diff) | Không còn "Sync backup" trên design |
| 3 | 3 file uncommitted → 3 PR riêng (nhận/bác như P0-2) | Antigravity đề xuất, Fable review | PR URLs + CI xanh |
| 4 | Interceptor phủ Notion publish (redact + UI warning) + tests | Fable | PR merged |
| 5 | WAL + busy_timeout; RIS per-file isolation + DLQ; guard fuzzy-merge metadata | Fable | PR merged, 2 gate PASS |
| 6 | Chốt thực thi `_human_review_required` + checklist trong UI | Fable spec → Antigravity | Test chặn publish khi thiếu APPROVED |
| 7 | Viết thật `human_review_checklist.md` (10 điểm, bác sĩ duyệt nội dung) | Owner + Fable | File trong repo, hiện ở UI |
| 8 | Tái hiệu chuẩn screener trên corpus gây mê + mồi | Antigravity (B2) | Bảng ngưỡng §3 ĐẠT trên miền mới |
| 9 | Nợ cũ: duyệt thật `arxiv:2508.05650`; xác nhận backup staging trước reset | Owner / Antigravity | Event APPROVED thật / ghi chú hồ sơ |

Ghi chú phạm vi: dự án OmniRoute tạm dừng theo chỉ đạo owner 2026-07-12 — các mục
R1–R5 của DEV-STATION-01 đóng băng, không tính vào kế hoạch trên.
