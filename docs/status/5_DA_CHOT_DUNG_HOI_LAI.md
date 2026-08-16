# 5. Những gì ĐÃ chốt — đừng hỏi lại

> **Cập nhật**: 2026-08-16 · SRagent `a11d14b`
> Bản đầy đủ kèm lý do: `docs/DECISIONS.md` trong repo.
> Tài liệu này tồn tại vì đã từng xảy ra chuyện "chốt rồi mà không tìm lại được", dẫn tới
> lập kế hoạch sai suốt mấy vòng.

| # | Quyết định | Nội dung |
|---|---|---|
| 1 | **Phạm vi y sinh** | ✅ **ĐÃ MỞ**. SR-Agent được xử lý chủ đề y khoa/lâm sàng. Ranh giới còn giữ: ngữ liệu là **bài báo đã xuất bản**, KHÔNG xử lý dữ liệu bệnh nhân thật |
| 2 | **Mức chất lượng** | "Chuẩn Q1" là **mức chất lượng mong muốn**, KHÔNG nhằm nộp tạp chí. ⇒ **bỏ** đăng ký PROSPERO; **giữ** PRISMA, đánh giá sai lệch, GRADE |
| 3 | **Nguồn dữ liệu** | Ưu tiên **miễn phí**: PubMed + Cochrane CENTRAL. **Loại Embase** vì cần trả phí. Giữ IEEE + arXiv |
| 4 | **Cách tổng hợp** | Ưu tiên **meta-analysis** (bậc chứng cứ cao hơn). Lui về tổng hợp mô tả chỉ khi các nghiên cứu không đủ đồng nhất để gộp |
| 5 | **Ngôn ngữ bản thảo** | **Song ngữ Anh – Việt**. Tiếng Anh là bản chuẩn. Hai bản dùng chung một bộ số |
| 6 | **Chủ đề đầu tiên** | **Quản lý chống đông trước, trong và sau mổ** |

## Ba nhầm lẫn đã xảy ra — đừng lặp lại

**1. Gộp hai sản phẩm làm một.** SR-Agent (hệ thống viết tổng quan) và AnesthOS-app (ứng dụng
lâm sàng) là hai thứ khác nhau. Từng có một kế hoạch 21 hạng mục bị sai phạm vi vì nhầm chỗ này.

**2. Tưởng phần lõi cần viết lại cho y khoa.** Không cần. Lõi hệ thống vốn **mù chủ đề** —
thêm nguồn y khoa chỉ là thêm một bộ nối và vài dòng cấu hình, không phải xây lại.

**3. Tưởng phạm vi y sinh chưa mở.** Quyết định đã tồn tại trong repo AnesthOS từ trước nhưng
chưa bao giờ ghi ngược về repo SR-Agent. Nay đã ghi cả hai nơi.
