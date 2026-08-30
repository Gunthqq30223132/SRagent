# Đặc tả V1 — Sổ phủ bằng chứng

> **Vai người viết tài liệu này:** Đặc tả (Claude). Claude **không** viết mã cài
> đặt và **không** tự chạy nghiệm thu. Xem §5.
> **Nguyên tắc gốc:** ĐÚNG trước MỚI. Kế hoạch đầy đủ:
> `/root/.claude/plans/resilient-herding-raven.md`.

---

## TỪ ĐIỂN

| Thuật ngữ | Nghĩa |
|---|---|
| **Khẳng định** (*claim*) | Một điều ứng dụng AnesthOS **nói với bác sĩ**. Ví dụ *"liều tối đa 15 mg"*. Đơn vị nhỏ nhất cần có bằng chứng. |
| **Lá** (*leaf*) | Một giá trị vô hướng trong cây JSON (chuỗi, số, luận lý, rỗng). Mỗi lá là ứng viên của một khẳng định. |
| **Sổ phủ** | Bảng liệt kê **mọi** khẳng định kèm mức bằng chứng hiện có. Mục đích chính: **làm cho sự thiếu vắng nhìn thấy được**. |
| **Tệp khai xuất xứ** | `provenance_manifest.json` — khai mỗi *tệp dữ liệu* lấy nguồn từ đâu. Là **siêu dữ liệu về nguồn**, không phải khẳng định lâm sàng. |

---

## 1. Mục đích

Hôm nay AnesthOS trình bày **16.417** khẳng định lâm sàng với **vẻ đáng tin như
nhau**. Không có cách nào phân biệt khẳng định đã truy được về nghiên cứu gốc với
khẳng định chưa ai kiểm.

V1 không xác minh gì cả. V1 chỉ trả lời **một** câu hỏi:

> Khẳng định nào hiện **không có gì chống lưng**, và nếu sai thì **hại đến đâu**?

Đó là thành quả rẻ nhất có giá trị lâm sàng ngay — không cần mạng, không cần
văn bản nguồn.

---

## 2. Quy tắc đếm — phải tất định, không được suy diễn

Toàn bộ tiêu chuẩn nghiệm thu treo trên quy tắc này. Mơ hồ một chỗ là số không
tái lập được và cổng kiểm sẽ báo động giả.

### 2.1 Duyệt cây

| Gặp | Làm |
|---|---|
| Từ điển (`dict`) | duyệt từng cặp khoá–giá trị; **bỏ qua** khoá bắt đầu bằng `_` |
| Danh sách (`list`) | duyệt từng phần tử, **giữ nguyên khoá của từ điển cha** |
| Giá trị vô hướng | **đếm là một lá**, gán cho khoá đang giữ |

Ví dụ: `{"routes": ["IV", "PO"]}` → **2 lá**, cả hai mang khoá `routes`.

### 2.2 Tệp bị loại khỏi phạm vi

| Tệp | Vì sao |
|---|---|
| `provenance_manifest.json` | Là **siêu dữ liệu về nguồn**, không phải điều app nói với bác sĩ. Đếm nó vào là sai loại (137 lá). |

### 2.3 Ba tập khoá

**Nhóm nhãn — không cần bằng chứng** (định danh + trình bày):

```
name  id  aliases  category  label  name_vi  label_vi  title  code
unit  abbr  short  key  group  icon  color  textColor
```

**Ưu tiên 1 — sai thì chết người:**

```
critical  dose  smartDose  max  periop  redFlags  route  routes
weightBasis  concentrations  withEpi  plain  timeToDeath
```

**Ưu tiên 2 — sai thì hại nặng:**

```
preferred  cautions  contraindications  interactions  drugCautions  sideEffects
indication  indications  timing  conditional  severity  action  urgency
triggerFlags  bleedingRisk  range  yellow  low  high  technique  techniques
options  required  typicalAgents  keyDrugs  severityScore  tier
```

**Mặc định:** khoá **không** nằm trong ba tập trên → **ưu tiên 3**.

Mặc định phải là 3, không phải 1. Bộ dữ liệu có **292 khoá hiếm** (dưới 20 lá,
tổng 763 lá); để mặc định cao sẽ thổi phồng nhóm nguy hiểm bằng nhiễu và làm hỏng
chính công dụng của việc xếp hạng.

### 2.4 Căn cứ xếp một số khoá gây tranh cãi

Xếp bằng **mẫu giá trị thật**, không bằng phỏng đoán từ tên khoá:

| Khoá | Giá trị thật | Xếp | Lý do |
|---|---|---|---|
| `timing` (463) | *"after delivery"*, *"on indication"* | 2 | thời điểm **xét nghiệm**, không phải thời điểm dùng thuốc |
| `conditional` (434) | *"ECG if cardiac"* | 2 | chỉ định xét nghiệm có điều kiện |
| `smartDose` (346) | liều thuốc | **1** | **là liều** — loại nó mà giữ `dose` là mâu thuẫn |
| `weightBasis` (96) | *"IBW"*, *"TBW"*, *"None"* | **1** | hệ số nhân liều; nhầm ở người béo phì / trẻ em gây quá liều nhiều lần |
| `max` (68) | *"2"*, *"15"*, *"50"* | **1** | liều tối đa **chính là** ngưỡng ngộ độc |
| `route`+`routes` (235) | *"IV"*, *"PO"*, *"IV slow"* | **1** | nhầm đường dùng gây tử vong trực tiếp |
| `concentrations`,`withEpi`,`plain` (118) | nồng độ thuốc tê | **1** | ngộ độc thuốc tê là một quy trình cấp cứu của chính ứng dụng |
| `timeToDeath` (30) | thời gian tới tử vong | **1** | quy trình cấp cứu |

---

## 3. Giao diện

```python
# tools/so_phu_bang_chung.py

class MucPhu(str, Enum):
    KHONG_CO        = "không có gì chống lưng"
    CHI_CO_NGUON    = "chỉ có nguồn cấp tệp"      # xuất xứ cấp TỆP, độ phân giải thô
    CO_CHUOI_DAY_DU = "có chuỗi bằng chứng đầy đủ"

class HoSoBangChung(BaseModel):
    duong_dan:  str          # 'drugs.json#propofol.max' — định vị cấp DÒNG
    khoa:       str          # khoá JSON, để truy lại quy tắc xếp hạng
    khang_dinh: str
    muc_rui_ro: int          # 1 | 2 | 3

    nguon_khai:      str | None                 # từ tệp khai xuất xứ
    doi_chieu_nguoc: TrangThai = KHONG_KIEM_DUOC # V2 điền
    bo_ba:           list[tuple[str,str,str]] = []   # V3 điền
    bac_chung_cu:    int | None = None
    do_manh:         str | None = None

    @property
    def muc_phu(self) -> MucPhu:
        """SUY RA, không bao giờ gán tay."""

def quet_khang_dinh(thu_muc_du_lieu: Path) -> list[HoSoBangChung]
def bao_cao_phu(ds: list[HoSoBangChung]) -> str
```

### Ràng buộc bất biến

| # | Ràng buộc | Vì sao |
|---|---|---|
| R1 | `muc_phu` **suy ra** từ các trường, không có setter | trường tự khai độ tin cậy là chế độ hỏng đã gặp ở đợt kiểm toán trước |
| R2 | `CO_CHUOI_DAY_DU` đòi **cả** `doi_chieu_nguoc == DAT` **và** `bo_ba` không rỗng **và** `bac_chung_cu` khác `None` | thiếu một mắt là chưa đầy đủ |
| R3 | `duong_dan` **duy nhất** trong toàn bộ kết quả | trùng đường dẫn thì không gắn được bằng chứng vào đâu |
| R4 | Chỉ **đọc** dữ liệu AnesthOS, tuyệt đối không ghi | repo khác, quyết định khác |
| R5 | Không gọi mạng | V1 phải chạy được khi mất mạng |

### Tái dùng, không viết lại

| Có sẵn | Ở đâu | Dùng để |
|---|---|---|
| `tach_trich_dan()` | `tools/mo_hat_giong.py` | bóc chuỗi trích dẫn ghép nhiều nguồn bằng dấu chấm phẩy |

---

## 4. Tiêu chuẩn nghiệm thu — dạng lệnh, số phải khớp chính xác

```bash
python3 tools/so_phu_bang_chung.py --du-lieu <AnesthOS>/src/domain/data/
```

| # | Phải ra đúng | Lệch thì |
|---|---|---|
| N1 | Tổng lá: **20.279** | quy tắc duyệt sai → **dừng** |
| N2 | Nhãn/định danh/trình bày: **3.862** | tập khoá nhãn sai → **dừng** |
| N3 | Mang hệ quả lâm sàng: **16.417** | → **dừng** |
| N4 | Ưu tiên 1: **2.271** · Ưu tiên 2: **4.908** · Ưu tiên 3: **9.238** | bảng xếp hạng sai → **dừng** |
| N5 | **0** khẳng định ở mức `CO_CHUOI_DAY_DU` | **cổng chống tự khai** — chưa có V2/V3 thì không khẳng định nào được phép có chuỗi đầy đủ |
| N6 | `3.862 + 2.271 + 4.908 + 9.238 == 20.279` | phép cộng không khớp = có lá bị đếm hai lần hoặc rơi mất |

**N5 là cổng quan trọng nhất.** Ra khác 0 nghĩa là bộ tính mức phủ đang tự khai —
đúng chế độ hỏng cả hệ này dựng lên để chặn.

### Vì sao KHÔNG kèm đoạn mã đã dùng để ra bốn con số này

Bốn con số ở N1–N4 do Claude tính khi soạn đặc tả, bằng một đoạn mã dùng một lần.
Đoạn mã đó **cố ý không được đưa vào repo**.

Lý do giống hệt lý do AG-2 phải viết kiểm thử trước khi có mã cài đặt:

| Nếu đưa mã của Claude cho AG-1 | Nếu không đưa |
|---|---|
| AG-1 chạy lại đúng đoạn mã đó → **luôn khớp** | AG-1 tự cài đặt từ quy tắc §2 |
| Khớp nhau **không chứng minh được gì** | Khớp nhau = **hai lần đọc độc lập cùng ra một kết quả** |
| Lỗi trong cách đọc dữ liệu của Claude sẽ **nhân bản sang** AG-1 | Lỗi của Claude sẽ **lộ ra** thành bất đồng |

**Nếu số của AG-1 lệch với N1–N4:** đó là **bất đồng thật, phải phân xử**, không
phải lỗi của AG-1. Ghi lại cả hai con số, chỉ ra khoá nào đếm khác, rồi chuyển
Gun quyết. Tuyệt đối **không** chỉnh mã cho khớp con số của Claude — quy tắc §2
mới là nguồn chân lý, bốn con số chỉ là hệ quả của nó.

Bản thân bốn con số này đã sai một lần: bản kế hoạch được duyệt ghi 20.416 /
16.562 / 2.241, sai vì đếm cả nội dung tệp khai xuất xứ (137 lá), xếp nhầm ba
khoá trình bày, và **bỏ sót `timeToDeath` khỏi ưu tiên 1**. Chúng là số đo, không
phải chân lý.

### Ba lớp rào cản áp cho V1

| Lớp | Nội dung | Ai viết |
|---|---|---|
| 1 · Đơn vị | quy tắc duyệt (§2.1), tập khoá (§2.3), ràng buộc R1–R5 — dữ liệu dựng nhỏ | AG-2 |
| 2 · Đối chứng dữ liệu thật | chạy trên dữ liệu AnesthOS thật, khớp N1–N6 | AG-2 |
| 3 · Kiểm chéo nguồn | **không áp dụng cho V1** — V1 chưa chạm nguồn nào | — |

Lớp 3 để trống ở đây là **đúng**, không phải thiếu sót. Ghi rõ thay vì bỏ lửng.

---

## 5. Phân quyền — không ai chấm bài của chính mình

| Quyền | Ai | Được sửa | Cấm |
|---|---|---|---|
| Đặc tả | Claude | `docs/DAC_TA_*.md` | **không viết mã, không tự chạy nghiệm thu** |
| Viết kiểm thử | AG-2 | `tests/**` | `tools/**`; **không đọc mã của AG-1** |
| Viết mã | AG-1 | `tools/**` | `tests/**` |
| Chạy nghiệm thu | AG-3 | không sửa gì | mọi thay đổi mã |
| Cổng cuối | Gun | — | — |

### Thứ tự bắt buộc

| Bước | Ai | Kết quả mong đợi |
|---|---|---|
| 1 | **AG-2** | kiểm thử **ĐỎ** (chưa có mã) — **chốt của cả bộ khung** |
| 2 | AG-1 | cài đặt tới khi xanh, **không sửa kiểm thử** |
| 3 | AG-3 | chạy N1–N6, báo số |
| 4 | Gun | duyệt |

Bước 1 là chốt: kiểm thử viết **trước khi tồn tại mã cài đặt** thì không thể chỉ
mô tả lại mã đó.

**Luật xử bất đồng:** AG-1 thấy kiểm thử sai → **không sửa**, ghi bất đồng rồi
**dừng**. Đây là chỗ **duy nhất** được phép dừng giữa chừng.

| Cổng kiểm bằng máy | Lệnh | Chặn |
|---|---|---|
| Phân quyền tệp | `git diff --name-only` sau mỗi bước | vai này lấn tệp vai kia |
| Chất lượng kiểm thử | `scripts/gate_m6.sh` | `assert True`, `skip`, `xfail` |
| Toàn vẹn | `python3 -m pytest` | số kiểm thử chỉ **tăng** (mốc 568) |

Sáu luật cứng L1–L6 ở `docs/KE_HOACH_ANTIGRAVITY.md` §1 áp dụng nguyên vẹn.

---

## 6. Chưa đặc tả — chờ cổng

| Hạng mục | Điều kiện mở |
|---|---|
| V2 · đối chiếu ngược | sau khi V1 qua N1–N6 |
| V3 · chuỗi bằng chứng | sau khi V2 đạt trên mẫu nhỏ |
| V4 · dò lỗi thời | **khoá cứng** cho tới khi V3 đạt — nguyên tắc ĐÚNG trước MỚI |

Viết đặc tả cho một tầng mà cổng phía trước có thể bác bỏ là làm việc thừa. Ba
tầng sau chỉ chốt giao diện ở kế hoạch, chưa chốt đặc tả.
