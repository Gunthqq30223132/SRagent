# 2. Tiến độ hiện tại

> **Cập nhật**: 2026-08-16 · SRagent `a11d14b` · AnesthOS-app `56f5a87`
> Con số dưới đây đo từ mã nguồn thật, không phải ước lượng.

## SR-Agent

**Phần thu thập dữ liệu: đã chạy được** — 4.801 dòng Python, 182 test pass.

| Hạng mục | Trạng thái |
|---|---|
| Thu thập từ IEEE + arXiv | ✅ chạy được |
| Gỡ trùng, chấm điểm chất lượng, bóc tách cấu trúc bài báo | ✅ chạy được |
| Lưu trữ + hàng đợi duyệt + giao diện duyệt | ✅ chạy được |
| Sàng lọc kép 2 AI + đo độ đồng thuận | ✅ chạy được |
| Trích xuất dữ liệu kèm trích dẫn nguyên văn | ✅ chạy được |
| Sơ đồ PRISMA | ✅ chạy được |
| **Lần chạy sống đầu tiên trên máy thật** | ❌ **CHƯA TỪNG CHẠY** |

**Phần viết bài tổng quan: còn thiếu nhiều.**

| Cần cho bài đạt mức Q1 | Trạng thái |
|---|---|
| Nguồn y khoa (PubMed, Cochrane) | ❌ chưa có |
| Đánh giá nguy cơ sai lệch của từng nghiên cứu | ❌ chưa có |
| Xếp hạng độ chắc chắn của bằng chứng (GRADE) | ❌ chưa có |
| Gộp số liệu định lượng (meta-analysis) | ❌ chưa có |
| Bảng kiểm PRISMA 27 mục | ❌ chưa có |
| Sinh bản thảo song ngữ Anh–Việt | ❌ chưa có |

**Ước lượng thô: phần thu thập ~70%, phần viết bài ~35%.**

## Vấn đề kỹ thuật đã phát hiện và ĐÃ SỬA

- Cổng kiểm tra chất lượng code trước đây **báo đạt giả** — nó trỏ vào một nhánh git đã bị
  xoá nên âm thầm bỏ qua mọi kiểm tra rồi vẫn in "PASSED". Đã sửa thành chặn cứng.
- Bộ lọc chống bịa số liệu có lỗ: số nhỏ mượn được chữ số của số lớn (`9.9%` được coi là
  hợp lệ vì nguồn có `99.9%`). Đã sửa, kèm 6 test hồi quy.

## Vấn đề đã phát hiện nhưng CHƯA SỬA

- **Kho dữ liệu đang tự xoá sau 72 giờ** — mâu thuẫn với mục tiêu lưu trữ lâu dài.
  Đã có thiết kế sửa, đang chờ một quyết định (xem tài liệu 4).
- **Một bài báo không dùng lại được cho hai nghiên cứu khác nhau** — dữ liệu sẽ ghi đè lẫn nhau.
  Cùng thiết kế sửa ở trên.
- **Bộ lọc chống bịa số chưa biết đơn vị y khoa** (mg, mcg, IU, INR) lẫn đơn vị thống kê
  (OR, RR, 95% CI, p). Chủ đề chống đông đầy những số này nên đây là việc gấp.

## AnesthOS-app

Mới có khung xương: 1 công thức tính cân nặng lý tưởng, 5 cổng kiểm tra tự động.

**Có một lỗi lâm sàng đang sống trên nhánh chính**: công thức trả về 50 kg cho trẻ sơ sinh
cao 50 cm — sai khoảng 17 lần nếu dùng để tính liều theo cân nặng. Nguyên nhân: khi chiều
cao ngoài vùng công thức có hiệu lực, code âm thầm trả giá trị nền thay vì báo lỗi.
Lỗi này đi qua đủ cả 5 cổng kiểm tra.
