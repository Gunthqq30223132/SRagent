# Đặc tả A0 — biểu mẫu bằng chứng cấp dòng

> **Vai của tài liệu này**: nguồn chân lý cho bước A0 trong `docs/LO_TRINH.md` §5.1.
> Kiểm thử là **bản diễn dịch** của đặc tả, không thay thế đặc tả.
>
> **Cách đọc**: mỗi cơ chế mở đầu bằng ô **「Nói đơn giản」**. Đọc riêng các ô đó là nắm
> được toàn bộ; phần dưới mỗi ô dành cho người viết mã.
>
> **Trạng thái xuất phát**: 639 kiểm thử xanh tại `cdc0d73`, cổng M6 xanh.

---

## TỪ ĐIỂN

| Thuật ngữ | Nghĩa ở đây |
|---|---|
| **Khẳng định** | một giá trị lá trong JSON của AnesthOS. `lidocaine.maxDoseMgPerKg.plain = 4.5` là **một** khẳng định |
| **Toạ độ nguồn** | chỉ dẫn tới **đúng chỗ** trong tài liệu nguồn nêu con số, kèm đoạn trích nguyên văn |
| **Băm** | chuỗi ngắn tính từ nội dung, kiểu dấu vân tay. Đổi một ký tự → khác hoàn toàn |
| **Vân tay bộ ba** | băm ghép của (tài liệu nguồn ‖ mã đã bóc số ‖ biểu mẫu). Đổi một thứ → khẳng định tụt hạng |
| **Phả hệ** | tại chỗ nêu con số, nguồn này dẫn nghiên cứu gốc nào. **Không** phải cả danh mục tham khảo |
| **Chung tổ tiên** | hai nguồn cùng dẫn về một nghiên cứu gốc → là **một** nguồn chép hai lần |
| **Mức phủ** | bậc thang đo một khẳng định được chống lưng tới đâu. **Tự tính ra, không ai điền** |

---

## 1. Mục đích

> ### 「Nói đơn giản」
>
> A0 **chưa đi tìm bằng chứng nào cả**. A0 chỉ thiết kế **cái biểu mẫu** mà mọi khẳng
> định lâm sàng sau này phải điền vào.
>
> Giống thiết kế **phiếu gây mê** trước ca mổ đầu tiên: quyết định phiếu có ô nào, ô nào
> bắt buộc, và ô nào **tự tính ra chứ không ai được điền tay**.
>
> Thiết kế sai biểu mẫu thì 16.417 khẳng định sau này đều ghi sai chỗ.

Hôm nay **100%** khẳng định ở mức *"chỉ có nguồn cấp tệp"* — trích dẫn trỏ vào **cả
quyển sách**. A0 dựng đường đi từ đó tới *"trỏ đúng câu chữ, và câu chữ đó kiểm lại được"*.

**A0 không nối mạng, không tải tài liệu, không thêm thư viện.** Đi lấy nguồn thật là
Chặng B.

---

## 2. Bốn ô của biểu mẫu

### 2.1 · Toạ độ nguồn — cấp dòng, không cấp tệp

> ### 「Nói đơn giản」
> Khác biệt giữa *"theo hướng dẫn của hội"* và *"hướng dẫn X, bảng 3, dòng ghi
> 4,5 mg/kg"*. Cái sau lật ra kiểm được, cái trước thì không.

```python
class ToaDoNguon(BaseModel):
    ma_tai_lieu:      str   # PMID / DOI / mã nhãn thuốc — định danh ổn định
    loai_tai_lieu:    str   # nhan_thuoc | huong_dan | duoc_dien | bai_bao
    vi_tri:           str   # mục nào, bảng nào, trang nào
    trich_nguyen_van: str   # BẮT BUỘC, không rỗng — đoạn văn chứa con số
```

`trich_nguyen_van` **cắt khoảng trắng hai đầu rồi vẫn rỗng** → **ném lỗi lúc dựng đối
tượng**, không nhận rồi báo sau. Toạ độ không có trích dẫn thì không phải toạ độ.

> Chuỗi `"   "` bị từ chối y như `""` (Critic Q9a): trích dẫn toàn khoảng trắng không
> chứng minh được gì, mà lại **trông như đã có trích dẫn**.

### 2.2 · Phép kiểm "nội dung có truy được trong nguồn không"

> ### 「Nói đơn giản」
>
> Đây là chỗ biến nguyên tắc *"số không bao giờ do máy tự nghĩ ra"* từ lời hứa thành
> **một phép kiểm chạy được**: mọi con số trong khẳng định **phải có mặt** trong đoạn
> trích nguyên văn. Không chứng minh được → khẳng định **không lên hạng**.

**Ba loại nội dung, ba số phận khác nhau** — đo trên dữ liệu thật:

| Loại nội dung | Ví dụ | Số khẳng định P1 | A0 xử |
|---|---|---:|---|
| **Có số** | `4.5` · `5–10 mg PO once daily` | **1.630** (71,8%) | **kiểm tự động** |
| **Từ vựng đóng** | `IV` · `TBW` · `Continue.` | **~515** | `KHÔNG KIỂM ĐƯỢC` — ghi rõ lý do |
| **Văn xuôi tự do** | câu mô tả dài | ~87 | `KHÔNG KIỂM ĐƯỢC` — cần người |

> **Điều đáng chú ý khi đo:** 641 khẳng định P1 "thuần chữ" hoá ra **hầu hết không phải
> văn xuôi** — chúng là **từ vựng đóng**: `periop` (238 giá trị kiểu *Continue. / Hold.*),
> `routes`/`route` (181 giá trị *IV / IM / IV infusion*), `weightBasis` (96 giá trị
> *TBW / IBW*). Chỉ 213 giá trị khác nhau trên 641 khẳng định.
>
> Nghĩa là chúng **kiểm được bằng máy**, chỉ bằng một cơ chế khác: đối chiếu với một
> **danh mục từ vựng đã khai**, không phải đối chiếu con số. **A0 không xây cơ chế đó**
> — chỉ phân loại và ghi lý do, để Chặng B biết miếng bánh này to bằng nào.
>
> **Và một lỗi dữ liệu phát hiện lúc đo:** **39** khẳng định P1 có giá trị **rỗng**.
> Một trường chết-người mà để trống. Ghi vào sổ, xử ở Chặng B.

#### Quy tắc bóc thẻ số — phải tất định

```python
def the_so(s: str) -> set[Decimal]
```

| Bước | Quy tắc |
|---|---|
| 1 | Chuẩn hoá gạch nối: `–` `—` `−` → `-` |
| 2 | Tìm mọi khớp của `\d+(?:[.,]\d+)?` |
| 3 | Dấu phẩy theo sau bởi **1–2** chữ số → dấu thập phân (`4,5` → `4.5`) |
| 4 | Dấu phẩy theo sau bởi **số chữ số KHÁC 1–2** → **NHẬP NHẰNG**. `1,500` = một nghìn rưỡi hay một phẩy năm? `1,5000` thì không phải cách viết hợp lệ nào cả (Critic Q9b) |
| 5 | Chuyển sang `Decimal`, trả về **tập hợp** |

**Bước 4 là chỗ chọn thà dừng còn hơn đoán.** Gặp số nhập nhằng → cả phép kiểm trả
`KHÔNG KIỂM ĐƯỢC` kèm lý do, **không tự chọn một cách hiểu**.

> ### 「Không phải lo xa — dữ liệu thật đã có sẵn ca đó」
>
> Quét toàn kho: **14** khẳng định chứa dạng `<số>,<3 chữ số>` (4 cái ở ưu tiên 1).
> Ca đầu tiên trong đó:
>
> ```json
> { "name": "Carvedilol", "smartDose": "3,125–25 mg PO BD" }
> ```
>
> Liều khởi đầu thật của carvedilol là **3,125 mg** — dấu phẩy ở đây là **dấu thập
> phân**. Quy tắc "phẩy + 3 chữ số = hàng nghìn" sẽ đọc thành **3125 mg**: sai **1000
> lần**, trên một thuốc chẹn beta không chọn lọc.
>
> Nếu A0 chọn đoán thay vì dừng, đặc tả này đã **nướng sẵn một lỗi nghìn lần vào nền hệ
> thống** — và nó sẽ im lặng, vì con số vẫn "kiểm được" và vẫn "khớp".

Mười bốn ca đó còn lộ ra **hai loại nội dung nữa** mà phép kiểm số không áp được:

| Dạng | Ví dụ thật | A0 xử |
|---|---|---|
| **Tỷ lệ pha loãng** | `1:10,000 = 100 mcg/mL` (adrenaline) | `SO_NHAP_NHANG` — Chặng B cần quy tắc riêng cho ký hiệu tỷ lệ |
| **Chuỗi trích dẫn** | `Walker BJ et al. Anesthesiology 2018;129` | số trong đó là **năm và số tập**, không phải liều — xem quy tắc ngay dưới |

**Quy tắc loại trừ theo khoá** (Critic Q7): khẳng định có `khoa == "references"` **không
được** đưa qua phép kiểm số — trả `KHÔNG KIỂM ĐƯỢC` / `KHANG_DINH_KHONG_SO`. Cho một
chuỗi trích dẫn qua phép kiểm liều nghĩa là coi **năm xuất bản và số tập** như thể chúng
là liều thuốc.

**So bằng tập hợp `Decimal`, không so chuỗi.** Lý do: `4.50` và `4.5` là **một** giá trị;
còn so chuỗi con thì `5` sẽ khớp nhầm vào `500` — cho ĐẠT sai.

#### Ba kết quả

| Kết quả | Khi nào |
|---|---|
| `ĐẠT` | mọi thẻ số của khẳng định ⊆ thẻ số của trích dẫn |
| `TRƯỢT` | có thẻ số **không** tìm thấy → **nghi bịa số** |
| `KHÔNG KIỂM ĐƯỢC` | chưa có toạ độ nguồn · hoặc khẳng định không chứa số · hoặc gặp số nhập nhằng |

**Dùng lại, không viết mới:** `verify_quote()` trong `tools/screen_run.py` đã có sẵn phép
chuẩn hoá và so nguyên văn.

### 2.3 · Vân tay bộ ba — để chữ ký tự hết hạn

> ### 「Nói đơn giản」
>
> Anh ký duyệt một con số hôm nay. **Sáu tháng sau nhà sản xuất sửa nhãn thuốc.** Chữ ký
> cũ vẫn nằm đó, trông vẫn hợp lệ — nhưng nó đang bảo chứng cho một tài liệu **không còn
> tồn tại ở dạng đó**.
>
> Giống một **kết quả xét nghiệm**: nó chỉ có giá trị cho đúng mẫu đó, đúng phương pháp
> đó, đúng khoảng tham chiếu đó. Labo đổi bộ kit → kết quả cũ không mặc nhiên còn dùng.

Khoá vào ba thứ cùng lúc:

| Khoá vào | Đổi nghĩa là |
|---|---|
| nội dung **tài liệu nguồn** | nhà sản xuất / hội đã sửa nhãn, sửa hướng dẫn |
| **đoạn mã đã bóc số** | cách đọc đã đổi → số bóc ra có thể khác |
| **biểu mẫu** đang dùng | cấu trúc dữ liệu đã đổi |

```python
def van_tay_bo_ba(bam_nguon: str, bam_ma_rut: str, bam_luoc_do: str) -> str
    # trả ĐÚNG dạng "sha256:<16 hex>" — hai phần, KHÔNG có phần thứ ba
```

> **Đính chính (Critic Q4).** Bản trước ghi *"cùng định dạng `van_tay_kho()`"*, nhưng
> `van_tay_kho()` trả **ba** phần `sha256:<16hex>:<số bản ghi>`. Hai vế loại trừ nhau.
> Chốt: `van_tay_bo_ba` trả **hai** phần — không có phần đếm, vì bộ ba **luôn đúng ba
> thành phần**, đếm một hằng số là vô nghĩa.
>
> **Ghép ba thành phần phải có dấu ngăn không xuất hiện được trong băm** (dùng `\n`).
> Nối chuỗi thẳng thì `("ab","c","d")` và `("a","bc","d")` cho **cùng** vân tay — hai
> nguồn khác nhau đội chung một chữ ký.

Hồ sơ giữ **hai** trường: `van_tay_tham_dinh` (lúc được thẩm định) và `van_tay_hien_tai`
(tính lại lúc đọc). Vân tay **còn hiệu lực** khi và chỉ khi cả hai khác `None` **và** bằng nhau.

> **Điểm cốt lõi về thiết kế:** việc tụt hạng là một **thuộc tính được tính ra**, không
> phải một tiến trình chạy nền. **Không có gì để chạy, nên không có gì để quên chạy.**

**Dùng lại:** `van_tay_kho()`, `van_tay_tu_tep()` trong `tools/so_quyet_dinh.py`.

### 2.4 · Bốn trạng thái đồng thuận

> ### 「Nói đơn giản」
>
> Hai nguồn cùng nói "4,5 mg/kg" **không có nghĩa là hai bằng chứng độc lập** — rất có
> thể cả hai đang dẫn lại **cùng một nghiên cứu 1978**. Giống hai bác sĩ đồng ý nhau vì
> **cùng học một thầy**: đó là một ý kiến, không phải hai.
>
> Nên biểu mẫu không được có ô "đồng ý / không đồng ý". Phải có **bốn** ô.

| Trạng thái | Nghĩa | Một người ký đủ? |
|---|---|---|
| `MOT_NGUON` | chỉ tìm được một nguồn | ⛔ |
| `KHONG_DO_DUOC_DOC_LAP` | ít nhất một nguồn **không khai** phả hệ | ⛔ |
| `CHUNG_TO_TIEN` | các nguồn cùng dẫn về một gốc | ⛔ **tính là một** |
| `DOC_LAP` | ≥2 nguồn, gốc **khác nhau** | ✅ |

Suy ra từ `nguon: list[ToaDoNguon]` và `pha_he: dict[ma_tai_lieu, list[ma_bai_goc]]`,
**theo đúng thứ tự này**:

| # | Điều kiện | Kết quả |
|---|---|---|
| 1 | `len(nguon) < 2` | `MOT_NGUON` |
| 2 | **bất kỳ** nguồn nào thiếu phả hệ, hoặc phả hệ rỗng | `KHONG_DO_DUOC_DOC_LAP` |
| 3 | gom cụm bắc cầu theo phả hệ giao nhau → còn **1** cụm | `CHUNG_TO_TIEN` |
| 4 | còn **≥2** cụm | `DOC_LAP` |

> ### 「Thứ tự này phải khoá bằng kiểm thử」
>
> Bước 2 **phải chạy trước** bước 4. Một nguồn không cho biết nó dẫn từ đâu thì **không
> được suy ra là độc lập**, kể cả khi nguồn kia trông có vẻ khác gốc.
>
> Đảo hai bước này là bẫy đồng thuận ảo quay lại — lần này núp trong mã.

Gom cụm ở A0 làm bằng **phép giao tập hợp thuần**, không thư viện. Ca bắc cầu phải đúng:
A∩B = ∅, B∩C ≠ ∅, A∩C = ∅ → hai cụm `{A}` và `{B,C}` → `DOC_LAP`.

*(Phả hệ nhiều chặng — hướng dẫn dẫn hướng dẫn dẫn nghiên cứu — để A3.)*

### 2.5 · Thang mức phủ 4 bậc

> ### 「Nói đơn giản」
>
> Thang hiện tại có 3 bậc, nhưng **cả 16.417 khẳng định rơi vào đúng một bậc**. Một thang
> mà mọi bệnh nhân đều cùng hạng thì **không phân loại được ai** — như phân loại ASA mà
> cả khoa đều ASA II. Nó không sai, nó **vô dụng**.
>
> Thêm một bậc ở giữa, đúng chỗ Chặng B sẽ sinh kết quả, để thang **đo được tiến độ**.

| Bậc | Điều kiện | Số hôm nay |
|---|---|---:|
| `KHONG_CO` | không có gì | 0 |
| `NGUON_CAP_TEP` | có trích dẫn cấp tệp *(đổi tên từ `CHI_CO_NGUON`)* | **16.417** |
| **`DA_DOI_CHIEU`** ← bậc mới | có toạ độ cấp dòng **và** nội dung `ĐẠT` **và** vân tay còn hiệu lực | 0 |
| `CO_CHUOI_DAY_DU` | **đạt đủ `DA_DOI_CHIEU`, CỘNG THÊM** phả hệ **và** `bac_chung_cu` **và** `do_manh` (GRADE) **và** đồng thuận ≠ `KHONG_DO_DUOC` | 0 |

Xét từ bậc **cao xuống thấp**, dừng ở bậc đầu tiên thoả.

> **`CO_CHUOI_DAY_DU` CỘNG DỒN lên `DA_DOI_CHIEU`** (Critic Q6). Không có toạ độ nguồn
> thì **không** thể có chuỗi đầy đủ, dù đã điền phả hệ, bậc chứng cứ và GRADE. Chữ
> "GRADE" ở bảng trên ánh xạ vào trường `do_manh` (Critic Q9d).

> ### 「Vì sao bậc này phải TỰ TÍNH, không được điền tay」
>
> Nếu bậc là ô **ai đó tick vào** thì nó thành lời tự khai, mà lời tự khai không kiểm
> được. Đây đúng lỗi "cột Đã‑thẩm‑định tự tick" từng làm hỏng một bản kiểm toán cũ.
>
> Nếu bậc **tự tính ra** từ các ô khác thì không ai khai gian được mà không khai gian cả
> các ô nguồn — mà các ô nguồn thì kiểm được.
>
> Giống BMI: không ai "khai" BMI, nó tính ra từ cân nặng và chiều cao.

---

## 3. Giao diện

```python
# tools/so_phu_bang_chung.py — mở rộng, không viết lại

class MucPhu(str, Enum):
    KHONG_CO        = "không có gì chống lưng"
    NGUON_CAP_TEP   = "chỉ có nguồn cấp tệp"        # đổi tên từ CHI_CO_NGUON
    DA_DOI_CHIEU    = "đã đối chiếu tới dòng"        # BẬC MỚI
    CO_CHUOI_DAY_DU = "có chuỗi bằng chứng đầy đủ"

class DongThuan(str, Enum):
    MOT_NGUON             = "chỉ có một nguồn"
    KHONG_DO_DUOC_DOC_LAP = "không đo được tính độc lập"
    CHUNG_TO_TIEN         = "chung tổ tiên — tính là một nguồn"
    DOC_LAP               = "độc lập — phả hệ khác nhau"

class LyDoKhongKiemDuoc(str, Enum):
    CHUA_CO_TOA_DO   = "chưa có toạ độ nguồn"
    KHANG_DINH_KHONG_SO = "khẳng định không chứa số"
    SO_NHAP_NHANG    = "số nhập nhằng dấu phân cách"

class ToaDoNguon(BaseModel):
    ma_tai_lieu:      str
    loai_tai_lieu:    str
    vi_tri:           str
    trich_nguyen_van: str        # cắt khoảng trắng hai đầu rồi phải còn ký tự

class HoSoBangChung(BaseModel):
    # — giữ nguyên từ V1 —
    duong_dan:  str
    khoa:       str
    khang_dinh: str
    muc_rui_ro: int
    nguon_khai: str | None = None
    bac_chung_cu: int | None = None
    do_manh:      str | None = None

    # — A0 thêm —
    nguon:              list[ToaDoNguon]      = []
    pha_he:             dict[str, list[str]]  = {}
    van_tay_tham_dinh:  str | None = None
    van_tay_hien_tai:   str | None = None

    @property
    def noi_dung_truy_duoc(self) -> TrangThai:  ...   # §2.2
    @property
    def ly_do_khong_kiem(self) -> LyDoKhongKiemDuoc | None: ...
    @property
    def van_tay_con_hieu_luc(self) -> bool:     ...   # §2.3
    @property
    def dong_thuan(self) -> DongThuan:          ...   # §2.4
    @property
    def muc_phu(self) -> MucPhu:                ...   # §2.5

class SoNhapNhang(ValueError):
    """Gặp `<số>,<đúng 3 chữ số>` — không quyết được hàng nghìn hay thập phân."""

def the_so(s: str) -> set[Decimal]      # NÉM SoNhapNhang khi gặp số nhập nhằng
def van_tay_bo_ba(bam_nguon: str, bam_ma_rut: str, bam_luoc_do: str) -> str
```

> **Vì sao `the_so` NÉM LỖI chứ không trả tập rỗng hay `None`.** Chữ ký trả
> `set[Decimal]` không có chỗ nào chở được lý do. Trả tập rỗng thì chỗ gọi không phân
> biệt được *"khẳng định không có số"* với *"có số nhưng không đọc nổi"* — hai thứ dẫn
> tới hai kết luận khác hẳn nhau. Ném lỗi buộc mọi chỗ gọi phải xử tường minh; quên xử
> thì vỡ to, không im lặng sai.
>
> `noi_dung_truy_duoc` bắt `SoNhapNhang` và trả `KHÔNG KIỂM ĐƯỢC` kèm
> `ly_do_khong_kiem = SO_NHAP_NHANG`.

**Trường `bo_ba` và `doi_chieu_nguoc` của V1 bị `nguon` + `pha_he` + `noi_dung_truy_duoc`
thay thế.** Không giữ song song hai cách biểu diễn cùng một việc.

### Ràng buộc bất biến

> **Mã tài liệu: `A0`.** R-series dưới đây **cục bộ, riêng của đặc tả này** — `A0.R1`
> nói về mọi `@property`, còn `V1.R1` nói về `muc_phu`: **hai luật khác nhau, trùng tên
> là do cùng đánh số từ 1**. Dẫn từ tài liệu khác phải viết đủ `A0.R4`.
> Xem `docs/QUY_UOC_KY_HIEU.md`.

| # | Ràng buộc | Vì sao |
|---|---|---|
| **R1** | **Mọi** thuộc tính ở §3 là `@property`, **không có setter** | trường tự khai độ tin cậy là chế độ hỏng đã gặp |
| **R2** | `DA_DOI_CHIEU` đòi **cả ba**: toạ độ · nội dung `ĐẠT` · vân tay còn hiệu lực | thiếu một mắt là chưa đối chiếu |
| **R3** | Bước 2 của §2.4 chạy **trước** bước 4 | không đo được ≠ độc lập |
| **R4** | `van_tay_tham_dinh` khác `van_tay_hien_tai` → **không** bậc nào cao hơn `NGUON_CAP_TEP` | chữ ký hết hiệu lực thì hạng cũng hết |
| **R5** | Chỉ **đọc** dữ liệu AnesthOS, không ghi | kho khác, quyết định khác |
| **R6** | Không gọi mạng | A0 phải chạy được khi mất mạng |

---

## 4. Tiêu chuẩn nghiệm thu

```bash
python3 tools/so_phu_bang_chung.py --du-lieu <AnesthOS>/src/domain/data/
```

> ### 「Dữ liệu để đo nằm ở đâu」 — Critic Q10
>
> **Cây làm việc của AnesthOS KHÔNG chứa dữ liệu.** `src/domain/data/` ở nhánh đang
> checkout có **0 tệp JSON**. Dữ liệu thật nằm ở nhánh **`origin/feat/p1-domain`**.
>
> Nên AG‑3 phải **bày dữ liệu ra trước khi đo**, và bày bằng **git**, không bằng cách đi
> tìm thư mục trên ổ đĩa — vì đi tìm thư mục chính là cách sự cố cũ đã xảy ra (luật L7):
>
> ```bash
> git -C <AnesthOS-app> ls-tree -r --name-only origin/feat/p1-domain \
>   | grep 'domain/data/.*\.json$' | wc -l      # PHẢI ra 23
> #
> # Lệnh trước thiếu `\.json$` nên bắt 25 dòng (dính index.ts, types.ts) — TRƯỢT
> # TRÊN DỮ LIỆU ĐÚNG.
> ```
>
> **Không bày được thì báo `KHÔNG ĐO ĐƯỢC`, tuyệt đối không báo ĐẠT** (nguyên tắc 4).
> Hiện tại Đ1–Đ8 **chưa có gì trong kho ràng buộc** — không kiểm thử, không script,
> không cổng. Bịt chỗ này là việc của bước AG‑3, và phải bịt trước khi ai nói "A0 xong".

**In đường dẫn tuyệt đối và số tệp JSON đọc được TRƯỚC mọi con số khác** (luật L7).
Thiếu `provenance_manifest.json` → **DỪNG** (luật L8).

| # | Phải ra đúng | Lệch thì |
|---|---|---|
| Đ1 | `NGUON_CAP_TEP` = **16.417** | → dừng |
| **Đ2** | `DA_DOI_CHIEU` = **0** | **cổng chống tự khai** → dừng |
| **Đ3** | `CO_CHUOI_DAY_DU` = **0** | **cổng chống tự khai** → dừng |
| Đ4 | `KHONG_CO` = **0** | → dừng |
| Đ5 | Tổng = **16.417**; ưu tiên 1 = **2.271** | đổi tên thang đã đổi cả ngữ nghĩa → dừng |
| Đ6 | `dong_thuan` = `MOT_NGUON` cho **cả 16.417** | chưa nguồn nào được nạp |
| Đ7 | Khẳng định **chứa chữ số** = **4.016**; riêng ưu tiên 1 = **1.630** | quy tắc đếm sai → dừng |
| Đ8 | Khẳng định gặp `SO_NHAP_NHANG` = **14** (ưu tiên 1: **4**) | ra 0 nghĩa là bước 4 đang **đoán thay vì dừng** → dừng ngay |

> **Đ7 đếm trên TẬP NÀO, và bằng phép nào.**
>
> **Tập đếm: 16.417 khẳng định lâm sàng** — tức đã loại 3.862 lá nhãn/định danh/trình
> bày. Đếm trên tập khác cho số khác, và cả hai đều đúng với câu hỏi của nó:
>
> | Tập | Kết quả |
> |---|---|
> | mọi lá, chỉ loại tệp khai xuất xứ | 4.092 |
> | **chỉ 16.417 khẳng định lâm sàng** | **4.016** ← Đ7 dùng số này |
>
> Chênh 76 là số lá nhãn có chứa chữ số. Hai lượt đếm độc lập từng ra 4.016 và 4.092;
> truy ra là **khác tập đếm, không phải sai phép đếm** — nên đặc tả phải nói rõ tập,
> không chỉ nói phép.
>
> **Phép đếm:** khẳng định mà **chuỗi chứa ít nhất một chữ số** — KHÔNG phải đếm
> `len(the_so(x)) > 0`. Hai phép lệch nhau **đúng 4**: bốn khẳng
> định nhập nhằng ở ưu tiên 1 **có** chữ số nên nằm trong 1.630 của Đ7, nhưng `the_so()`
> **ném lỗi** trên chúng nên phép đếm kia bỏ ra, cho 1.626.
>
> **Đ8 là tập con của Đ7**, không phải tập rời. Dùng nhầm phép đếm tạo một "bất đồng
> giả" lệch đúng 4, và người cài đặt sẽ đi tìm một lỗi không tồn tại.

> **Đ2 và Đ3 là hai mục quan trọng nhất.** A0 chưa đi lấy nguồn nào. Nếu có khẳng định
> nào tự lên bậc `DA_DOI_CHIEU` thì biểu mẫu **đang tự phong hạng cho chính nó** — đúng
> lỗi cả thiết kế này dựng lên để chặn. Ra khác 0 thì **dừng và báo**, đừng đi tiếp.

### Ca kiểm thử bắt buộc, trên mẫu dựng tay

| Ca | Phải ra |
|---|---|
| khẳng định `"4.5"`, trích dẫn *"…not to exceed 4.5 mg/kg…"* | `ĐẠT` |
| khẳng định `"4.50"`, trích dẫn có `4.5` | `ĐẠT` — so `Decimal`, không so chuỗi |
| khẳng định `"5"`, trích dẫn chỉ có `500` | **`TRƯỢT`** — không được khớp chuỗi con |
| khẳng định `"1,500 mg"` | `KHÔNG KIỂM ĐƯỢC` / `SO_NHAP_NHANG` |
| khẳng định `"3,125–25 mg PO BD"` (ca carvedilol thật) | `SO_NHAP_NHANG` — **tuyệt đối không** được ra `{3125, 25}` |
| khẳng định `"IV"` | `KHÔNG KIỂM ĐƯỢC` / `KHANG_DINH_KHONG_SO` |
| 2 nguồn, một nguồn **không có phả hệ**, nguồn kia phả hệ khác | **`KHONG_DO_DUOC_DOC_LAP`**, không phải `DOC_LAP` |
| 2 nguồn cùng dẫn PMID 12345 | `CHUNG_TO_TIEN` |
| 3 nguồn: A∩B = ∅, B∩C ≠ ∅, A∩C = ∅ | `DOC_LAP` (hai cụm) |
| đủ mọi điều kiện, nhưng `van_tay_hien_tai` ≠ `van_tay_tham_dinh` | `NGUON_CAP_TEP` — **R4** |
| `ToaDoNguon` với `trich_nguyen_van=""` | **ném lỗi lúc dựng** |

### Vì sao KHÔNG kèm đoạn mã đã tính Đ1–Đ8

Bảy con số này do Claude tính bằng một đoạn mã dùng một lần, **cố ý không đưa vào kho**.

| Cài từ **quy tắc §2** | Dò ngược để khớp số |
|---|---|
| Số khớp = **hai lần đọc độc lập cùng ra một kết quả** | Số khớp **không chứng minh gì** |
| Lỗi trong cách đọc của Claude **lộ ra** | Lỗi đó **nhân bản** và biến mất khỏi tầm nhìn |

**Số của bạn lệch Đ1–Đ8 → đó là BẤT ĐỒNG THẬT.** Ghi cả hai số, chỉ ra khoá nào đếm
khác, chuyển Gun quyết. Bốn con số của V1 **đã sai một lần rồi**
(20.416/16.562/2.241 → 20.279/16.417/2.271) — chúng là **số đo, không phải chân lý**.

---

## 5. Phân vai — không ai chấm bài của chính mình

| Vai | Được làm | **Cấm** |
|---|---|---|
| Claude | đặc tả này, tính Đ1–Đ8 | viết mã cài đặt, tự chạy nghiệm thu |
| **AG‑2** | sửa **9 dòng** trong kiểm thử V1 + viết kiểm thử A0 | đọc mã AG‑1, chạm `tools/**` |
| **AG‑1** | `tools/so_phu_bang_chung.py` | chạm `tests/**`, **dò ngược Đ1–Đ8** |
| **AG‑3** | chạy nghiệm thu trên mã đã đẩy, **chỉ báo số** | sửa bất cứ thứ gì |
| Gun | duyệt lâm sàng | — |

> ### 「Vì sao kiểm thử phải có TRƯỚC mã」
>
> Viết mã trước rồi viết kiểm thử sau thì người viết sẽ vô thức viết kiểm thử **vừa khít
> với mã mình vừa viết** — kể cả khi mã sai. Giống **đăng ký đề cương trước khi thu số
> liệu**: chốt tiêu chí trước, để kết quả không uốn theo tiêu chí.
>
> Nên **commit đầu tiên của AG‑2 bắt buộc ĐỎ**. Đó là ngoại lệ duy nhất của luật L6, với
> ba điều kiện: chỉ chạm `tests/**` · thông điệp ghi **chính xác số kiểm thử đỏ** · đỏ vì
> **thiếu mã**, không vì `skip`/`xfail`/`assert True`.

> **Bước 1 chạm bao nhiêu dòng kiểm thử V1** (Critic Q3). **9 dòng**, không phải 5:
> 2 dòng đổi `CHI_CO_NGUON` → `NGUON_CAP_TEP`, và 7 dòng bỏ `bo_ba`/`doi_chieu_nguoc`.
> Đo bằng bản mô phỏng: **2 kiểm thử V1 sẽ đỏ** khi AG‑1 cài A0. Vì AG‑1 **cấm chạm
> `tests/`**, AG‑2 phải sửa xong **ngay ở commit đỏ đầu tiên** — bỏ qua là đẩy AG‑1 vào
> chỗ buộc phải vi phạm phân vai.

### Thứ tự bắt buộc

```
1. AG-2  → sửa 9 dòng trong tests/test_so_phu_bang_chung.py
           + viết tests/test_a0_*.py                        (ĐỎ, ghi rõ số đỏ)
2. AG-1  → tools/so_phu_bang_chung.py                        (chuyển XANH)
3. AG-3  → chạy nghiệm thu + bash scripts/gate_m6.sh         (chỉ báo số)
4. Gun   → duyệt
```

Mỗi bước: `python3 -m pytest` phải xanh (trừ bước 1) và **số kiểm thử chỉ tăng** từ 639.
`bash scripts/gate_m6.sh` phải qua.

---

## 6. Chưa đặc tả — chờ cổng

| Việc | Chờ gì |
|---|---|
| Danh mục **từ vựng đóng** cho `periop` / `routes` / `weightBasis` (~515 khẳng định P1) | Chặng B — cần biết nguồn nào khai danh mục chuẩn |
| **39** khẳng định P1 giá trị **rỗng** | ghi vào sổ; xử theo lớp ở Chặng B, **không sửa lẻ** |
| Phả hệ **nhiều chặng** | A3 — và chỉ khi A1 chứng minh là có thật |
| Nghĩa đầy đủ của nhãn `EF2` | cần sửa cấu trúc kho tạm |
