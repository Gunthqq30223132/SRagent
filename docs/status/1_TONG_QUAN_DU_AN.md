# 1. Tổng quan dự án

> **Cập nhật**: 2026-08-16 · SRagent `a11d14b` · AnesthOS-app `56f5a87`
> **Nguồn sự thật**: GitHub. Bản trên Drive là bản sao chỉ đọc — nếu hai bên khác nhau, tin GitHub.

## Đây là HAI sản phẩm, không phải một

Nhầm lẫn này đã từng làm lệch cả một kế hoạch, nên ghi rõ:

| Tiêu chí | SR-Agent | AnesthOS-app |
|---|---|---|
| Là gì | Hệ thống tự thu thập tài liệu khoa học rồi viết bài tổng quan hệ thống | Ứng dụng hỗ trợ quyết định lâm sàng gây mê |
| Công nghệ | Python, chạy local trên Mac | React + TypeScript |
| Repo | `Gunthqq30223132/SRagent` | `Gunthqq30223132/AnesthOS-app` |
| Trạng thái | Đang phát triển, phần thu thập đã chạy được | Mới có khung xương |

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
