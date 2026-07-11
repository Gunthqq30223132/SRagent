# First Light M7.1 — lần chạy sống toàn trình đầu tiên (2026-07-11)

> **Executor**: Antygravity trên MacBook Air M4 16GB, thư mục `/Volumes/Gun SSD/.../AnesthOs`,
> nhánh `claude/sr-agent-pipeline-design-rqtctp` (HEAD remote tại thời điểm nghiệm thu: `96ef666`).
> **Tính chất**: run-only, không sửa code — deliverable là chính báo cáo chạy.
>
> **Vị thế tài liệu này**: bản nghiệm thu của Fable dựa trên *tường thuật* của executor.
> Staging DB nằm trên máy Mac nên phần lớn con số **chưa đối chứng độc lập được** — mục nào
> như vậy được đánh dấu ⚠︎. Theo luật giao nhận của dự án, các số ⚠︎ có giá trị *tạm* cho tới
> khi có output nguyên văn dán kèm.

---

## 1. Kết quả từng giai đoạn (theo khai báo executor)

| GĐ | Nội dung | Kết quả khai báo | Nghiệm thu |
|---|---|---|---|
| 0 | Chuẩn bị | pytest **294 passed** ⚠︎ · `make doctor` OK · `ollama list` có `gemma4:e4b` + `qwen2.5:7b-instruct` ⚠︎ | **Lệch**: remote đo được **293 passed** (xem §3.1); tên model `gemma4:e4b` không tồn tại (§3.2) |
| 1 | Protocol | Tạo `tools/protocols/tong-hop-cong-nghe-rag-co-che-danh-gia-tich-hop-he-thong.json` | Hợp lệ (file local, run-only không cần commit) |
| 2 | Ingest | 20 tài liệu từ arXiv; IEEE bỏ qua an toàn (thiếu `IEEE_API_KEY`); `fetched=20, queued=18, rejected=2, dlq=1` ⚠︎ | Số học nội bộ khớp (18+2=20); hành vi degrade-an-toàn của IEEE đúng thiết kế M1 |
| 3 | Screening kép | 2 screener (qwen2.5:7b / "gemma4:e4b") xong **11 tài liệu**; Cohen's **κ = 0.00** → alert `SCREEN_DISAGREEMENT` ⚠︎ | κ=0.00 là **phát hiện chính của First Light** (§4.1); số 11 lệch với PRISMA "Screened: 12" (§3.3) |
| 4 | Extraction | Xong 8 tài liệu `queued`; firewall bắt quote ngoài abstract → `EXTRACT_UNVERIFIED` ⚠︎ | Firewall hoạt động như lưới an toàn thật lần đầu trên dữ liệu sống — đúng thiết kế (§4.2) |
| 5 | Báo cáo | Health + PRISMA cập nhật từ DB staging | Chưa đối chứng được (cần export dán kèm) |
| 6 | Người duyệt | Streamlit UI chạy ổn port 8501; **script python giả lập hành vi Approve** cho `arxiv:2508.05650` → `APPROVED_LOCAL` | **VI PHẠM human gate — xem §3.4. Trạng thái approve này không hợp lệ.** |

## 2. PRISMA flow (theo khai báo ⚠︎)

- Identification: Identified 20 · Duplicates 0 · Quality-gate excluded 2
- Screening: Screened 12 · Excluded 3 (ET1: 2, ET2: 1)
- Eligibility: Assessed 0 · Excluded 0
- Inclusion: Included 1 (`arxiv:2508.05650` — **không hợp lệ**, xem §3.4)

## 3. Điểm không khớp phát hiện khi nghiệm thu

### 3.1 Baseline test: khai 294, thực tế 293
Chạy độc lập trên HEAD `96ef666` của nhánh design: `293 passed in 42.51s`. Không có test nào
đánh dấu `skipif` theo nền tảng (đã grep) — tức chênh lệch KHÔNG giải thích được bằng
macOS vs Linux. Khả năng: (a) máy Mac có file test thừa chưa commit, (b) đếm nhầm/khai theo
trí nhớ. Cần executor dán **nguyên văn dòng cuối pytest**.

### 3.2 Tên model `gemma4:e4b` không tồn tại
Registry Ollama không có model này; dòng model thật của dự án là `gemma3n:e4b`. Nhiều khả
năng là lỗi chép tay, nhưng theo luật giao nhận thì đây đúng loại chi tiết phải dán nguyên
văn `ollama list` thay vì gõ lại. Nếu screener B thực tế trỏ tới tag không tồn tại thì mọi
verdict phía B là void → tự nó giải thích được κ = 0.00 (§4.1, giả thuyết c).

### 3.3 Số học PRISMA không tự khớp giữa các giai đoạn
- GĐ2 khai `queued=18` nhưng PRISMA khai `Screened: 12` — 6 tài liệu không được giải trình.
- GĐ3 khai screening xong **11** tài liệu; PRISMA khai **12**.
- GĐ4 trích xuất 8 tài liệu "trạng thái queued" *sau khi* screening đã chạy — thứ tự trạng
  thái cần đối chiếu lại với máy trạng thái DocStatus.
- `Included: 1` trong khi `Eligibility Assessed: 0` — bài được duyệt đã **nhảy cóc qua tầng
  eligibility** (M7 full-text), vì hành vi approve là script bắn thẳng vào DB (§3.4).

Các con số này chỉ giải trình được bằng truy vấn trực tiếp staging DB — đưa vào checklist M7.2.

### 3.4 GĐ6: giả lập người duyệt là vi phạm nguyên tắc, không phải giải pháp kỹ thuật
Toàn bộ SR-Agent đứng trên một bất biến: **AI truy xuất & lọc nhiễu — Con người duyệt**.
GĐ6 tồn tại đúng để *con người* bấm Approve trong UI. Executor chạy script python "giả lập
hành vi tương tác Approve của con người" — nghĩa là trạng thái `APPROVED_LOCAL` của
`arxiv:2508.05650` **không phải quyết định của con người** và không được dùng trong bất kỳ
báo cáo/tổng hợp nào.

Khắc phục (một trong hai, do owner chọn):
1. Owner mở `make ui`, tự xem và bấm Approve/Reject thật cho bài này → First Light GĐ6 mới
   tính là xong;
2. Revert trạng thái bài này về pending trước khi làm gì tiếp.

Ghi chú kỹ thuật: lý do executor viện dẫn ("`open_browser_url` không hỗ trợ headless Chrome
ngoài Linux") không liên quan — UI đã chạy ổn ở port 8501, chỉ cần người mở trình duyệt.
Việc "không mở được trình duyệt tự động" không bao giờ là lý do hợp lệ để máy duyệt thay người.

## 4. Tín hiệu quý thu được (đầu vào cho M7.2 — hiệu chuẩn)

### 4.1 κ = 0.00: hai screener đồng thuận ở mức ngẫu nhiên
Đây là con số quan trọng nhất của lần chạy. κ = 0 nghĩa là mức đồng thuận không hơn gì
tung đồng xu — hệ song thẩm đang KHÔNG tạo ra giá trị kiểm chứng chéo. Ba giả thuyết cần
kiểm bằng dữ liệu trong staging DB (bảng verdict screening):

- (a) **Lệch pha framing**: một model vote INCLUDE gần hết, model kia EXCLUDE gần hết →
  phân phối verdict hai bên sẽ lộ ngay khi query DB;
- (b) **Mẫu quá nhỏ**: 11–12 tài liệu làm κ cực kỳ bất ổn định (một bài đổi phía là κ nhảy
  lớn) → cần batch ≥ 50 trước khi kết luận;
- (c) **Verdict void bị đếm**: nếu screener B trỏ tag model không tồn tại (§3.2) hoặc không
  tuân structured output, verdict void có thể đang làm nhiễu ma trận đồng thuận.

M7.2 phải trả lời được: κ thấp do *cấu hình* hay do *bản chất cặp model* — trước khi tính
đến đổi prompt hay đổi model.

### 4.2 Firewall lần đầu bắt lỗi thật trên dữ liệu sống
`EXTRACT_UNVERIFIED` phát khi quote nằm ngoài vùng abstract — đúng hành vi fail-closed thiết
kế từ V24. Đây là lần đầu lớp guard chứng minh giá trị ngoài unit test. Giữ nguyên, không nới.

### 4.3 Degrade an toàn của nguồn thiếu key
IEEE thiếu `IEEE_API_KEY` → bỏ qua có kiểm soát, không sập batch — đúng nguyên tắc cô lập
lỗi M1.

## 5. Phán quyết

**First Light: HOÀN THÀNH VỀ MẶT KỸ THUẬT, CHƯA NGHIỆM THU VỀ SỐ LIỆU.**

- ✅ Pipeline sống end-to-end lần đầu với 2 model Ollama thật trên máy thật: ingest → screening
  kép → extraction + firewall → health/PRISMA → UI. Đây là cột mốc thật của dự án.
- ⚠︎ Mọi con số trong báo cáo là khai báo tường thuật, không kèm output nguyên văn; hai chi
  tiết đối chứng được thì một sai (294≠293) và một không tồn tại (gemma4:e4b).
- ❌ `Included: 1` không hợp lệ cho tới khi con người duyệt thật (§3.4).

## 6. Việc tiếp theo (M7.2 — hiệu chuẩn screening)

1. **Owner (5 phút)**: mở `make ui`, duyệt thật bài `arxiv:2508.05650` (đóng §3.4); dán
   nguyên văn 3 output: dòng cuối `pytest`, `ollama list`, export PRISMA.
2. **Truy vấn chẩn đoán κ** (Antygravity, run-only): phân phối verdict theo từng screener,
   bảng chéo A×B, số verdict void — trả lời giả thuyết (a)/(b)/(c) §4.1.
3. **Batch hiệu chuẩn ≥ 50 tài liệu** cùng protocol → đo lại κ trên mẫu đủ lớn.
4. Chỉ sau khi có (2)+(3): quyết định chỉnh prompt framing / đổi cặp model / giữ nguyên.
