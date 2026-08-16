# 3. Việc tiếp theo

> **Cập nhật**: 2026-08-16 · SRagent `a11d14b` · AnesthOS-app `56f5a87`
> Xếp theo thứ tự nên làm, không phải theo độ khó.

## Việc CHỈ Gun làm được (không giao ai thay thế)

### 1. Chốt "ngoại lệ vùng cấm" — ~5 phút, mở khoá nhiều việc phía sau
Chi tiết ở tài liệu 4, mục 7. Chưa chốt thì không sửa được kho dữ liệu, mà kho dữ liệu là
nền của toàn bộ định vị hệ thống. **Đây là việc rẻ nhất có tác động lớn nhất hiện nay.**

### 2. Chạy "First Light" — lần chạy sống đầu tiên
Cần: máy Mac, Ollama đã cài, khoá API của IEEE. Có runbook từng bước tại
`docs/runbooks/M7.1-first-light.md` (đã sửa 2 lỗi chặn, giờ chạy được).

Vì sao quan trọng: toàn bộ hệ thống chưa từng chạy trên dữ liệu thật lần nào. Mọi con số
hiện có đều từ test. Cho tới khi chạy thật, **không ai biết hệ thống có thực sự hoạt động không**.
Đây là mốc lớn nhất đang treo.

### 3. Quyết 3 mục còn lại ở tài liệu 4
Không gấp bằng mục 1, nhưng để lâu thì chặn dần.

## Việc giao được cho AI thực thi

Xếp theo thứ tự phụ thuộc:

| Thứ tự | Việc | Vì sao ưu tiên vậy |
|---|---|---|
| A | **Sửa lỗi cân nặng lý tưởng ở AnesthOS** | Lỗi lâm sàng đang sống. Sửa mất khoảng 1 giờ, không phụ thuộc gì cả |
| B | **Bật kiểm tra tự động cho nhánh AI làm việc** | 2 dòng cấu hình. Hiện AI làm việc ở nhánh **không có cổng kiểm tra nào chạy** — nơi rủi ro cao nhất lại không được canh |
| C | **Bổ sung đơn vị y khoa + thống kê cho bộ lọc chống bịa số** | Chủ đề chống đông đầy liều thuốc và ngưỡng INR. Không có bước này thì bài viết ra không kiểm chứng được |
| D | **Tách kho dữ liệu khỏi hàng đợi duyệt** | Chặn bởi quyết định mục 1. Xong mới dùng lại được dữ liệu giữa các nghiên cứu |
| E | **Thêm nguồn PubMed** | Mở khoá chủ đề y khoa. Đã có 2 mẫu nguồn sẵn để làm theo |
| F | Đánh giá nguy cơ sai lệch, GRADE, meta-analysis, sinh bản thảo | Phần viết bài. Cần E xong trước mới có dữ liệu thật để chạy |

## Đường găng — chuỗi việc quyết định tổng thời gian

```
Chốt ngoại lệ  →  Tách kho  →  Thêm PubMed  →  Thu thập chủ đề chống đông
                                                   →  Đánh giá bằng chứng  →  Viết bản thảo
```

Mọi ngày chậm ở **"chốt ngoại lệ"** là một ngày chậm của toàn bộ chuỗi phía sau.
Các việc A, B, C nằm ngoài chuỗi này nên chạy song song được, không cần chờ.

## Gợi ý phân bổ trong tuần

- **Nửa ngày**: chạy First Light (việc 2) — cho ra dữ liệu thật để mọi kế hoạch sau bám vào.
- **15 phút**: chốt các quyết định ở tài liệu 4.
- Còn lại giao AI: A, B, C chạy song song ngay.
