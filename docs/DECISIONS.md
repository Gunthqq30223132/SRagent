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

### 7. Kiến trúc: SR-Agent là BỘ MÁY SINH CHỨNG CỨ của AnesthOS
**Chốt ngày**: 2026-08-23

> AnesthOS đưa ra khuyến cáo lâm sàng. Khuyến cáo phải có chứng cứ.
> **Chứng cứ đến từ SR-Agent.** SR-Agent tách riêng KHÔNG phải vì nó là sản phẩm
> khác, mà vì nó **tái dùng được cho mọi lĩnh vực** — đổi nguồn tham khảo là có
> một hệ tri thức hệ thống cho bất kỳ vấn đề nào.

- **Đính chính khung hiểu cũ**: các tài liệu trước mô tả "hai sản phẩm riêng biệt".
  Sai về quan hệ. Đúng là: **một chuỗi giá trị** — SR-Agent (sinh chứng cứ) nuôi
  AnesthOS (ra khuyến cáo). Tách repo là quyết định kỹ thuật để tái dùng, không phải
  ranh giới sản phẩm.
- **Hệ quả trực tiếp lên thiết kế**: lõi SR-Agent phải **mù lĩnh vực**. Mọi thứ đặc
  thù y khoa (nguồn PubMed, đơn vị lâm sàng, bậc chứng cứ) phải nằm ở tầng cắm thêm,
  không được ngấm vào lõi. Đây là lý do `gate_m6.sh` có luật cấm rò thuật ngữ lĩnh
  vực vào `sr_agent/` — luật đó giờ có căn cứ kiến trúc, không chỉ là quy ước.
- **Thứ tự ưu tiên đi kèm**: hoàn thiện SR-Agent chạy thật trước. Lớp A/B/C của
  AnesthOS **chỉ bộc lộ điểm yếu khi có chứng cứ thật chảy vào** — thiết kế thêm
  lúc chưa chạy là đoán.

### 8. Mở khóa danh sách nguồn — bỏ ràng buộc 2 nguồn
**Chốt ngày**: 2026-08-23 · *(thay thế mục "ngoại lệ vùng cấm" đang chờ)*

> Cho phép **tất cả** các nguồn. `config.py` không còn khóa cứng arXiv + IEEE.

- **Trước**: `Document.source` là `Literal["ieee","arxiv"]`, `ID_PATTERNS` là hằng số.
  Thêm một nguồn = sửa mã lõi = đụng vùng cấm. Ràng buộc này sinh ra ở chặng M0-M2
  để giữ staging đồng nhất trong lúc dựng pipeline; nó đã xong vai trò.
- **Sau**: sổ đăng ký mở qua `config.register_source()`. Nguồn tự khai quy tắc ID và
  tier của mình tại module định nghĩa fetcher.
- **Ranh giới còn giữ** (mở khóa không phải bỏ kiểm soát):
  - Nguồn **đã đăng ký** → kiểm quy tắc ID nghiêm ngặt, dùng tier khai báo.
  - Nguồn **chưa đăng ký** → vẫn chạy, nhưng nhận `UNKNOWN_SOURCE_TIER = 5` (hạng
    thấp nhất). Chưa thẩm định thì không được hưởng uy tín — mặc định thận trọng.
  - `source` rỗng vẫn bị từ chối: tài liệu không truy vết được nguồn thì vô giá trị.
- **Kiểm chứng**: 266 test xanh; `ieee` vẫn bắt buộc 8 chữ số, `arxiv` vẫn bắt buộc
  tiền tố — mở khóa không làm lỏng nguồn cũ.

---

## CHỜ CHỐT

| # | Tên gọi | Vì sao cần chốt |
|---|---|---|
| 8 | **Protocol sửa thì tạo review mới hay sửa tại chỗ** (*mã: D33 Q-1*) | Bất biến nền tảng của schema; sửa sau rất đắt |
| 9 | **Trần lưu giữ kho** (*mã: D33 Q-2*) | SQLite một file, corpus tăng đơn điệu |
| 10 | **Vị trí tài liệu kiểm toán lâm sàng** (*D32 + probe*) | Sau quyết định #1 thì vấn đề này gần như tự tan, xem ghi chú bên dưới |

> Ghi chú mục 10: quyết định #1 đã mở phạm vi y sinh, nên việc D32 và
> `docs/audit/probe_clinical_gaps.py` nằm trong repo SRagent **không còn là vi phạm**.
> Chỉ còn câu hỏi tổ chức thư mục, không còn là câu hỏi tuân thủ.
