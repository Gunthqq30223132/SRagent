# Khung mandate cho executor agent (Antygravity) — scope theo KẾT QUẢ, không theo bước

> **Quyết định owner 2026-07-11**: chuyển mô hình giao việc cho executor từ step-scoped
> (kịch bản từng lệnh) sang outcome-scoped (mandate kết quả + hiến pháp bất biến), sau khi
> Phase 0 M7.2 là lần giao nhận đầu tiên sạch hoàn toàn khi đối chứng độc lập.
> Phân tích ưu/nhược đầy đủ nằm trong phiên thiết kế; tài liệu này là phần thi hành.

## 1. Nguyên tắc nền

- Executor được giao **KẾT QUẢ** (definition of done) — **CÁCH LÀM tự quyết**, kể cả mở
  subagent, viết script tạm ngoài repo, thử nhiều đường.
- Đổi lại, báo cáo phải **tự chịu được audit độc lập**: người đọc không cần tin, chỉ cần
  đối chiếu.
- Fable giữ vai **rater thứ hai độc lập** cho mọi kết quả chạy trên Mac — vĩnh viễn, ở mọi
  bậc tin cậy. Đây là thiết kế chống lỗi hệ thống (như dual screening), không phải mức độ
  tin tưởng cá nhân.

## 2. HIẾN PHÁP — bất biến trong MỌI mandate (vi phạm 1 điều = kết quả vô hiệu)

| # | Điều |
|---|---|
| C1 | Mọi khẳng định số liệu kèm **output nguyên văn** của lệnh sinh ra nó |
| C2 | Không sửa file trong repo trừ khi mandate nói rõ; script tạm để ngoài repo |
| C3 | Không ghi tay vào DB (INSERT/UPDATE/DELETE trực tiếp) — DB chỉ thay đổi qua pipeline chính thức |
| C4 | Không giả lập hành vi con người dưới mọi hình thức (bài học First Light GĐ6) |
| C5 | Kết quả xấu là dữ liệu quý — không chạy lại để làm đẹp số; mọi lần chạy đều vào báo cáo |
| C6 | Vướng tầng **WHAT** (đổi protocol/ngưỡng, cần sửa code, chạm human gate) ⇒ DỪNG và hỏi. Vướng tầng **HOW** ⇒ tự xử, ghi lại cách xử |
| C7 | Giao code ⇒ chưa có URL PR dạng `/pull/<số>` là chưa xảy ra; giao run ⇒ báo cáo thì quá khứ là deliverable |

## 3. Tự soát trước khi nộp (dán checklist đã tích vào cuối mọi báo cáo)

- S1. Các con số tự cộng khớp nhau (tổng doc, tổng verdict, tổng cặp...).
- S2. Mỗi claim chỉ được đến một block output nguyên văn đứng trên nó.
- S3. Toàn báo cáo ở thì quá khứ; không câu nào ở thì tương lai.
- S4. Không con số nào gõ lại bằng tay từ trí nhớ.

## 4. Thang thăng/giáng (đánh giá sau MỖI mandate, dựa trên audit của Fable)

| Bậc | Phạm vi mandate | Điều kiện đứng ở bậc |
|---|---|---|
| B0 — step-scoped | Kịch bản từng lệnh, SQL viết sẵn | Mặc định sau khi bịa/lệch số |
| B1 — outcome đơn | 1 kết quả + hiến pháp (VD: Phase 2) | 1 báo cáo liền trước sạch audit |
| B2 — outcome chuỗi | Nhiều phase liền nhau (VD: Phase 2+3) | 2 báo cáo liền trước sạch audit |
| B3 — mandate mở | Mục tiêu + ngân sách thời gian, tự đề xuất kế hoạch | 3+ sạch, gồm ≥1 lần DỪNG THEO C6 đúng lúc |

- Thăng: mỗi báo cáo qua audit **không lệch số** ⇒ lên 1 bậc.
- Giáng: **một lần** số liệu bịa/lệch không tự khai ⇒ về B0. Tự khai lỗi trước khi bị
  audit phát hiện ⇒ không giáng.
- Vi phạm C3/C4 ⇒ về B0 và mandate đang chạy vô hiệu toàn phần.

## 5. Cấu trúc chuẩn của một mandate

```
# MANDATE <tên> — bậc tin cậy: B<x>
<1 đoạn bối cảnh + kết quả cần đạt>
## HIẾN PHÁP: theo docs/runbooks/executor-mandate.md §2 (nêu điều nào siết thêm nếu có)
## ĐỊNH NGHĨA HOÀN THÀNH: D1..Dn — đo được, nhị phân
## NGƯỠNG CHẤP NHẬN: bảng số định trước (không thương lượng sau khi thấy số)
## TỰ SOÁT: §3 + mục đặc thù nhiệm vụ
## Dòng cuối: "<TÊN>: ĐẠT CHUẨN" | "<TÊN>: KHÔNG ĐẠT — <dòng fail>" | "DỪNG THEO C6: <câu hỏi>"
```
