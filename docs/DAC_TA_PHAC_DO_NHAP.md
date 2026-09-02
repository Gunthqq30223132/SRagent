# Đặc tả — Antigravity + NotebookLM soạn phác đồ nháp

> **Vai của tài liệu**: nguồn chân lý cho luồng sinh phác đồ. Đi kèm
> `docs/BAN_GIAO_CHANG_A.md` (bản giao việc Chặng A), không thay thế nó.
>
> **Cách đọc**: mỗi cơ chế mở đầu bằng ô 「Nói đơn giản」.
>
> **Cập nhật**: 2026-09-01

---

## 1 · Vì sao có luồng này

> ### 「Nói đơn giản」
>
> Gun đã có sẵn hai thứ: **một kho notebook NotebookLM** dựng từ nguồn anh tự chọn lọc,
> và **thói quen soạn phác đồ trong Notion rồi làm theo đúng cái đã soạn**.
>
> Thay vì Gun tự viết từng phác đồ, máy soạn **bản nháp** từ chính kho nguồn đó, Gun
> duyệt. NotebookLM chỉ trả lời trong phạm vi tài liệu đã nạp và có trích dẫn tới đoạn
> cụ thể — nên bản nháp **mang sẵn vết nguồn**, thứ mà bản viết tay từ trí nhớ không có.

**Đầu ra KHÔNG phải phác đồ dùng được ngay.** Nó là **ứng viên** — chưa qua kiểm máy và
chưa có chữ ký thì không được dùng lâm sàng.

### Chỉnh kỳ vọng: đây không phải tiết kiệm thời gian

| | Gun tự viết | Máy soạn, Gun duyệt |
|---|---|---|
| mỗi khẳng định | **soạn** từ kiến thức — nhanh | **đọc đoạn trích, đối chiếu số, kiểm điều kiện** |
| sản phẩm | phác đồ | phác đồ **+ hồ sơ bằng chứng từng dòng** |

Duyệt đúng cách có thể **chậm hơn** tự viết. Cái được là **vết bằng chứng** — mục đích
của cả dự án. Ghi rõ để không ai vào việc với kỳ vọng sai rồi cắt khâu duyệt.

---

## 2 · Ba lỗ của hướng này, và cách vá

### Lỗ 1 · Trích dẫn là con trỏ, không phải bằng chứng

> ### 「Nói đơn giản」
>
> Máy bảo đảm *"câu này tôi viết dựa trên đoạn kia"*. Nó **không** bảo đảm câu đó **giữ
> nguyên nghĩa** của đoạn kia.
>
> Ca hỏng cụ thể: nguồn viết *"7 mg/kg **khi có adrenaline**"*, máy tóm thành *"liều tối
> đa 7 mg/kg [tr.12]"*. Trích dẫn thật, trang thật, số thật — và **sai lâm sàng**, vì
> một điều kiện bị rơi.
>
> Cùng hạng lỗi với ca carvedilol `3,125` đã ghi ở `docs/DAC_TA_A0.md`: **con số sống
> sót, ý nghĩa thì không.**

**Vá:** bản ghi bắt buộc mang `trich_nguyen_van` + trường `dieu_kien`, rồi chạy qua phép
kiểm A0 (`the_so`, `noi_dung_truy_duoc`).

### Lỗ 2 · Duyệt văn trôi chảy là phép kiểm YẾU HƠN tự viết

> ### 「Nói đơn giản」
>
> Một bản nháp mạch lạc, trích dẫn đầy đủ, làm người đọc **dễ gật hơn** — không phải khó
> hơn. Đó là hiệu ứng mỏ neo.
>
> Trước: Gun viết → Gun ký. Người ký **hiểu sâu vì tự soạn**.
> Sau: máy viết → Gun ký. Người ký **đọc thứ mình không soạn**.

**Vá:** gài lỗi có chủ đích trước khi đưa duyệt (§5, K3). Đo tỷ lệ bắt được **trước khi
tin vòng lặp**.

### Lỗ 3 · Bộ nguồn thành điểm hỏng vô hình

> ### 「Nói đơn giản」
>
> NotebookLM chỉ trả lời trong phạm vi tài liệu đã nạp. Thiếu một hướng dẫn quan trọng
> thì nó **vẫn viết ra phác đồ đầy đủ trích dẫn**, và **không tín hiệu nào báo thiếu**.
> Bản đủ và bản thiếu **trông y hệt nhau**.

Đây đúng bài toán một chiều đã gặp: nguồn tổng hợp chứng minh được **có lỗ hổng**, không
bao giờ chứng minh được **không có lỗ hổng**.

**Vá:** bước A4 — quét Europe PMC tìm bài bậc cao **không có** trong notebook. Biến lỗ
vô hình thành **danh sách có tên**.

---

## 3 · Đầu ra bắt buộc — bản ghi, không phải văn xuôi

Văn xuôi không kiểm được bằng máy.

```json
{
  "notebook_uuid":    "00000000-1111-2222-3333-444444444444",
  "khang_dinh":       "4.5",
  "don_vi":           "mg/kg",
  "doi_tuong":        "lidocaine, gây tê thấm, người lớn",
  "dieu_kien":        ["KHÔNG kèm adrenaline"],
  "trich_nguyen_van": "The maximum recommended dose of lidocaine without epinephrine is 4.5 mg/kg, not to exceed 300 mg.",
  "nguon":            { "ten": "...", "trang": 12, "muc": "Table 3" },
  "may_noi_gi":       "trich_nguyen_van",
  "canh_bao":         []
}
```

**Năm trường bắt buộc — thiếu một là bản ghi bị loại:**

| Trường | Vì sao |
|---|---|
| `notebook_uuid` | khai nguồn bằng **mã bất biến**, không bằng tên. Khớp mờ tên chính là cách sự cố luật L7 đã xảy ra |
| `trich_nguyen_van` | không có nguyên văn thì **không chạy được phép kiểm số** — trích dẫn chỉ còn là nhãn |
| `dieu_kien` | vá cho lỗ 1. Không có điều kiện nào → ghi `[]` **có chủ ý**, không bỏ trống |
| `may_noi_gi` | `trich_nguyen_van` (chép thẳng) hay `dien_giai` (máy diễn đạt lại). Mọi bản ghi `dien_giai` **bị đánh dấu, duyệt riêng** |
| `nguon.trang` | không có trang thì không lật ra kiểm lại được |

---

## 4 · Nhiệm vụ cho Antigravity

| # | Việc | Ràng buộc |
|---|---|---|
| 1 | Nhận **một `notebook_uuid`** | một chủ đề mỗi lượt, không gộp. **Nhận mã, không nhận tên** |
| 2 | Liệt kê **điểm quyết định** của chủ đề trước khi hỏi nội dung | neo vào điểm quyết định, không neo vào chủ đề — nguyên tắc đã dùng ở `tools/dat_cau_hoi.py` |
| 3 | Hỏi NotebookLM và **lấy về nguyên văn đoạn trích**, không chỉ câu tóm | không lấy được nguyên văn → `canh_bao: ["khong_lay_duoc_nguyen_van"]` |
| 4 | Bóc thành bản ghi theo §3 | **không suy ra** con số nào không có trong `trich_nguyen_van` |
| 5 | Tự kiểm: mọi thẻ số của `khang_dinh` phải có trong `trich_nguyen_van` | bản ghi trượt → **giữ lại và đánh dấu**, không vứt, không sửa số cho khớp |
| 6 | Nộp kèm **danh sách điểm quyết định KHÔNG trả lời được** từ bộ nguồn | đây là dữ liệu quý nhất — nó chỉ ra lỗ hổng của bộ nguồn |

**Bốn điều cấm:**

| # | Cấm | Vì sao |
|---|---|---|
| C1 | Điền con số không có trong đoạn trích, dù "biết là đúng" | đó là kiến thức của mô hình, không phải của nguồn — ngoài phạm vi truy vết được |
| C2 | Gộp nhiều điều kiện vào một khẳng định | *"4,5 mg/kg (7 nếu có adrenaline)"* phải là **hai** bản ghi |
| C3 | Bỏ bản ghi vì nó mâu thuẫn với bản ghi khác | mâu thuẫn giữa hai nguồn là **phát hiện**, không phải lỗi — giữ cả hai, đánh dấu |
| C4 | Chép nguyên văn từ **nguồn thương mại** vào kho git | chỉ lưu toạ độ + băm + độ dài. Nguyên văn ở lại máy Gun |

---

## 5 · Nghiệm thu

| # | Kiểm | ĐẠT | TRƯỢT | VÔ HIỆU |
|---|---|---|---|---|
| K1 | Mọi bản ghi đủ 5 trường bắt buộc | 100% đủ | có bản ghi thiếu | — |
| K2 | Thẻ số khớp nguyên văn (phép kiểm A0) | mọi bản ghi `đạt` **hoặc đã đánh dấu** `trượt` | có bản ghi `trượt` **bị giấu** | không lấy được nguyên văn |
| **K3** | **Ca đối chứng dương** — gài 5 lỗi (2 đổi số · 2 bỏ điều kiện · 1 gán nhầm nguồn) | Gun bắt **≥4/5** | bắt ≤2/5 → **vòng duyệt không sống**, dừng và thiết kế lại | — |
| K4 | Danh sách điểm quyết định không trả lời được | có, kèm tên từng điểm | không nộp | — |
| K5 | Đối chiếu A4: bài bậc cao ngoài notebook | danh sách **đích danh** | báo phần trăm không tên bài | Europe PMC không với tới |

> ### 「K3 là mục quan trọng nhất」
>
> Nó **không đo phác đồ — nó đo cổng duyệt.** Một cổng chưa từng bắt được gì thì không
> có bằng chứng nào nói nó đang canh cái gì.
>
> Gài lỗi rồi đo, **trước khi** tin vòng lặp — chứ không tin trước rồi phát hiện sau 200
> khẳng định. Gun **biết trước là có lỗi được gài**, không biết là lỗi nào: đúng như một
> bài nội kiểm chất lượng phòng xét nghiệm, không phải cái bẫy.

---

## 6 · Hiện trạng kho notebook — đo ngày 2026-09-01

Đo trên hai tệp Gun cung cấp. **Hai tệp KHÔNG nằm trong kho git** (chứa cấu trúc tri
thức cá nhân, URL riêng, tài khoản) — kho chỉ giữ số đo rút ra, đúng ranh giới đã đặt
cho nguồn thương mại (C4).

| Hạng mục | Số đo |
|---|---|
| Trang Notion | **5.031** |
| Notebook NotebookLM | **873** |
| Tài liệu nguồn (tổng) | **11.805** · trung vị 6/notebook · lớn nhất 273 |
| Trạng thái *"Đã liên kết TLTK"* | **133 / 873 (15%)** |

### 6.1 · ⚠ Khoá nối chỉ phủ 13% — hai tệp không tệp nào đủ một mình

| | |
|---|---|
| Trang **có** `notebook_uuid` | **115 / 5.031 (2%)** → 112 notebook |
| Notebook **chưa có URL máy dùng được** | **761 / 873 (87%)** |
| Cột link trong tệp CSV | chỉ còn chữ hiển thị `🔗 Mở Notebook` — **URL mất khi xuất** |
| Khớp tên giữa hai tệp | **35 / 114** |

**Không được giả định "tra sổ là ra notebook".** Đúng là: **112 notebook nối được ngay,
761 cái còn lại phải lấy URL trước khi máy chạm tới.**

### 6.2 · ✅ Miền gây mê là miền chín nhất — thí điểm rơi đúng chỗ

| | |
|---|---|
| Notebook GMHS | **36** |
| Đã liên kết TLTK | **35 / 36** (toàn kho chỉ 15%) |

Chủ đề thí điểm A1 nối được ngay: `Đại Cương Về Thuốc Tê` (19 nguồn) ·
`Clinical Manifestations of Local Anesthetic Toxicity` (3 nguồn) ·
`GÂY TÊ TRỤC THẦN KINH` · `GÂY TÊ THẦN KINH CHI TRÊN`.

### 6.3 · ✅ Sửa một kết luận cũ: sách Stoelting's CÓ trong kho

`docs/LO_TRINH.md` §8 từng ghi: `drugs.json` (683 khẳng định P1) trích dẫn *Stoelting's
Pharmacology* nên **"không có cửa tự động nào tới sách"**, và đề xuất truy ngược lên FDA
thay thế. **Kết luận đó SAI.**

| Sách AnesthOS trích dẫn | Notebook |
|---|---|
| Stoelting's Pharmacology and Physiology in Anesthetic | ✅ có (8 nguồn) |
| Stoelting's Anesthesia and Co-Existing Disease | ✅ có (14 nguồn) |
| Miller's Anesthesia 10e | ✅ có (8 nguồn) |
| Chestnut's Obstetric Anesthesia | ✅ có (10 nguồn) |
| **ASRA** — nguồn của `local_anesthetics.json` | ⛔ **KHÔNG có** |

→ Cụm P1 lớn nhất của AnesthOS **truy được thẳng tới nguồn nó đã trích dẫn**.
→ Nhưng **ASRA thiếu**, mà đó là nguồn cấp tệp của chính chủ đề thí điểm.

### 6.4 · ✅ Nỗi lo notebook dùng chung: đo rồi, rất nhỏ

Cảnh báo trước: hai chủ đề chung một notebook thì khẳng định của chúng **chung tổ tiên ở
cấp bộ nguồn** — bẫy đồng thuận ảo ở tầng cao hơn tầng đã chặn.

Đo thật: **3/112 notebook dùng cho nhiều trang, dính 6 trang**, và cả ba là **trang trùng
lặp** (cùng tên, một bản có tiền tố `[GMHS]`) — không phải hai chủ đề khác nhau.

→ Hạ từ *rủi ro kiến trúc* xuống *việc dọn trùng*. Vẫn giữ `notebook_uuid` trong bản ghi
để đo tiếp; **hai khẳng định cùng `notebook_uuid` không bao giờ được tính là hai xác
nhận độc lập.**

### 6.5 · ⚠ Cây Notion chưa dùng làm phạm vi phác đồ được

| Vấn đề | Số đo |
|---|---|
| Gốc cây là **UUID thô** | ~110 gốc kiểu `[26f64a33]`; chỉ 3 gốc có tên: `MEDICAL Hub` (429), `PERSONAL Hub` (307), `SR-Agent Dashboard` (9) |
| Nhánh lớn nhất tên viết tắt | `TKTK (2)` = **1.926 trang** |
| Độ sâu không đều | 3.982 trang ở độ sâu 3; có nhánh sâu tới 7 |

→ **Phạm vi một phác đồ lấy theo `notebook_uuid`** — đơn vị có ranh giới thật là tập
nguồn của notebook đó. **Không** lấy theo nút cây. Cây dùng để định vị, chưa dùng để
phân định phạm vi.

---

## 6b · Lỗ thứ tư, phát hiện ở lượt chạy đầu: SAI LOẠI NGUỒN

> ### 「Nói đơn giản」
>
> Ba lỗ ở §2 đều nói về *"nguồn trả lời sai"*. Lỗ thứ tư khác hẳn: **hỏi nhầm nguồn ngay
> từ đầu**.

Đo trên chủ đề thí điểm — 54 khẳng định ưu tiên 1 của `local_anesthetics.json`:

| Số | Trường | Bản chất | NotebookLM trả lời được? |
|---:|---|---|---|
| **26** | `concentrations` | dữ kiện **thị trường** | ⛔ **không** |
| 14 | `maxDoseMgPerKg` | khuyến cáo lâm sàng | ✅ |
| 14 | `absoluteMaxAdult` | khuyến cáo lâm sàng | ✅ |

**48% khẳng định chết-người của chủ đề này không thuộc loại mà luồng phác đồ trả lời
được.** Sách giáo khoa không biết ở Việt Nam bán nồng độ nào.

Nguy hiểm ở chỗ: hỏi vẫn **ra câu trả lời có trích dẫn đầy đủ** — chỉ là sai ngữ cảnh.
Không phép kiểm nào ở §5 bắt được, vì thẻ số **có** trong nguyên văn, điều kiện **có**
ghi. Chỉ con người biết đây là câu hỏi sai loại.

**Vá — thêm một bước trước khi hỏi:**

> **Phân loại từng điểm quyết định theo LOẠI NGUỒN trước khi mở notebook.**
>
> | Luồng | Bản chất | Nguồn đúng |
> |---|---|---|
> | **A** | hằng số lý hoá (pKa, gắn protein) | dược điển |
> | **B** | dữ kiện thị trường / pháp quy | đăng ký thuốc quốc gia |
> | **C** | khuyến cáo lâm sàng | sách · hướng dẫn hội → **NotebookLM** |
>
> Chỉ **Luồng C** đi qua luồng phác đồ. A và B **gác lại có tên có lý do**, không hỏi.

Xem `docs/DECISIONS.md` #12.

---

## 7 · Ba việc phát sinh — trên máy Gun, không chặn A0

| # | Việc | Vì sao |
|---|---|---|
| 1 | Lấy URL cho **761 notebook** còn thiếu (xuất lại giữ hyperlink, hoặc quét API) | không có URL thì 87% kho nằm ngoài tầm máy |
| 2 | **Bổ sung notebook ASRA** trước khi chạy A1 | nguồn cấp tệp của chủ đề thí điểm đang thiếu |
| 3 | Đặt tên cho các gốc cây UUID | cây chưa điều hướng được bằng máy lẫn bằng mắt |

Cả ba cần đăng nhập Notion → thuộc máy Gun. **Không chặn A0**, phần đó chạy song song.

---

## 8 · Ranh giới với phần còn lại của hệ

```
notebook (Gun chọn, định danh bằng notebook_uuid)
        │
        ▼  Antigravity + NotebookLM
   bản ghi ứng viên  ──►  phép kiểm A0 (the_so, noi_dung_truy_duoc)
        │                        │ số không khớp nguyên văn → đánh dấu
        │                        ▼
        │                 gài 5 lỗi đối chứng (K3)
        │                        ▼
        └──────────────►   Gun duyệt từng bản ghi
                                 ▼
                   phác đồ có chữ ký + hồ sơ bằng chứng
                                 ▼
                   A4: có bài bậc cao NGOÀI notebook không?
```

**Không đổi gì trong `docs/BAN_GIAO_CHANG_A.md`.** A0 vẫn cài như đã giao; A1 nay có
nguồn khẳng định **thật** thay vì 54 khẳng định dựng.
