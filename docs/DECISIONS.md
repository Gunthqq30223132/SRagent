# Sổ quyết định dự án SR-Agent

> **Tại sao có tài liệu này**: các quyết định trước đây nằm rải trong spec, git log, và hội
> thoại — dẫn tới tình trạng "đã chốt rồi mà không tìm lại được". Từ nay MỌI quyết định
> phạm vi/kiến trúc ghi ở đây, **có tên gọi bằng lời**, mã số chỉ là phụ.
>
> Quy ước: mỗi mục có **Tên gọi** (dùng khi nói chuyện) và *mã* (dùng khi tham chiếu trong code/spec).

---

## ĐÃ CHỐT

### 1. Mở phạm vi y sinh — *mã cũ: D30-S1*
**Chốt ngày**: 2026-08-16 · **Người chốt**: chủ dự án (Gun)

SR-Agent **được phép** xử lý chủ đề và tài liệu y sinh/lâm sàng.

- **Thay thế** ràng buộc CS-only tại `docs/HANDOVER.md:23` và `docs/specs/D30-...md:12-13`.
- **Bằng chứng đã có từ trước**: `AnesthOS-app/README.md:9,48,51` gọi `sr-agent` là
  *"autonomous clinical AI agent"* và là consumer của Clinical Engine. Quyết định đã tồn
  tại ở repo AnesthOS nhưng chưa từng ghi ngược về repo này — đó là lý do nó "mất tích".
- **Mở khoá**: nguồn y khoa, rubric y khoa, Risk of Bias, GRADE, chủ đề lâm sàng.
- **KHÔNG mở**: xử lý dữ liệu bệnh nhân thật (PHI). Ngữ liệu là **bài báo đã xuất bản**.
  Ranh giới này giữ nguyên và cần giữ tường minh.

### 2. Mức chất lượng mục tiêu: "chuẩn Q1" là mức chất lượng, KHÔNG nộp tạp chí
**Chốt ngày**: 2026-08-16

Bài systematic review viết ra nhắm **đạt mức chặt chẽ của tạp chí Q1**, nhưng không nhằm
nộp đăng thực tế.

- **Hệ quả — BỎ**: đăng ký PROSPERO (chỉ cần khi nộp thật).
- **Hệ quả — GIỮ**: PRISMA 2020 (sơ đồ dòng + checklist 27 mục), sàng lọc kép + κ,
  Risk of Bias, GRADE, chiến lược tìm kiếm tái lập được. Đây là cái tạo ra chất lượng thật.

### 3. Nguồn dữ liệu: ưu tiên miễn phí
**Chốt ngày**: 2026-08-16

| Nguồn | Trạng thái | Lý do |
|---|---|---|
| **PubMed / MEDLINE** | ✅ dùng | Miễn phí, API E-utilities ổn định, dialect MeSH đã đặc tả tại `D30:102` |
| **Cochrane CENTRAL** | ✅ dùng | Miễn phí phần tra cứu; nguồn RCT tốt nhất cho câu hỏi can thiệp |
| **Embase** | ❌ loại | Cần license trả phí |
| IEEE, arXiv | ✅ giữ | Đã chạy; hữu ích cho chủ đề giao thoa kỹ thuật |

**Ghi vào Limitations của bản thảo**: thiếu Embase ⇒ có thể bỏ sót tài liệu châu Âu và
tài liệu dược. Đây là hạn chế phải khai báo, không phải giấu.

### 4. Ưu tiên meta-analysis hơn narrative synthesis
**Chốt ngày**: 2026-08-16

Khi dữ liệu cho phép gộp, **ưu tiên meta-analysis** vì bậc chứng cứ cao hơn.
Narrative synthesis là phương án lui khi không đạt điều kiện đồng nhất.

- **Điều kiện gác cổng** (không được bỏ qua): đồng nhất về lâm sàng (population,
  intervention, comparator) và về phương pháp (thiết kế nghiên cứu, cách đo outcome).
  Gộp nghiên cứu không đồng nhất cho ra con số đẹp nhưng **sai khoa học** — đây là lỗi
  nặng nhất mà reviewer bắt được.
- **Kéo theo khối lượng**: random/fixed effects, I², forest plot, funnel plot, Egger's test.

### 5. Ngôn ngữ bản thảo: song ngữ Anh — Việt
**Chốt ngày**: 2026-08-16

Bản thảo sinh ra ở **cả hai ngôn ngữ**, tiếng Anh là bản chuẩn (thuật ngữ khoa học),
tiếng Việt là bản song hành.

- **Bất biến bắt buộc**: hai bản phải dùng **cùng một bộ số** từ tầng extraction. Dịch
  không bao giờ được sinh lại số. Số là slot, chữ là bản dịch.

### 6. Chủ đề bài SR đầu tiên
**Chốt ngày**: 2026-08-16

> **"Tiếp cận quản lý chống đông trước, trong và sau mổ"**
> (Perioperative anticoagulation management)

- Chủ đề lâm sàng thuần túy ⇒ xác nhận quyết định #1.
- **Lưu ý kỹ thuật quan trọng**: chủ đề này chứa dày đặc **liều thuốc, ngưỡng INR, và
  khoảng thời gian** (ngừng thuốc trước mổ bao nhiêu giờ, bắc cầu heparin, thời điểm dùng
  lại). Nghĩa là bản thảo sẽ chứa số lâm sàng trích từ nghiên cứu ⇒ tường lửa số
  (`tools/guard/firewall.py`) **phải bổ sung cả đơn vị lâm sàng lẫn đơn vị thống kê**
  (mg, mcg, IU, mL, giờ, INR, OR, RR, HR, 95% CI, p, I²). Hiện chưa có đơn vị nào trong số đó.

---

## CHỜ CHỐT

| # | Tên gọi | Vì sao cần chốt |
|---|---|---|
| 7 | **Ngoại lệ vùng cấm để tách kho** (*mã: D33 §5*) | Tách corpus khỏi hàng đợi buộc phải sửa `schemas.py`, `pipeline.py` — đang bị `gate_m6.sh` khoá |
| 8 | **Protocol sửa thì tạo review mới hay sửa tại chỗ** (*mã: D33 Q-1*) | Bất biến nền tảng của schema; sửa sau rất đắt |
| 9 | **Trần lưu giữ kho** (*mã: D33 Q-2*) | SQLite một file, corpus tăng đơn điệu |
| 10 | **Vị trí tài liệu kiểm toán lâm sàng** (*D32 + probe*) | Sau quyết định #1 thì vấn đề này gần như tự tan, xem ghi chú bên dưới |

> Ghi chú mục 10: quyết định #1 đã mở phạm vi y sinh, nên việc D32 và
> `docs/audit/probe_clinical_gaps.py` nằm trong repo SRagent **không còn là vi phạm**.
> Chỉ còn câu hỏi tổ chức thư mục, không còn là câu hỏi tuân thủ.
