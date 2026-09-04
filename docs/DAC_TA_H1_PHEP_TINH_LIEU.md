# Đặc tả H1 — phép tính liều thuốc tê

> **Mã tài liệu: `H1`.** Series `R` (ràng buộc) và `Đ` (đích nghiệm thu) dưới đây **cục
> bộ, riêng tài liệu này** — dẫn từ ngoài phải viết đủ `H1.R2`. Xem
> `docs/QUY_UOC_KY_HIEU.md`.
>
> **Vai**: chốt **khoá tra** của từng số hạng TRƯỚC khi `LO_TRINH.md` B4 sinh
> `local_anesthetics.v2.json`. Không chốt trước thì v2 mang sẵn lỗi của v1.
>
> **Cập nhật**: 2026-09-04

---

## TỪ ĐIỂN

| Từ | Nghĩa trong tài liệu này |
|---|---|
| **số hạng** | một đại lượng trong bất đẳng thức an toàn (LGH, trần, C_adjust, IBW) |
| **khoá tra** | tập thuộc tính phải nêu đủ mới xác định được **một** giá trị của số hạng |
| **loại trần** | trần nhãn pháp lý · đích thực hành · hay trần theo đường dùng cụ thể |
| **cân nặng giao nhau** | cân nặng mà tại đó `mg/kg × cân nặng` = `trần một lần` |

---

## 1. Vì sao có tài liệu này

> ### 「Nói đơn giản」
>
> Trước đây hệ thẩm định **từng trường dữ liệu** mà không hỏi **phép tính nào tiêu thụ
> nó**. Giống như kiểm từng chỉ số xét nghiệm mà không biết đang chẩn đoán bệnh gì —
> mỗi con số "đúng" riêng lẻ, ghép lại vẫn ra kết luận sai.
>
> Bộ 28 khẳng định của phác đồ #1 được dựng bằng cách liệt kê 7 hoạt chất × 4 tên trường.
> Đó là **liệt kê trường**, không phải **phân rã phép tính**.

Hậu quả đo được: ca lidocaine `plain` nay có **ba** con số, và chúng **không mâu thuẫn** —
chúng trả lời **ba câu hỏi khác nhau** mà lược đồ hiện tại chỉ có **một** ô để chứa.

| Con số | Nguồn | Câu hỏi nó trả lời |
|---|---|---|
| **4,5** mg/kg | tệp dựng AnesthOS | — (chưa truy được nguồn) |
| **3,0** mg/kg | đích thực hành, `LO_TRINH.md` cổng G2 | liều an toàn nên nhắm tới |
| **5,0** mg/kg | UpToDate, *Subcutaneous infiltration* | trần cho **gây tê thấm dưới da** |

`maxDoseMgPerKg.plain` không có khoá **đường dùng**, nên ba câu trả lời khác nhau bị ép
vào một ô. Đó là **khoá thiếu**, không phải bất đồng nguồn.

---

## 2. Hai bất đẳng thức

```
Liều cho phép một lần (mg) = min( LGH × C_adjust × IBW , Trần một lần )
Σ liều trong 24 h (mg) ≤ Trần 24 h
```

Hai bất đẳng thức **độc lập**: một cái chặn liều tiêm lúc này, một cái chặn tổng tích luỹ.
Bất đẳng thức thứ hai hiện **không có ô nào trong lược đồ**, dù số liệu **đã có trong
nguyên văn đã trích** (`Table 5.2`, cột *Over 24 h*: bupivacaine 400 · levobupivacaine 400
· ropivacaine 800 mg). Số đang bị vứt lúc nạp.

### 2.1 · `min()` không phải trang trí — nhưng cũng chưa phải hai bằng chứng

Đo trên `local_anesthetics.json` tại `origin/feat/p1-domain`, bệnh nhân 70 kg: **4/14** tổ
hợp bị **trần** chặn, **10/14** bị **mg/kg** chặn. Nếu bỏ `min()` và chỉ dùng mg/kg thì
lidocaine plain cho 315 mg trong khi trần là 300.

Nhưng tính **cân nặng giao nhau** (= trần ÷ mg/kg) cho cả 14 tổ hợp thì ra một dải rất hẹp:

| Cân nặng giao nhau | Số tổ hợp |
|---|---|
| 66,7 kg | 2 |
| 70,0 – 72,7 kg | 9 |
| 75,0 – 80,0 kg | 3 |

**Toàn bộ nằm trong 66,7–80,0 kg.** [Suy luận] Đây là dấu vết của một bảng dựng bằng cách
lấy *một* con số rồi suy ngược ra con số kia quanh mốc người lớn ~70 kg — nghĩa là hai số
hạng **không độc lập**, chúng là **một phép đo viết hai lần**.

> **Hệ quả bắt buộc**: `mg/kg` và `trần một lần` của cùng một hoạt chất **không bao giờ
> được tính là hai xác nhận độc lập**. Cùng một cái bẫy `dong_thuan` của A0 đã chặn ở cấp
> khẳng định, nay xuất hiện ở cấp **số hạng**.

`bupivacaine.withEpi` và `levobupivacaine.withEpi` giao nhau **đúng 70,0 kg** — ở 69 kg
mg/kg chặn, ở 71 kg trần chặn. Ca kiểm thử bắt buộc, xem Đ3.

---

## 3. Khoá tra của từng số hạng

| Số hạng | Khoá tra đầy đủ | Lược đồ v1 |
|---|---|---|
| **LGH** (mg/kg) | hoạt chất · adrenaline · **đường dùng** · **cơ sở cân nặng** · **loại trần** | có 2, thiếu 3 |
| **Trần một lần** (mg) | như trên | có 2, thiếu 3 |
| **C_adjust** | **tổ hợp** tình trạng bệnh nhân | không có trường |
| **IBW** | công thức · giới tính · chiều cao | không có trường |
| **Trần 24 h** (mg) | hoạt chất · đường dùng | không có trường |

### 3.1 · `loai_tran` là KHOÁ, không phải cột thêm

Ba giá trị, ứng đúng vào các bước đã có trong `LO_TRINH.md` §5.2:

| Giá trị | Nguồn | Bước |
|---|---|---|
| `tran_nhan` | nhãn thuốc — trần pháp lý | B1 · luồng `S2` · tất định |
| `dich_thuc_hanh` | hướng dẫn hội — đích an toàn hơn | B2 · luồng `S3` |
| `tran_theo_duong_dung` | khuyến cáo cho **một** đường dùng cụ thể | B2 · luồng `S3` |

H1 **không** dựng khái niệm song song: `tran_nhan` chính là `max_ceiling` của B1,
`dich_thuc_hanh` chính là `clinical_target` của B2. H1 chỉ thêm **giá trị thứ ba** — ô mà
ca lidocaine 5,0 mg/kg rơi vào — và nâng nó từ *cột* lên *khoá*.

### 3.2 · `co_so_can_nang` là trường bắt buộc, `khong_noi` là trạng thái riêng

| Giá trị | Nghĩa |
|---|---|
| `IBW` | nguồn nói rõ dùng cân nặng lý tưởng |
| `TBW` | nguồn nói rõ dùng cân nặng thực |
| `khong_noi` | **nguồn không nói** — không được mặc định thành IBW hay TBW |

Bằng chứng thật cho việc này là bắt buộc: `Table 5.2` ghi thẳng *"Patient ideal body
weight should be used"*; đoạn UpToDate cho lidocaine chỉ ghi *"5 mg/kg"* **không nói cân
nặng nào**. Ở bệnh nhân béo phì hai cách hiểu lệch nhau rất lớn.

### 3.3 · `C_adjust` là BẢNG TRA TỔ HỢP, cấm nhân chuỗi

Toàn bộ bằng chứng hiện có, từ `docs/runs/PHAC_DO_01_ban_ghi.json` — **ba** bản ghi:

| Tổ hợp | Hệ số | Ghi chú |
|---|---|---|
| trẻ em < 8 tuổi | 0,80 | nguyên văn |
| **người cao tuổi CÓ suy gan hoặc suy thận nặng** | 0,50 | **một hệ số cho một tổ hợp**, không phải hai hệ số nhân nhau |
| thai kỳ, gây tê trục thần kinh | giảm tới 1/3 | bản ghi `dien_giai` — **chưa phải nguyên văn** |

Ba điều rút ra, đều thành ràng buộc:

- Nguồn cho **hệ số của tổ hợp**, không cho hệ số của từng yếu tố. Mô hình
  `C_adjust = c_tuổi × c_gan × c_thận` **không có bằng chứng nào chống lưng**.
- Tổ hợp chưa có trong bảng → **rơi về tổ hợp thận trọng nhất đã có bằng chứng**, không
  nội suy, không nhân.
- Bản ghi `dien_giai` **không được vào phép tính** cho tới khi có nguyên văn.

### 3.4 · `ma_doi_chieu` = số hạng + đủ khoá

```
LGH(lidocaine, khong_adrenaline, tham_duoi_da, khong_noi, tran_theo_duong_dung) = 5 mg/kg
```

Thay cho `lidocaine.maxDoseMgPerKg.plain`, vốn **giấu mất** đường dùng, cơ sở cân nặng và
loại trần.

> **Ca thật, lỗi của chính tài liệu tiền nhiệm.** Bộ đối chiếu
> `docs/runs/PHAC_DO_01_doi_chieu.json` đặt tên hoạt chất theo **tên hiển thị**
> (`2-Chloroprocaine`, `Lidocaine (Lignocaine)`), trong khi lược đồ nguồn dùng **khoá**
> (`chloroprocaine`, `lidocaine`). Khi đối chiếu, chỉ 11/28 mã khớp — và tôi đã kết luận
> nhầm rằng bên nộp đặt tên sai. **Bên nộp đúng.** Vì vậy R4 dưới đây bắt tên phải là
> khoá lược đồ, không phải tên hiển thị.

---

## 4. Ràng buộc bất biến

| # | Ràng buộc | Vì sao |
|---|---|---|
| **R1** | Mỗi giá trị LGH và trần phải mang **đủ 5 khoá**; thiếu một khoá → không được nạp | khoá thiếu là nguyên nhân của cả ba con số lidocaine bị ép một ô |
| **R2** | `co_so_can_nang = khong_noi` là trạng thái **riêng**, cấm mặc định thành IBW/TBW | không đo được ≠ đạt (nguyên tắc 4) |
| **R3** | `C_adjust` tra theo **tổ hợp**; cấm nhân các hệ số với nhau | không có bằng chứng nào cho tính nhân |
| **R4** | Tên hoạt chất trong `ma_doi_chieu` là **khoá lược đồ**, không phải tên hiển thị | ca 11/28 ở §3.4 |
| **R5** | `mg/kg` và `trần` của cùng hoạt chất **không** được tính là hai xác nhận độc lập | §2.1 — chúng là một phép đo viết hai lần |
| **R6** | Bản ghi `may_noi_gi = dien_giai` không vào phép tính | máy diễn đạt lại chưa phải nguyên văn |

---

## 5. Đích nghiệm thu

| # | Đích | Đo thế nào |
|---|---|---|
| **Đ1** | v2 chở đủ **5 số hạng**, gồm `tran_24h` hiện đang bị vứt | đếm trường trong `local_anesthetics.v2.json` |
| **Đ2** | 3 giá trị `tran_24h` đã có nguyên văn (bupi 400 · levobupi 400 · ropi 800) được nạp | so với `Table 5.2` trong bản ghi phác đồ #1 |
| **Đ3** | Ca 70,0 kg của `bupivacaine.withEpi`: 69 kg → mg/kg chặn · 71 kg → trần chặn | kiểm thử biên, cả hai phía |
| **Đ4** | Mọi giá trị LGH/trần có `co_so_can_nang`; số cái `khong_noi` được **báo cáo**, không giấu | đếm, in ra |
| **Đ5** | Không tổ hợp `C_adjust` nào sinh ra bằng phép nhân | rà bảng, không có ô nào là tích của hai ô khác |

**Ba trạng thái** (nguyên tắc 4): số hạng thiếu khoá → **VÔ HIỆU**, không phải TRƯỢT,
cũng không phải ĐẠT. Chạy được thì báo số, không chạy được thì nói không chạy được.

---

## 6. Chưa đặc tả — có tên, có lý do

| Việc | Vì sao hoãn |
|---|---|
| Công thức IBW cụ thể (Devine · Robinson · …) | là **một phép tính riêng có nguồn riêng**, thuộc luồng `S3`; chọn công thức trước khi có bằng chứng là đặt nhãn trước khi đo |
| Ô chở "nghiên cứu gốc đo gì, trên ai" | `HoSoBangChung` chưa có ô; A0 đang đóng băng với 100 kiểm thử đỏ — xem `LO_TRINH.md` §3 câu 6 |
| Liều tối đa theo đường dùng cho **mọi** hoạt chất | mới có bằng chứng cho lidocaine; phần còn lại cần một lượt phác đồ nữa |
