# 4. Quyết định đang chờ Gun chốt

> **Cập nhật**: 2026-08-16 · SRagent `a11d14b`
> Cái đã chốt rồi nằm ở tài liệu 5 — đừng hỏi lại những mục đó.

---

## Mục 7 — Cho phép sửa file lõi để tách kho dữ liệu?  🔴 GẤP

**Bối cảnh**: hệ thống có một "vùng cấm" — vài file lõi mà AI không được tự ý sửa, có cổng
tự động chặn. Cơ chế này sinh ra để AI không phá kiến trúc. Nhưng việc tách kho dữ liệu
**buộc phải** sửa 2 file trong vùng cấm đó.

**Nếu không cho**: kho dữ liệu không tách được → vẫn tự xoá sau 72 giờ → không dùng lại được
dữ liệu giữa các nghiên cứu → định vị "kho dữ liệu nhiều nguồn" không thành.

**Nếu cho tuỳ tiện**: mất luôn giá trị của cổng bảo vệ.

**Đề xuất**: cho phép, kèm 3 ràng buộc — (a) khai báo trước khi sửa, không sửa xong mới báo;
(b) chỉ được thêm tham số mới, không đổi logic đang chạy; (c) file cấu hình vẫn khoá nguyên.

→ **Cần Gun trả lời: đồng ý / không / đồng ý với ràng buộc khác.**

---

## Mục 8 — Sửa đề cương nghiên cứu thì tạo bản mới hay sửa tại chỗ?

**Bối cảnh**: mỗi bài tổng quan bắt đầu bằng một đề cương (câu hỏi nghiên cứu, tiêu chí
chọn/loại bài báo). Câu hỏi: nếu đang làm dở mà muốn đổi tiêu chí thì sao?

**Đề xuất**: **tạo bản mới**, đóng băng bản cũ.

**Vì sao**: đề cương chốt trước khi sàng lọc là ranh giới giữa nghiên cứu nghiêm túc và
"chọn kết quả mình thích". Nếu sửa được tiêu chí sau khi đã thấy kết quả thì tính khách quan
mất sạch, mà không ai phát hiện được vì lịch sử bị ghi đè. Chi phí gần bằng 0.

→ **Cần Gun trả lời: đồng ý tạo bản mới, hay muốn cho sửa tại chỗ?**

---

## Mục 9 — Kho dữ liệu có giới hạn dung lượng không?

**Đề xuất**: **chưa đặt giới hạn**. Thay bằng cảnh báo khi file vượt 2 GB.

**Vì sao**: vấn đề đang sửa *chính là* việc tự động xoá dữ liệu — đặt giới hạn xoá là tái
phạm ngay trong bản vá. Mỗi bài báo chiếm khoảng 5–15 KB, nên 2 GB tương đương hàng trăm
nghìn bài, xa hơn nhiều so với nhu cầu vài nghiên cứu. Đây là vấn đề của năm sau.

→ **Cần Gun trả lời: đồng ý không đặt giới hạn?**

---

## Mục 10 — Tài liệu kiểm toán lâm sàng để ở repo nào?  🟢 gần như tự giải

**Bối cảnh**: có vài tài liệu phân tích an toàn lâm sàng nằm trong repo SR-Agent, trước đây
là vấn đề vì repo đó cấm nội dung y khoa.

**Đề xuất**: **giữ nguyên tại chỗ**. Quyết định mở phạm vi y sinh (tài liệu 5, mục 1) đã
làm vấn đề tuân thủ biến mất. Và các file kiểm tra đó kiểm chính bộ lọc nằm trong repo này —
tách ra là tách test khỏi thứ nó kiểm.

→ **Cần Gun trả lời: đồng ý giữ nguyên?**

---

## Tóm tắt cho Spark

Gun đang nợ **4 quyết định**. Chỉ **mục 7 là gấp** — nó chặn đường găng của cả dự án.
Ba mục còn lại đều đã có đề xuất kèm lý do, chỉ cần gật hoặc phản đối.
