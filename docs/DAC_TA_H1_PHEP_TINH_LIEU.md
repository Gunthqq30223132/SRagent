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

### 2.1 · `min()` không phải trang trí

Đo trên `local_anesthetics.json` tại `origin/feat/p1-domain`, bệnh nhân 70 kg:

| Ràng buộc thật ở 70 kg | Số tổ hợp | Ví dụ |
|---|---|---|
| **trần** chặn | **2** | lidocaine plain 315 > 300 · prilocaine plain 420 > 400 |
| hai vế **bằng nhau** — `min()` không chọn gì | **2** | bupi/levobupi withEpi, đều 175 mg |
| mg/kg chặn | **10** | — |

Bỏ `min()` thì lidocaine plain cho 315 mg trong khi trần nhãn là 300. Hai ca là đủ để giữ
`min()`; không cần con số to hơn.

> **Đính chính, ghi lại để không lặp.** Bản đầu của mục này ghi *"4/14 bị trần chặn"* —
> sai, do đếm `>=` thành "chặn": hai ca 175 = 175 bị xếp nhầm vào nhóm trần. Bảng dải cân
> nặng cũng lệch (ghi 2/9/3, đúng là **2/8/4**). Làm mạnh con số lại làm yếu chính luận
> điểm nó chống lưng.

### 2.2 · Hai số hạng KHÔNG độc lập — nhưng lý do không phải dải cân nặng

Cân nặng giao nhau (= trần ÷ mg/kg) của cả 14 tổ hợp nằm trong **66,7–80,0 kg**. Phép đo
này **đã từng chạy và đã bị bác**: `LO_TRINH.md` §9 ghi *"Kiểm nhất quán nội tại
`mg/kg × cân nặng ↔ trần` — đã chạy thử: 14/14 cặp nhất quán ở 66,7–80 kg → **không có
sức phân biệt**"*. Không được dùng nó làm bằng chứng.

Và nó **cũng không phân biệt được thật**: tính trên `Table 5.2` (nguồn thật, đã trích
trong `PHAC_DO_01_ban_ghi.json`), dải là **62,5–83,3 kg** — rộng hơn, nhưng cùng hình dạng.

Lý do đúng để giữ ràng buộc R5 là **cấu trúc, không phải số đo**: bảng liều thuốc tê được
soạn bằng cách lấy một trong hai con số rồi suy ra con số kia qua một mốc người lớn quy
chiếu. Điều đó đúng với cả bảng thật lẫn bảng dựng, nên `mg/kg` và `trần` của cùng hoạt
chất **không bao giờ được tính là hai xác nhận độc lập** — cùng cái bẫy `dong_thuan` của
A0, ở cấp **số hạng** thay vì cấp khẳng định.

`bupivacaine.withEpi` và `levobupivacaine.withEpi` giao nhau **đúng 70,0 kg** trên tệp
dựng. Xem Đ3 — và đọc kỹ cảnh báo ở đó.

---

## 3. Khoá tra của từng số hạng

| Số hạng | Khoá tra đầy đủ | Lược đồ v1 |
|---|---|---|
| **LGH** (mg/kg) | hoạt chất · adrenaline · **đường dùng** · **cơ sở cân nặng** · **loại trần** | có 2, thiếu 3 |
| **Trần một lần** (mg) | như trên | có 2, thiếu 3 |
| **C_adjust** | **tổ hợp** tình trạng bệnh nhân | không có trường |
| **IBW** | công thức · giới tính · chiều cao | **đã có** — `AnesthOS/src/domain/calculators/ibw.ts` |
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
| `IBW` | cân nặng lý tưởng — nguồn nói rõ |
| `ABW` | cân nặng hiệu chỉnh — `ABW = IBW + 0,4 × (cân nặng thật − IBW)` |
| `TBW` | cân nặng thực — nguồn nói rõ |
| `khong_noi` | **nguồn không nói** — không được mặc định thành bất kỳ giá trị nào |

`ABW` **bắt buộc phải có mặt** trong danh sách: `calculateIBW()` của AnesthOS đã trả về
`adjustedBodyWeightKg` cùng lúc với `ibwKg`. Bỏ `ABW` khỏi enum là bỏ đúng chỗ nguy hiểm
nhất — ở bệnh nhân béo phì, ba cách hiểu cân nặng tách xa nhau nhất chính là ở đó.

Vì sao phải khai, có ca thật cả hai phía: `Table 5.2` ghi thẳng *"Patient ideal body
weight should be used"* → `IBW`; còn đoạn UpToDate cho lidocaine chỉ ghi *"5 mg/kg"*, **không
nói cân nặng nào** → bắt buộc `khong_noi`, cấm đoán.

### 3.3 · `C_adjust` là BẢNG TRA TỔ HỢP, cấm nhân chuỗi

Toàn bộ bằng chứng hiện có, từ `docs/runs/PHAC_DO_01_ban_ghi.json` — **ba** bản ghi:

| Tổ hợp | Hệ số | Ghi chú |
|---|---|---|
| trẻ em < 8 tuổi | 0,80 | nguyên văn nói *"maximum allowable dose"*, **không nêu hoạt chất** |
| người cao tuổi CÓ suy gan hoặc suy thận nặng, **RIÊNG lidocaine** | 0,50 | **một hệ số cho một tổ hợp**, không phải hai hệ số nhân nhau |
| thai kỳ, gây tê trục thần kinh | giảm tới 1/3 | bản ghi `dien_giai` — **chưa phải nguyên văn** |

Ba điều rút ra, đều thành ràng buộc:

- Nguồn cho **hệ số của tổ hợp**, không cho hệ số của từng yếu tố. Mô hình
  `C_adjust = c_tuổi × c_gan × c_thận` **không có bằng chứng nào chống lưng**.
- Tổ hợp chưa có trong bảng → **rơi về tổ hợp thận trọng nhất đã có bằng chứng**, không
  nội suy, không nhân.
- Bản ghi `dien_giai` **không được vào phép tính** cho tới khi có nguyên văn.
- **Hệ số mang phạm vi hoạt chất riêng, cấm ngoại suy.** Nguyên văn của hệ số 0,50 là
  *"the total dose of **lidocaine** should be decreased by approximately 50 percent in older
  adults with severe liver or kidney disease"* — nói **lidocaine**, không nói nhóm amide.
  Áp nó cho bupivacaine là ngoại suy, mà bản ghi vẫn khai `may_noi_gi = trich_nguyen_van`
  và `canh_bao = []`: **không tín hiệu nào báo**. R7 chặn việc này.

### 3.4 · `ma_doi_chieu` = số hạng + đủ khoá

```
LGH(lidocaine, khong_adrenaline, tham_duoi_da, khong_noi, tran_theo_duong_dung) = 5 mg/kg
```

Thay cho `lidocaine.maxDoseMgPerKg.plain`, vốn **giấu mất** đường dùng, cơ sở cân nặng và
loại trần.

> **Ca thật — 17/28 mã không nối được, và nguyên nhân chính KHÔNG phải tên hoạt chất.**
> Đếm lại từng mã lệch giữa `docs/runs/PHAC_DO_01_doi_chieu.json` và
> `docs/runs/PHAC_DO_01_ban_ghi.json`:
>
> | Nguyên nhân | Số mã | Bên nào sai |
> |---|---|---|
> | **tên trường**: bộ đối chiếu `absoluteMaxAdult` · bản ghi `maxDoseMg` | **14** | **bản ghi** — `maxDoseMg` không tồn tại trong lược đồ |
> | tên hoạt chất: bộ đối chiếu `2chloroprocaine` · lược đồ `chloroprocaine` | 4 | **bộ đối chiếu** |
> | chưa từng có bản ghi | 1 | — |
>
> (14 + 4 + 1 = 19 > 17 vì hai mã mắc cả hai lỗi cùng lúc.)
>
> Trường `ma` của bộ đối chiếu **vốn đã dùng khoá lược đồ**, không dùng tên hiển thị — tên
> hiển thị nằm ở trường `hoat_chat` riêng. Nghĩa là chẩn đoán "bên nộp đặt tên hiển thị"
> mà bản đầu tài liệu này đưa ra là **sai**, và nếu chỉ vá tên hoạt chất thì **14/17
> nguyên nhân thật vẫn còn nguyên**. R4 vì vậy phải phủ cả **tên trường**.

---

## 4. Ràng buộc bất biến

| # | Ràng buộc | Vì sao |
|---|---|---|
| **R1** | Mỗi giá trị LGH và trần phải mang **đủ 5 khoá**; thiếu một khoá → không được nạp | khoá thiếu là nguyên nhân của cả ba con số lidocaine bị ép một ô |
| **R2** | `co_so_can_nang = khong_noi` là trạng thái **riêng**, cấm mặc định thành IBW/TBW | không đo được ≠ đạt (nguyên tắc 4) |
| **R3** | `C_adjust` tra theo **tổ hợp**; cấm nhân các hệ số với nhau | không có bằng chứng nào cho tính nhân |
| **R4** | Mọi thành phần của `ma_doi_chieu` — **tên hoạt chất VÀ tên trường** — phải là khoá có thật trong lược đồ nguồn; mã chứa khoá không tồn tại thì bị loại ngay khi nạp | ca 17/28 ở §3.4: 14 lệch do tên trường, chỉ 4 do tên hoạt chất |
| **R5** | `mg/kg` và `trần` của cùng hoạt chất **không** được tính là hai xác nhận độc lập | §2.2 — bảng liều được soạn bằng cách suy một số ra số kia qua mốc quy chiếu. **Không** viện dải 66,7–80 kg làm bằng chứng: `LO_TRINH.md` §9 đã bác phép đo đó |
| **R6** | Bản ghi `may_noi_gi = dien_giai` không vào phép tính | máy diễn đạt lại chưa phải nguyên văn |
| **R7** | Hệ số `C_adjust` chỉ áp cho **đúng hoạt chất mà nguyên văn nêu tên**; nguyên văn không nêu hoạt chất thì phải khai `pham_vi = khong_ro` | hệ số 0,50 nói riêng lidocaine nhưng bảng ghi như hệ số chung — ngoại suy không có tín hiệu báo, xem §3.3 |

---

## 5. Đích nghiệm thu

| # | Đích | Đo thế nào |
|---|---|---|
| **Đ1** | v2 chở đủ **5 số hạng**, gồm `tran_24h` hiện đang bị vứt | đếm trường trong `local_anesthetics.v2.json` |
| **Đ2** | 3 giá trị `tran_24h` đã có nguyên văn (bupi 400 · levobupi 400 · ropi 800) được nạp | so với `Table 5.2` trong bản ghi phác đồ #1 |
| **Đ3** | Ca biên cân nặng giao nhau: dưới ngưỡng → mg/kg chặn · trên ngưỡng → trần chặn | **ngưỡng lấy từ v2, KHÔNG lấy 70,0 kg của tệp dựng.** Bằng chứng thật (`Table 5.2`) cho bupivacaine 3 mg/kg + 225 mg → giao nhau **75,0 kg**; dùng 70,0 kg là bắt v2 chép lại số của v1 |
| **Đ4** | Mọi giá trị LGH/trần có `co_so_can_nang`; số cái `khong_noi` được **báo cáo**, không giấu | đếm, in ra |
| **Đ5** | Không tổ hợp `C_adjust` nào sinh ra bằng phép nhân | rà bảng, không có ô nào là tích của hai ô khác |

**Ba trạng thái** (nguyên tắc 4): số hạng thiếu khoá → **VÔ HIỆU**, không phải TRƯỢT,
cũng không phải ĐẠT. Chạy được thì báo số, không chạy được thì nói không chạy được.

---

## 6. Chưa đặc tả — có tên, có lý do

| Việc | Vì sao hoãn |
|---|---|
| ~~Công thức IBW cụ thể~~ | **KHÔNG còn hoãn — đã có sẵn.** `AnesthOS/src/domain/calculators/ibw.ts` dùng **Devine 1974**, kèm `ClinicalProvenance` đầy đủ và `ClinicalValidationError` fail-loud. H1 **dùng lại**, không viết mới. Việc còn lại chỉ là đối chiếu xuất xứ đó qua luồng `S3` như mọi khẳng định khác |
| Ô chở "nghiên cứu gốc đo gì, trên ai" | `HoSoBangChung` chưa có ô; A0 đang đóng băng với 100 kiểm thử đỏ — xem `LO_TRINH.md` §3 câu 6 |
| Liều tối đa theo đường dùng cho **mọi** hoạt chất | mới có bằng chứng cho lidocaine; phần còn lại cần một lượt phác đồ nữa |
