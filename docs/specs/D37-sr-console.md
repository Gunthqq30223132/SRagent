# D37 — SR Console: phân xử escalation + cổng consensus (BS3.1 + BS4.1)

**Trạng thái:** thiết kế đóng băng 2026-07-19 (PM Fable 5). Phụ thuộc D36
(run_id). **Đây là nơi duy nhất trong hệ con người tạo các trạng thái mà
orchestrator/BS4 chỉ được ĐỌC** — hiện thân code của bất biến CLAUDE.md #6.

## §0. Vì sao cần console riêng (không nhét vào ui/app.py)

`ui/app.py` phục vụ vòng đời triage (Approve→Notion/Reject) — đã hiệu chuẩn,
có sẹo thread-safety riêng, và người dùng nó với tâm thế "duyệt bài lẻ".
Phân xử SR cần tâm thế khác (so hai rater, đọc quote, quyết định có hệ quả
xuống consensus) và các nút của nó tạo trạng thái pipeline. Trộn hai tâm thế
một chỗ = mời gọi bấm nhầm. File riêng `ui/sr_console.py`, lệnh `make sr-ui`,
cùng pattern mở connection theo rerun (sẹo cross-thread 2026-07-11).

## §1. Cấu trúc: 3 tab, chọn run ở sidebar

Sidebar: dropdown run (từ `sr_runs`, mặc định run OPEN mới nhất) + banner
khóa-ghi nếu lockfile single-writer đang tồn tại (D39 §3 — console thành
read-only khi orchestrator đang chạy).

### Tab 1 — Phân xử RoB (BS3.1)
- Danh sách doc `ROB_ESCALATED` của run (từ events run-scoped), sắp theo:
  có `ROB_PERTINENCE_FLAG` trước (xem §4), rồi theo rubric_score giảm dần.
- Mỗi doc: study_type A vs B; bảng domain — mỗi hàng: verdict A + quote A |
  verdict B + quote B | radio người chọn {Low, Some concerns, High, VOID}.
  Quote hiển thị kèm kết quả verify_quote (tái dùng import, không viết lại).
- Nút **Lưu phán định**: (1) INSERT `rob_assessment` agent='human',
  model='human', verdict từng domain người chọn; (2) `__overall__` tính bằng
  `compute_rob2_overall`/`compute_minors_overall` **import từ rob_run** —
  người chọn domain, MÁY tính overall tất định (người không được tự đặt
  overall, tránh sai thuật toán RoB2); (3) event `ROB_COMPLETED`
  (run_id truyền tường minh, detail="human adjudication").
- Bất biến: chỉ đường UI này tạo `agent='human'`. VOID người chọn giữ nguyên
  ngữ nghĩa VOID (doc rơi khỏi consensus theo weighting BS4 — không rửa).

### Tab 2 — Escalation khác (read-only + đánh dấu đã xem)
- `ELIG_ESCALATED` docs, batch-flags `SCREEN_KAPPA_LOW`/`SCREEN_DEGENERATE`
  của run. v1 chỉ hiển thị + nút "đã xem" (event `ESCALATION_ACKED`) — phân
  xử eligibility bằng tay là hiếm; đừng xây UI cho ca chưa gặp (YAGNI có
  chủ đích, ghi lại để mở rộng khi FL cho thấy tần suất thật).

### Tab 3 — Run dashboard + CỔNG CONSENSUS (BS4.1)
- Funnel per-run từ events (fetched → screened → elig → rob → extracted) +
  PRISMA preview (`prisma_report --run`).
- Đếm nghĩa vụ còn nợ: N escalation chưa phân xử (ROB_ESCALATED chưa có
  ROB_COMPLETED sau nó), M quote unverified.
- **Nút "✅ Chốt tập bằng chứng — cho phép tổng hợp"**: chỉ ENABLE khi
  N == 0 (điều kiện tất định, hiển thị lý do khi disable). Bấm (kèm checkbox
  xác nhận) ⇒ event `CONSENSUS_APPROVED` (run_id tường minh) + sr_runs.state
  = CONSENSUS_READY. Đây là trạng thái mà gate `consensus_review` của
  orchestrator đọc (D36 §3).
- Nút "⛔ Hủy run" ⇒ state ABANDONED + lý do bắt buộc.

## §2. Bất biến CỨNG
1. Console KHÔNG gọi LLM, KHÔNG chạy stage — chỉ đọc DB + ghi phán định người.
2. Không đường code nào ngoài callback nút Tab 3 ghi `CONSENSUS_APPROVED`;
   không CLI tương đương (cấm scriptable — bất biến #6).
3. Overall RoB luôn do pure function tính từ domain người chọn (§1 Tab 1).
4. Mọi write vô hiệu khi lockfile single-writer tồn tại (D39).

## §3. Test offline bắt buộc (`tests/test_sr_console_logic.py`)
Logic tách khỏi Streamlit thành module thuần (`ui/console_logic.py`) để test
không cần UI runtime — pattern build_page_payload của notion_page:
(a) danh sách escalation đúng run + đúng thứ tự; (b) lưu phán định ghi đủ
rows + overall tất định + event run-scoped; (c) điều kiện enable nút consensus
(N>0 ⇒ False); (d) approve ghi event + state đúng run; (e) abandoned thả
miễn trừ (phối test với D36); (f) VOID người chọn ⇒ overall VOID.

## §4. Phụ lục — Pertinence lint (giảm tải người, đóng một phần FL-1 F4)

FL-1 F4: quote đúng-nguyên-văn nhưng vô nghĩa với domain (quote chain-of-thought
gán cho "randomization") — verify_quote không bắt được vì nó chỉ chứng minh
NGUỒN GỐC. Không sửa được bằng verification (cấm cosine/fuzzy — bất biến #2);
sửa bằng **xếp hàng ưu tiên cho người**:
- Protocol JSON thêm khối tùy chọn:
  `"rob_hints": {"d1_randomization": ["random", "allocat", "sequence"], ...}`
  — ngữ nghĩa miền nằm trong PROTOCOL, core giữ topic-blind (bất biến #3).
- `rob_run` sau khi verify_quote pass: nếu domain có hints và quote (casefold)
  không chứa BẤT KỲ stem nào (substring exact, không fuzzy) ⇒ event
  `ROB_PERTINENCE_FLAG` (informational — KHÔNG đổi verdict, KHÔNG VOID).
- Console Tab 1 dùng flag này để xếp doc lên đầu hàng phân xử.
- Mặc định không có `rob_hints` ⇒ tính năng tắt hoàn toàn (opt-in per protocol).
- Test: quote thiếu mọi stem ⇒ flag; có ≥1 stem ⇒ không flag; không hints ⇒
  không flag; flag không ảnh hưởng verdict/overall.

## §5. Ngoài phạm vi
Sửa verdict screening bằng tay (chưa có ca cần) · phân xử consensus-claim
(đó là đọc báo cáo BS4) · auth/multi-user (single-user local-first).
