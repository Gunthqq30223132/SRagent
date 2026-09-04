# Phác đồ #1 — Đại Cương Về Thuốc Tê · bộ hồ sơ giao việc

> **Người thực hiện**: Antigravity, chạy trên máy Gun (cần đăng nhập NotebookLM).
> **Đặc tả gốc**: `docs/DAC_TA_PHAC_DO_NHAP.md` — đọc trước, tài liệu này không thay thế.
> **Bộ đối chiếu**: `docs/runs/PHAC_DO_01_doi_chieu.json` — **đã chốt, không sửa**.

---

## 1 · Notebook nguồn

| Vai | `notebook_uuid` | Tên | Số nguồn |
|---|---|---|---|
| chính | `e44dacda-9111-4f5c-8fd5-e0e448068b75` | `[GMHS] Đại Cương Về Thuốc Tê` | 19 |
| ngộ độc | `a20c7bf9-c47a-4d4d-b1a7-0fc586372f0c` | `[GMHS] Clinical Manifestations of Local Anesthetic Toxicity (LAST)` | 3 |

**Nhận mã, không nhận tên.** Khớp mờ theo tên chính là cách sự cố luật L7 đã xảy ra:
đúng mã, đúng phép đếm, **nhầm nguồn**, và không gì trong báo cáo cho thấy.

**Mở đầu mỗi lượt chạy, in trước mọi con số** (luật L7):

```
notebook_uuid : <uuid>
số nguồn      : <n>
ngày chạy     : <ISO-8601>
```

---

## 2 · Chín điểm quyết định

### Nhóm 1 — có đối chiếu · 28 khẳng định · **lõi đo được**

Hỏi **cho từng** hoạt chất trong bảy: **lidocaine · bupivacaine · levobupivacaine ·
ropivacaine · mepivacaine · prilocaine · 2-chloroprocaine**.

| # | Câu hỏi | Điều kiện phải nêu rõ trong câu hỏi |
|---|---|---|
| **Q1** | Liều tối đa theo cân nặng, **KHÔNG** kèm adrenaline? | mg/kg · người lớn · không adrenaline |
| **Q2** | Liều tối đa theo cân nặng, **CÓ** kèm adrenaline? | mg/kg · người lớn · có adrenaline |
| **Q3** | Trần tuyệt đối một lần dùng ở người lớn, **KHÔNG** adrenaline? | mg · người lớn · không adrenaline |
| **Q4** | Trần tuyệt đối một lần dùng ở người lớn, **CÓ** adrenaline? | mg · người lớn · có adrenaline |

> ### 「Vì sao phải nêu điều kiện NGAY TRONG câu hỏi」
>
> Hỏi trống *"liều tối đa lidocaine là bao nhiêu?"* thì nguồn trả lời **7 mg/kg** — con
> số đúng cho trường hợp **có adrenaline**. Ghi lại thành "liều tối đa 7 mg/kg" là
> **sai lâm sàng gấp rưỡi**, dù trích dẫn thật và trang thật.
>
> Đây đúng hạng lỗi carvedilol `3,125` đã ghi ở `docs/DAC_TA_A0.md`: **con số sống sót,
> điều kiện thì không.**

### Nhóm 2 — không có đối chiếu, nhưng phác đồ cần

| # | Câu hỏi | Notebook |
|---|---|---|
| **Q5** | Điều chỉnh liều trần ở **suy gan · suy thận · người già · trẻ em · thai kỳ**? | chính |
| **Q6** | **Dấu hiệu sớm** của ngộ độc thuốc tê toàn thân, theo thứ tự xuất hiện? | LAST |
| **Q7** | Xử trí: **liều nhũ tương lipid** khởi đầu và duy trì? | LAST |
| **Q8** | Vị trí tiêm nào **cấm dùng adrenaline**? | chính |
| **Q9** | Chọn thuốc theo loại phong bế — căn cứ nào? | chính |

### Nhóm 3 — **KHÔNG HỎI**

26 khẳng định `concentrations` (nồng độ có bán). **Không hỏi NotebookLM.**

> Nồng độ lidocaine `[0,5 · 1 · 1,5 · 2 · 4 · 5]` là **danh sách ống thuốc có bán**,
> không phải khuyến cáo y khoa. Không sách giáo khoa nào trả lời được *"ở Việt Nam bán
> nồng độ nào"* — hỏi thì sẽ nhận câu trả lời **có trích dẫn đầy đủ mà sai ngữ cảnh**.
>
> Cần **nguồn đăng ký thuốc quốc gia**, là loại nguồn thứ ba hệ chưa có.

---

## 3 · Đầu ra — bản ghi, không phải văn xuôi

Một khẳng định = một bản ghi. Văn xuôi không kiểm được bằng máy.

```json
{
  "notebook_uuid":    "e44dacda-9111-4f5c-8fd5-e0e448068b75",
  "diem_quyet_dinh":  "Q1",
  "ma_doi_chieu":     "lidocaine.maxDoseMgPerKg.plain",
  "khang_dinh":       "4.5",
  "don_vi":           "mg/kg",
  "doi_tuong":        "lidocaine, người lớn",
  "dieu_kien":        ["KHÔNG kèm adrenaline"],
  "trich_nguyen_van": "The maximum recommended dose of lidocaine without epinephrine is 4.5 mg/kg, not to exceed 300 mg.",
  "nguon":            { "ten": "<tên tài liệu trong notebook>", "trang": 12, "muc": "Table 3" },
  "may_noi_gi":       "trich_nguyen_van",
  "canh_bao":         []
}
```

**Sáu trường bắt buộc — thiếu một là bản ghi bị loại:**

| Trường | Vì sao |
|---|---|
| `notebook_uuid` | khai nguồn bằng **mã bất biến**, không bằng tên |
| `ma_doi_chieu` | khoá nối sang `docs/runs/PHAC_DO_01_doi_chieu.json`. Nhóm 2 ghi `null` |
| `trich_nguyen_van` | không có nguyên văn thì **không chạy được phép kiểm số** — trích dẫn chỉ còn là nhãn |
| `dieu_kien` | không có điều kiện nào → ghi `[]` **có chủ ý**, không bỏ trống |
| `may_noi_gi` | `trich_nguyen_van` (chép thẳng) hay `dien_giai` (diễn đạt lại). Mọi bản `dien_giai` **bị đánh dấu, Gun duyệt riêng** |
| `nguon.trang` | không có trang thì không lật ra kiểm lại được |

---

## 4 · Bốn điều cấm

> Series `X` **cục bộ, riêng tài liệu này** — dẫn từ ngoài phải viết đủ
> `PHAC_DO_01.X4`. Trước đây đánh `C1…C4`, đổi 2026-09-04 vì `C` đã là chặng lộ
> trình toàn cục. Xem `QUY_UOC_KY_HIEU.md` §5 va chạm #6.

| # | Cấm | Vì sao |
|---|---|---|
| **X1** | Điền con số **không có** trong `trich_nguyen_van`, dù "biết là đúng" | đó là kiến thức của mô hình, không phải của nguồn — ngoài phạm vi truy vết được |
| **X2** | Gộp nhiều điều kiện vào một khẳng định | *"4,5 mg/kg (7 nếu có adrenaline)"* phải là **hai** bản ghi |
| **X3** | Bỏ bản ghi vì nó mâu thuẫn với bản ghi khác | mâu thuẫn giữa hai nguồn là **phát hiện**, không phải lỗi — giữ cả hai, đánh dấu |
| **X4** | Chép nguyên văn từ **sách giáo khoa** vào kho git | nguồn thương mại: kho chỉ lưu toạ độ + băm + độ dài. Nguyên văn ở lại máy Gun |

**Và một điều cấm nặng nhất, viết riêng:**

> ⛔ **KHÔNG ĐƯỢC mở `docs/runs/PHAC_DO_01_doi_chieu.json` trước khi nộp bản ghi.**
>
> Tệp đó chứa 28 con số của dữ liệu **dựng**. Nhìn thấy chúng trước khi hỏi nguồn là
> **biết đáp án trước khi làm bài** — sau đó không ai phân biệt được "nguồn nói vậy" với
> "tìm cho khớp con số đã thấy".
>
> Đối chiếu là việc **sau khi** nộp, do người khác làm.

---

## 5 · Tự kiểm trước khi nộp

| # | Kiểm | Xử khi trượt |
|---|---|---|
| 1 | Mọi bản ghi đủ 6 trường bắt buộc | bổ sung, hoặc loại và ghi lý do |
| 2 | Mọi **thẻ số** trong `khang_dinh` có mặt trong `trich_nguyen_van` | **giữ lại và đánh dấu** `canh_bao: ["so_khong_khop_nguyen_van"]` — **không** vứt, **không** sửa số cho khớp |
| 3 | Mỗi Q1–Q9 có kết quả, kể cả *"nguồn không trả lời được"* | ghi vào danh sách §6 |
| 4 | Không có `ma_doi_chieu` nào lặp lại | trùng nghĩa là gán nhầm |

---

## 6 · Nộp gì

| # | Tệp | Nội dung |
|---|---|---|
| 1 | `docs/runs/PHAC_DO_01_ban_ghi.json` | toàn bộ bản ghi, kể cả bản đã đánh dấu cảnh báo |
| 2 | `docs/runs/PHAC_DO_01_khong_tra_loi_duoc.md` | **điểm quyết định nguồn KHÔNG trả lời được**, đích danh từng cái |

> ### 「Tệp thứ hai có thể là thứ giá trị nhất lượt này」
>
> Nó chỉ thẳng vào **lỗ hổng của bộ nguồn** — thông tin không thể lấy được bằng cách đọc
> những gì nguồn **trả lời được**.
>
> NotebookLM chỉ trả lời trong phạm vi tài liệu đã nạp. Thiếu một hướng dẫn quan trọng
> thì nó **vẫn viết ra câu trả lời đầy đủ trích dẫn**, và **không tín hiệu nào báo
> thiếu**. Bản đủ và bản thiếu **trông y hệt nhau**.

---

## 7 · Sau khi nộp — không phải việc của Antigravity

| Bước | Ai |
|---|---|
| Gài 5 lỗi đối chứng (2 đổi số · 2 bỏ điều kiện · 1 gán nhầm nguồn) | Claude |
| Duyệt từng bản ghi · **đo tỷ lệ bắt lỗi gài** | **Gun** |
| Đối chiếu bản ghi ĐÃ KÝ với 28 khẳng định dựng | Claude |

> ⚠ **Chưa được ký khẳng định nào** cho tới khi phép kiểm số của A0 (`the_so`,
> `noi_dung_truy_duoc`) cài xong — hiện 100 kiểm thử vẫn đỏ. Bản ghi là **dữ liệu, giữ
> được**; thu trước, kiểm máy sau. Chưa kiểm máy thì chưa đủ điều kiện vào phác đồ.
