# SR-Agent đối chiếu quy trình EBM 5 bước — và quy trình lặp lại được

> Đối chiếu thiết kế hiện tại với quy trình thật của lâm sàng viên (5As × tam giác
> giá trị), tìm chỗ hụt, rồi dựng quy trình dùng lại được cho **mọi vấn đề mới**.
> Mốc: 568 test xanh · nhánh `claude/sr-agent-architecture-audit-scn4v6`.

---

## 1. Bản đồ phủ — SR-Agent đang ở đâu trên 5As

| Bước | SR-Agent có gì | Mức phủ |
|---|---|---|
| **1 · Ask** | `dat_cau_hoi.py`: PICO, 5 dạng câu hỏi, mù kết cục cài vào cấu trúc, 17 câu tiền mê | **~70%** — chỉ xử lý Foreground |
| **2 · Acquire** | `europepmc.py` + `quet_that.py`: quét cả kho, cursor, 13.173 bản ghi | **~50%** — nhưng **đi ngược tháp** |
| **3 · Appraise** | `evidence_level` suy từ `pubTypeList` | **~10%** — 1 trục yếu trên 3 trục |
| **4 · Apply** | AnesthOS (chưa nối vào SR-Agent) | **0%** |
| **5 · Assess** | *không có gì* | **0%** |

Ba chỗ hụt lớn nhất không nằm ở nơi tôi tưởng. Chi tiết ở §2.

---

## 2. Ba phát hiện

### 2.1 · SR-Agent đang tìm NGƯỢC tháp bằng chứng

Lâm sàng viên quét **từ đỉnh xuống** và **dừng ngay khi có câu trả lời**:

```
Systems → Summaries → Synopses → Syntheses → Studies
   ↑ dừng ở đây nếu đủ                          ↑ SR-Agent bắt đầu ở đây
```

SR-Agent quét **đáy tháp** — 13.173 bản ghi thô — cho **mọi** câu hỏi. Với phần
lớn trong 17 câu tiền mê, đỉnh tháp **đã có câu trả lời**: ASA có hướng dẫn nhịn
ăn, ESC/ACC có hướng dẫn tim mạch chu phẫu, ASRA có hướng dẫn kháng đông trục
thần kinh. Dựng tổng quan hệ thống mới cho từng câu là **làm lại việc đã có**.

**Đảo lại thành bước phân loại đứng trước:**

| Đỉnh tháp nói gì | Làm gì |
|---|---|
| trả lời đủ · không mâu thuẫn · còn hạn | **dừng** — ghi nguồn, ghi phiên bản, xong |
| im lặng · mâu thuẫn nhau · quá hạn | **mới** quét đáy (kho đầy đủ) |

Đây là chỗ 80/20 lớn nhất của cả hệ: phần lớn điểm quyết định **không cần** tổng
quan hệ thống mới, chỉ cần câu trả lời sẵn có được **truy nguồn và gắn phiên bản**.

**Ranh giới bắt buộc — đỉnh tháp là LỚP DẪN ĐƯỜNG, không phải nguồn được trích:**

UpToDate/DynaMed cho biết **hướng dẫn nào, thử nghiệm nào** đáng kể.
AnesthOS trích **chính hướng dẫn/thử nghiệm đó**, không trích UpToDate.

Ba cái lợi cùng lúc: xuất xứ kiểm chứng được · không vướng bản quyền · SR-Agent
vẫn thêm giá trị thay vì chép lại. Cùng một ranh giới đã ghi trong
`tools/nguon_tong_hop.py` — *đề thi cho bộ sàng, không làm bộ sàng*.

### 2.2 · Tự động hoá phải nhắm vào bước NGƯỜI LÀM YẾU, không phải bước người làm giỏi

| Bước | Người làm | Máy nên |
|---|---|---|
| Ask | khá — nhưng hay hỏi mơ hồ | hỗ trợ cấu trúc hoá |
| Acquire | **yếu** — vài chục giây/câu, không quét hết được | **thay thế** ✅ đang làm |
| Appraise | **giỏi** — chuyên môn lâm sàng | chuẩn bị số liệu, **không thay** |
| Apply | **giỏi, không thể thay** — tam giác giá trị cần bệnh nhân | chỉ cấp thông tin (LHH, NNT) |
| Assess | **yếu nhất — gần như không ai làm** | **thay thế** ❌ **chưa làm gì** |

Bước 5 là chỗ hệ luôn-bật có **lợi thế tuyệt đối** so với người: không ai rà lại
khuyến cáo cũ khi có thử nghiệm mới. SR-Agent đang đầu tư đúng vào Acquire nhưng
**bỏ trống hoàn toàn** chỗ nó có lợi thế lớn nhất.

**Và hạ tầng cho nó ĐÃ CÓ SẴN**, dựng cho việc khác: `van_tay_kho()` (vân tay
kho) + `so_quyet_dinh.jsonl` (sổ nối thêm). Chúng sinh ra để phục vụ PRISMA,
nhưng đó **đúng là** thứ một bộ dò lỗi thời cần: kho đổi vân tay → khuyến cáo
dựa trên kho đó bị đánh dấu cần rà lại. Rẻ, và chưa ai nối vào.

### 2.3 · Chưa phân biệt câu hỏi Nền tảng và câu hỏi Đặc hiệu → làm việc thừa

`dat_cau_hoi.py` coi **mọi thứ** là Foreground và ép vào PICO. Nhưng lược đồ đầu
ra của AnesthOS có rất nhiều trường thuần **Background**:

| Trường | Loại | Cần gì |
|---|---|---|
| thành phần thang STOP-BANG | Background | một nguồn chuẩn + phiên bản |
| định nghĩa phân độ ASA | Background | một nguồn chuẩn + phiên bản |
| STOP-BANG tầm soát có cải thiện kết cục không | **Foreground** | PICO đầy đủ |
| ngưỡng Hb truyền máu | **Foreground** | PICO đầy đủ |

Chạy đường ống PICO cho câu Background là **tốn công vô ích** — và tệ hơn, nó
tạo ra một kho 5.000 bài cho một câu hỏi chỉ cần tra một dòng trong hướng dẫn.

Phân loại này **rẻ** và phải đứng **trước** mọi thứ khác.

---

## 3. Hai lỗi cụ thể trong mã hiện có

### 3.1 · `EF2` trong `tools/criteria/default.json` vi phạm chính nguyên tắc mù kết cục

```json
"EF2": { "label_vi": "Không báo cáo outcome quan tâm" }
```

Loại một nghiên cứu **vì nó không báo cáo kết cục ta quan tâm** chính là sai lệch
báo cáo chọn lọc — đúng thứ nguyên tắc mù kết cục sinh ra để chặn. Nghiên cứu
thoả P, I, C phải được **nhận vào** rồi **gắn nhãn "không có dữ liệu kết cục"**,
không phải bị loại.

Mù kết cục đã được cài vào cấu trúc ở `KhungTuyenChon.thanh_truy_van()` (truy vấn
không bao giờ chạm `ket_cuc`), nhưng bộ mã loại trừ ở tầng sàng **thì chưa** —
hai tầng đang nói ngược nhau.

`EF1`, `EF4` cũng là di sản ngành máy tính (*metrics*, *salami slicing*), không
hợp lâm sàng.

### 3.2 · `tools/evidence_extract.py` là di sản arXiv, không dùng được cho lâm sàng

```python
has_code_repo · dataset_spec · baselines
```

Đây là trường bóc tách cho bài học máy. Nó **trông như** đã phủ bước Appraise
nhưng thực tế phủ 0%. Đừng đếm nó vào năng lực hiện có.

---

## 4. Quy trình lặp lại được cho MỘT vấn đề bất kỳ

```
VẤN ĐỀ MỚI  ("quản lý kháng đông", "khám tiền mê", ...)
  │
  ├─[0] PHÂN RÃ  vấn đề → điểm quyết định            ✅ tu_luoc_do_dau_ra()
  │        neo vào LƯỢC ĐỒ ĐẦU RA, không neo vào chủ đề
  │
  ├─[1] ASK     mỗi điểm quyết định: Nền tảng hay Đặc hiệu?   ❌ THIẾU
  │        Nền tảng  → nguồn chuẩn + phiên bản → xong
  │        Đặc hiệu  → PICO theo 1 trong 5 dạng   ✅ dat_cau_hoi.py
  │
  ├─[2] ACQUIRE quét TỪ ĐỈNH THÁP XUỐNG              ⚠ ĐANG NGƯỢC
  │        đỉnh đủ → dừng, ghi nguồn gốc
  │        đỉnh hụt → quét đáy                       ✅ quet_that.py
  │        đo độ nhạy bằng chuẩn vàng ngoài          ✅ nguon_tong_hop.py
  │
  ├─[3] APPRAISE ba trục                             ⚠ mới có ~1/3 của 1 trục
  │        Giá trị      thiết kế + kiểm soát sai lệch
  │        Tác động     ARR / NNT / cỡ tác động
  │        Áp dụng được P thật của bài  vs  P mục tiêu
  │
  ├─[4] APPLY   AnesthOS xuất khuyến cáo             ❌ chưa nối
  │        kèm ĐỘ MẠNH + NGUỒN + điều kiện áp dụng
  │
  └─[5] ASSESS  vân tay kho + lịch rà lại            ❌ TRỐNG
           kho đổi → khuyến cáo dựa trên nó bị gắn cờ
           └──────────── vòng lại [2] ────────────┘
```

Bước [5] là thứ biến một lần chạy thành một **quy trình**. Thiếu nó thì mỗi vấn
đề là một dự án riêng lẻ hết hạn dần, không phải một hệ vận hành.

---

## 5. Thứ tự nên làm — theo 80/20

| # | Việc | Vì sao trước | Giá |
|---|---|---|---|
| 1 | **[5] Bộ dò lỗi thời** | chỗ máy có lợi thế tuyệt đối; hạ tầng đã có sẵn | **rẻ** |
| 2 | **[2] Phân loại đỉnh tháp trước** | cắt nhiều việc thừa nhất | vừa |
| 3 | **[1] Router Nền tảng/Đặc hiệu** | chặn đường ống PICO chạy cho câu không cần | **rẻ** |
| 4 | **[3] Trục Tác động (ARR/NNT)** | AnesthOS cần để nói độ mạnh khuyến cáo | vừa |
| 5 | Bắt PICO thật của bài đã nhận | phát hiện quần thể trôi khỏi quần thể mục tiêu | vừa |
| — | ~~Tổng quan hệ thống de-novo cho cả 17 câu~~ | **cái bẫy** — làm lại việc đỉnh tháp đã làm | rất đắt |

Sửa `EF2` đi kèm việc #3 (cùng chạm tầng sàng).

---

## 6. Ba cấp PICO — hiện chỉ có cấp 1

| Cấp | Là gì | SR-Agent |
|---|---|---|
| Review PICO | ranh giới nhận/loại | ✅ `KhungTuyenChon` |
| Synthesis PICO | gom nhóm để so sánh/phân tích gộp | ❌ |
| Included Study PICO | PICO **thật** của bài đã nhận | ❌ |

Cấp 3 đáng làm sớm hơn cấp 2, vì nó **đo được**: so P-thật của kho với P-mục tiêu
sẽ lộ ra quần thể đã trôi. Đó đúng loại hỏng im lặng cả hệ này dựng lên để bắt —
truy vấn vẫn chạy, kho vẫn đầy, chỉ là đầy sai người bệnh.

---

## 7. Dùng lại ngoài y học

5As nói bằng từ vựng y khoa nhưng **cấu trúc thì phổ quát**:

| Bước | Dạng tổng quát | Y | Ngoài y |
|---|---|---|---|
| Ask | điểm quyết định → câu hỏi trả lời được | PICO | PICO vẫn dùng được nếu có P/I/C/O |
| Acquire | tháp nguồn, quét từ đỉnh | UpToDate → PubMed | tiêu chuẩn ngành → survey → bài gốc |
| Appraise | giá trị / tác động / áp dụng được | RCT, NNT | thiết kế, cỡ tác động, bối cảnh |
| Apply | xuất khuyến cáo kèm điều kiện | tam giác giá trị | ràng buộc của người dùng |
| Assess | rà lại theo lịch | kiểm toán lâm sàng | **giống hệt** |

Chỉ **hai thứ** là cắm-thay-được theo lĩnh vực: **sổ đăng ký nguồn** (tháp) và
**thang thẩm định**. Phần còn lại của vòng lặp không đổi. Đó là điều kiện để
SR-Agent là engine dùng lại được chứ không phải công cụ riêng của AnesthOS.

---

## 8. Chỗ máy KHÔNG được lấn

Tam giác giá trị: bằng chứng ∩ chuyên môn lâm sàng ∩ giá trị người bệnh.

SR-Agent chỉ sản xuất **đỉnh thứ nhất**. Bước 4 (Apply) đòi hỏi ra quyết định
chia sẻ với người bệnh — **không tự động hoá được, và không nên**.

Nên đầu ra đúng của AnesthOS không phải "hãy làm X" mà là:

> X, độ mạnh Y, dựa trên Z, áp dụng khi điều kiện W — **bác sĩ và người bệnh quyết**.

Thiết kế đầu ra mà bỏ mất "điều kiện W" là biến một công cụ hỗ trợ quyết định
thành một công cụ **thay thế** quyết định. Đó là hỏng lâm sàng, không phải hỏng kỹ thuật.
