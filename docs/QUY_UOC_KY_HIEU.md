# Quy ước ký hiệu — SR-Agent & AnesthOS

> **Tài liệu này là nguồn chân lý về ký hiệu.** Một ký hiệu không có dòng trong sổ đăng
> ký ở §3 thì **coi như không tồn tại** — dù nó đã được dùng ở đâu đó.
>
> **Cập nhật**: 2026-08-31 · **Chốt tại**: `docs/DECISIONS.md` #10

---

## 1 · Vì sao cần

> ### 「Nói đơn giản」
>
> Ký hiệu tồn tại để **tra cứu nhanh**: thấy `L3` là nhảy thẳng tới đúng luật đó, khỏi
> đọc lại cả tài liệu. Giống mã **ICD-10** hay bảng phân loại **ASA** — một mã trỏ đúng
> **một** thứ, và trỏ như thế mãi mãi.
>
> Một mã mang hai nghĩa thì **tệ hơn là không có mã**. Không có mã thì người đọc buộc
> phải đọc kỹ. Có mã sai thì người đọc tra nhầm bảng **mà vẫn thấy tự tin** — và không
> có gì báo động cả.
>
> Đó chính là điều đã xảy ra trong kho này. Xem §5.

---

## 2 · Hai trục phân loại

Mọi ký hiệu, hiện tại và tương lai, đều xếp được bằng hai câu hỏi.

### Trục 1 · Phạm vi hiệu lực

| Loại | Nghĩa | Đánh số |
|---|---|---|
| **Toàn cục** | có hiệu lực ở **mọi** tài liệu, **mọi** chặng, vĩnh viễn | không bao giờ khởi động lại. Một chữ cái = **một** nghĩa duy nhất, đời đời |
| **Cục bộ** | chỉ có nghĩa **trong** tài liệu khai ra nó | khởi động lại từ 1 ở mỗi tài liệu — **cố ý**, không phải va chạm |

> **Ký hiệu cục bộ dẫn từ ngoài tài liệu chủ BẮT BUỘC gắn mã tài liệu**: `A0.R4`,
> `V1.Đ2`. Viết trần `R4` ở tài liệu khác là sai quy ước.
>
> Đây giống biến cục bộ trong hai hàm khác nhau: trùng tên **không** phải lỗi, miễn là
> gọi từ ngoài thì gọi đủ tên.

### Trục 2 · Vai trò

| Vai trò | Trả lời câu hỏi |
|---|---|
| **Luật** | *"được phép làm gì, cấm làm gì"* |
| **Mốc lộ trình** | *"đang ở đâu, đi đâu tiếp"* |
| **Phân loại** | *"thứ này thuộc nhóm nào"* |
| **Ràng buộc bất biến** | *"cấu trúc dữ liệu này không bao giờ được vi phạm điều gì"* |
| **Đích nghiệm thu** | *"chạy xong phải ra đúng con số nào"* |

---

## 3 · Sổ đăng ký — toàn bộ ký hiệu được phép tồn tại

| Ký hiệu | Phạm vi | Vai trò | Nghĩa | Khai ở |
|---|---|---|---|---|
| **L1…L10** | toàn cục | luật | luật vận hành dự án | `KE_HOACH_ANTIGRAVITY.md` §1 |
| **M0…M6** | toàn cục | mốc lộ trình | **chặng phát triển pipeline** (lịch sử, đã xong) — `gate_m6.sh` là cổng của M6 | `HANDOVER.md` |
| **P1/P2/P3** | toàn cục | phân loại | **mức ưu tiên rủi ro** của một khẳng định (1 = chết người) | `DAC_TA_V1_SO_PHU.md` §2.3 |
| **A / B / C** | toàn cục | mốc lộ trình | chặng lớn của lộ trình hiện hành | `LO_TRINH.md` §5 |
| **A‑0, A0…A4, B1…B6, C0…C3** | toàn cục | mốc lộ trình | bước trong chặng | `LO_TRINH.md` §5 |
| **G1, G2** | toàn cục | mốc lộ trình | cổng rẽ nhánh giữa các bước | `LO_TRINH.md` §5 |
| **V1, A0** | toàn cục | mã tài liệu | tên ngắn của một đặc tả, dùng để gắn ký hiệu cục bộ | tên tệp `DAC_TA_*.md` |
| **R1…** | **cục bộ** | ràng buộc bất biến | bất biến của riêng một đặc tả | mỗi `DAC_TA_*.md` §3 |
| **Đ1…** | **cục bộ** | đích nghiệm thu | con số phải khớp của riêng một đặc tả | mỗi `DAC_TA_*.md` §4 |
| **EF·, ET·** | toàn cục | phân loại | mã tiêu chí sàng lọc | `tools/criteria/default.json` |
| **BS-B, BS-C, BS-F** | toàn cục — **kho AnesthOS** | luật | chuẩn an toàn lâm sàng | `AnesthOS-app/CLAUDE.md` — **đăng ký để tránh đụng, không sửa từ kho này** |
| **D30…D33, TS-·** | toàn cục | mã tài liệu | đặc tả các đợt cũ | `docs/specs/` — lịch sử, không cấp thêm |

**Mã tài liệu suy ra từ tên tệp**: bỏ tiền tố `DAC_TA_`, lấy phần đầu →
`DAC_TA_A0.md` = `A0` · `DAC_TA_V1_SO_PHU.md` = `V1`.

### Chữ cái đã bị chiếm — không được cấp lại cho nghĩa khác

`A` `B` `C` `D` `Đ` `E` `G` `L` `M` `P` `R` `T` `V` — cùng với `BS-`, `EF`, `ET`, `TS-`.

> **Chữ còn trống**: `H` `I` `K` `Q` `S` `U` `X` `Y`. Cấp một chữ mới là việc hiếm —
> đọc §4 trước, phần lớn nhu cầu nên nối vào series sẵn có.

---

## 4 · Luật cấp ký hiệu mới — bốn bước, không được bỏ bước

| # | Bước |
|---|---|
| **1** | **Tra sổ §3 trước.** Chữ cái đã có nghĩa thì **vĩnh viễn không tái sử dụng** cho nghĩa khác — kể cả khi series cũ đã ngừng dùng |
| **2** | Hỏi: đây là **luật vận hành vĩnh viễn**? Nếu đúng → **nối tiếp `L`**, đừng đẻ series mới |
| **3** | Cục bộ trong một đặc tả → dùng lại **`R`** (ràng buộc) hoặc **`Đ`** (đích). Đúng thiết kế, không phải va chạm. Phải ghi dòng khai *"cục bộ, riêng tài liệu này"* ngay đầu mục |
| **4** | Buộc phải cấp series toàn cục mới → **cùng commit** thêm một dòng vào §3. Không có dòng trong sổ = ký hiệu không tồn tại |

---

## 5 · Đã từng sai ở đâu — chứng cứ sống, đừng xoá

Bốn va chạm có thật trong kho này. Giữ lại để người sau hiểu vì sao có luật §4.

| # | Va chạm | Hậu quả |
|---|---|---|
| **1** | Chữ **N** mang **ba nghĩa**: `N‑1/N‑2/N‑3` (luật nghiệm thu) · `N1…N6` (đích của V1) · *"liệt kê **N** quyết định"* (số đếm thường) | Đọc `N1` mà tưởng luật `N‑1` thì tra nhầm bảng, không có gì báo động |
| **2** | Hai bộ **R** trùng tên khác nội dung: `V1.R1` nói `muc_phu`, `A0.R1` nói mọi `@property` | Không tài liệu nào ghi rõ chúng độc lập → người đọc tưởng là một |
| **3** | Chữ đại diện "đích nghiệm thu" đổi tuỳ hứng: `N` ở V1, `M` ở A0 | Lý do thật (N đã bị chiếm) **chưa từng viết ra**, nên `M` xuất hiện vô căn cứ |
| **4** | **`M` vốn đã là chặng phát triển M0–M6.** Dùng `M1…M8` làm đích nghiệm thu tạo va chạm **ngay trong một tài liệu**: `DAC_TA_A0.md` dòng 9 `M6` = cổng chặng, dòng 341 `M6` = đích thứ 6 | Cùng tệp, cùng ký hiệu, hai nghĩa |

### Và một va chạm suýt nữa, do chính lúc sửa

Bản kế hoạch sửa bốn lỗi trên định cấp `P1/P2/P3` cho luật nghiệm thu. Chạy phép kiểm va
chạm trước khi chốt: **`P1` đã dùng ở hơn 10 chỗ**, nghĩa là **"ưu tiên 1"**.

> Suýt chữa bệnh bằng đúng con vi khuẩn gây bệnh. Đây là lý do bước 1 của §4 phải là
> **luật**, không phải thói quen tốt.
>
> Và phát hiện đó dẫn tới cách sửa gọn hơn hẳn: `N‑1/N‑2/N‑3` **vốn cùng loại** với
> `L1…L6`. Không cấp chữ mới, mà **xoá bớt một series** — chúng thành `L7/L8/L9`.

---

## 6 · Cách sửa khi phát hiện va chạm

| Bước | Việc |
|---|---|
| 1 | **Đừng đổi con số.** Chỉ đổi chữ cái đứng trước. `20.279` vẫn là `20.279` |
| 2 | Ưu tiên **gộp series** hơn đổi tên series. Bớt một ký hiệu tốt hơn đổi tên một ký hiệu |
| 3 | Series **đang chạy đúng thì không đụng**, dù trông không cân đối. Đổi tên thứ đang đúng là tự tạo rủi ro |
| 4 | Sửa xong, đối chiếu tập hợp mọi con số trước và sau — phải **y hệt** |
