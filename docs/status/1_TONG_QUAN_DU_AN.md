# 1. Tổng quan dự án

> **Cập nhật**: 2026-08-16 · SRagent `a11d14b` · AnesthOS-app `56f5a87`
> **Nguồn sự thật**: GitHub. Bản trên Drive là bản sao chỉ đọc — nếu hai bên khác nhau, tin GitHub.

## MỘT chuỗi giá trị, hai kho mã

> **Đính chính 2026-08-23.** Bản trước ghi "hai sản phẩm riêng biệt" — sai về quan hệ.

```
   SR-Agent  ──── chứng cứ ────►  AnesthOS  ──── khuyến cáo ────►  Bác sĩ
   sinh chứng cứ                  ra quyết định
```

AnesthOS đưa ra khuyến cáo lâm sàng. **Khuyến cáo phải có chứng cứ, và chứng cứ đến từ
SR-Agent.** SR-Agent được tách riêng KHÔNG phải vì nó là sản phẩm khác, mà vì nó **tái
dùng được cho mọi lĩnh vực**: đổi nguồn tham khảo là có một hệ tri thức hệ thống cho
bất kỳ vấn đề nào — y khoa chỉ là lĩnh vực đầu tiên.

| Tiêu chí | SR-Agent | AnesthOS-app |
|---|---|---|
| Vai trò | **Bộ máy sinh chứng cứ** — dùng chung, mù lĩnh vực | **Bộ ra quyết định** — chuyên gây mê |
| Là gì | Thu thập y văn → kho dữ liệu → bài tổng quan hệ thống | Ứng dụng hỗ trợ quyết định lâm sàng |
| Công nghệ | Python, chạy local trên Mac | React + TypeScript |
| Repo | `Gunthqq30223132/SRagent` | `Gunthqq30223132/AnesthOS-app` |
| Trạng thái | Đang phát triển, thu thập chạy được, **chưa chạy dữ liệu sống** | Mới có khung xương |

**Hệ quả lên thiết kế**: lõi `sr_agent/` phải mù lĩnh vực. Mọi thứ đặc thù y khoa —
nguồn PubMed, đơn vị lâm sàng, bậc chứng cứ — nằm ở tầng cắm thêm (`tools/sources/`,
`tools/profiles/`), không được ngấm vào lõi.

**Hệ quả lên thứ tự làm**: hoàn thiện SR-Agent chạy thật trước. Lớp A/B/C của AnesthOS
chỉ bộc lộ điểm yếu khi có chứng cứ thật chảy vào — thiết kế thêm lúc chưa chạy là đoán.

## SR-Agent làm gì

```
Nhiều nguồn  →  Kho dữ liệu  →  Bài systematic review theo vấn đề nghiên cứu
(PubMed,        (lưu trữ         (đạt mức chặt chẽ của tạp chí Q1,
 Cochrane,       lâu dài)         nhưng KHÔNG nhằm nộp đăng)
 IEEE, arXiv)
```

Chuỗi xử lý: chủ đề → sinh đề cương PICO → tìm kiếm → sàng lọc kép (2 AI độc lập, đo độ
đồng thuận) → trích xuất dữ liệu kèm trích dẫn nguyên văn → báo cáo PRISMA → bản thảo.

**Nguyên tắc xuyên suốt**: máy làm phần lặp lại, người duyệt phần quan trọng.
Không tài liệu nào tự động được chấp nhận.

## AnesthOS-app làm gì

Máy tính lâm sàng cho bác sĩ gây mê. Kiến trúc tách đôi cứng: phần tính toán y khoa
(`src/domain/`) hoàn toàn thuần tuý, không mạng, không ngẫu nhiên — tách khỏi phần giao diện.
Mọi công thức phải khai báo nguồn gốc (hướng dẫn nào, năm nào).

## Chủ đề nghiên cứu đầu tiên

> **Tiếp cận quản lý chống đông trước, trong và sau mổ**

Đây là bài systematic review đầu tiên SR-Agent sẽ viết.
