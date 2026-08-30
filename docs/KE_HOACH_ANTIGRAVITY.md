# Kế hoạch giao cho Antigravity — SR-Agent

> **Người viết**: Claude (thiết kế + harness) · **Người thực thi**: Antigravity · **Cổng**: Gun
> **Nhánh**: `claude/sr-agent-architecture-audit-scn4v6` · **Cập nhật**: 2026-08-24
> **Trạng thái khởi điểm**: 550 test xanh, Europe PMC chạy thật từ máy Gun.

---

## 0. Vì sao bản kế hoạch này viết chặt như vậy

Antigravity nhanh và có quyền vào GitHub lẫn terminal. Đúng thứ cần. Nhưng
**tốc độ cao trên một hệ đo hỏng chỉ là đi nhanh hơn về phía sai**.

Cả quá trình dựng SR-Agent, **mọi lỗi đáng giá đều do PHÉP ĐO bắt, không do ai
rà tay**: `MESH:` đúng cú pháp mà không lôi được bài mồi · hai chỗ dựng truy vấn
cãi nhau 0/4 vs 4/4 · `hitCount` bị trang sau ghi đè · nháy kép lồng · mệnh đề
đối chiếu lọc theo cách diễn đạt · hai mệnh đề trùng trục làm kho phình 27 lần.

Không cái nào lộ ra khi đọc mã. Tất cả lộ ra khi chạy và ĐO.

Nên bản kế hoạch này không mô tả "làm gì" mà mô tả **"làm xong thì đo bằng cách
nào"**. Mỗi nhiệm vụ có tiêu chí nghiệm thu CHẠY ĐƯỢC, không phải mô tả bằng lời.

---

## 1. LUẬT CỨNG — vi phạm là hỏng cả hệ, không phải lỗi nhỏ

### L1. KHÔNG làm test xanh bằng cách nới test

Đây là chế độ hỏng nguy hiểm nhất của một executor nhanh. Test đỏ nghĩa là **mã
sai HOẶC kỳ vọng sai** — phải xác định là cái nào rồi mới sửa.

- Sửa mã cho đúng kỳ vọng → **được**
- Đổi kỳ vọng vì hành vi đã được CỐ Ý đổi, kèm giải thích trong commit → **được**
- Nới `assert`, thêm `skip`, `xfail`, hoặc xoá test để cho xanh → **CẤM**

`scripts/gate_m6.sh` đã có chốt bắt `assert True` / `skip` / `xfail`.

### L2. KHÔNG chạm vùng cấm zero-touch

`sr_agent/ingest/` · `sr_agent/pipeline.py` · `pyproject.toml`

Ngoại lệ ĐÃ KHAI và chỉ hai tệp: `sr_agent/config.py`, `sr_agent/models/schemas.py`
(mở sổ đăng ký nguồn). Không mở thêm ngoại lệ nào nữa.

**Không thêm phụ thuộc mới.** Mọi thứ phải chạy bằng `httpx` + `pydantic` +
thư viện chuẩn. Thêm gói là chạm `pyproject.toml`.

### L3. Mọi phép đo mới phải tự biết khi nào nó VÔ HIỆU

Bài học trả giá thật: phép so "tổng quan có lọt vào kho không" thành vô nghĩa
sau khi gỡ mệnh đề đối chiếu — vì lúc đó truy vấn mở đầu là tập con chặt, độ phủ
luôn 100%. Báo `✓` ở đó là **báo một thành tích không tồn tại**.

Mọi phép đo mới phải trả về được ba trạng thái, không phải hai:

```
ĐẠT · TRƯỢT · VÔ HIỆU (không đủ căn cứ để kết luận)
```

Trạng thái thứ ba là bắt buộc. Thiếu nó thì phép đo sẽ có ngày im lặng báo đạt.

### L4. Lỗi mạng tính là TRƯỢT, không phải bỏ qua

Lỗi mạng lặng lẽ thành "đạt" đúng là kiểu hỏng cả hệ này dựng lên để chặn.

### L5. KHÔNG bịa dữ liệu để lấp chỗ trống

Không có mã bài thì để trống và nói rõ. Bịa một PMID trông hợp lý là phá luôn
giá trị của phép đo mà nó phục vụ.

### L6. Mỗi commit phải chạy `python3 -m pytest` xanh trước khi đẩy

Số test chỉ được TĂNG hoặc giữ nguyên, không được giảm.

**NGOẠI LỆ DUY NHẤT — bước 1 của AG-2 (viết kiểm thử trước khi có mã).**

L6 được viết khi giả định MỘT tác nhân làm cả viết mã lẫn viết kiểm thử. Dưới
mô hình tách vai (`docs/DAC_TA_V1_SO_PHU.md` §5), bước đầu tiên **bắt buộc phải
đỏ**: kiểm thử viết ra trước khi tồn tại mã cài đặt thì không thể chỉ mô tả lại
mã đó — đó chính là rào cản, không phải sự cố.

Ngoại lệ này có ba điều kiện, thiếu một là vi phạm L6 thật:

| # | Điều kiện |
|---|---|
| 1 | Chỉ commit của **AG-2**, và chỉ chạm `tests/**` |
| 2 | Thông điệp commit ghi **chính xác số kiểm thử đỏ** và lý do |
| 3 | Kiểm thử đỏ vì **thiếu mã**, không phải vì `skip`/`xfail`/`assert True` |

Commit kế tiếp (AG-1 cài đặt) phải đưa toàn bộ về xanh. Đỏ kéo dài quá một
commit là hỏng thật, không còn là ngoại lệ.

---

## 2. Bối cảnh kỹ thuật — đọc trước khi làm

| Việc | Trạng thái |
|---|---|
| Nguồn Europe PMC, quét cả kho bằng cursor | ✅ `tools/sources/europepmc.py` |
| Từ vấn đề → điểm quyết định → truy vấn | ✅ `tools/dat_cau_hoi.py` |
| 17 câu hỏi tiền mê | ✅ `tools/profiles/tien_me_cau_hoi.json` |
| Chạy nhiều câu một lệnh | ✅ `tools/chay_cau_hoi.py` |
| Kho bất biến + sổ quyết định nối thêm | ✅ `tools/so_quyet_dinh.py` |
| **Đo độ nhạy thật** | ❌ **chưa có — nhiệm vụ T1-T2** |
| Sàng lọc | ❌ chưa có — T4 |
| Sơ đồ PRISMA | ❌ chưa — số liệu đã ghi sẵn trong sổ |

**Ba giới hạn hạ tầng, không sửa bằng mã được:**

1. `eutils.ncbi.nlm.nih.gov` chặn cả máy Gun lẫn Spark → dùng Europe PMC.
2. Sandbox của Claude chặn mọi tên miền ngoài danh sách trắng → Claude không tự
   gọi Europe PMC được. **Antigravity thì gọi được** — đó là lý do có bản này.
3. `pip install` trên macOS báo `externally-managed-environment` → bỏ qua,
   `httpx`/`pydantic` đã có sẵn.

---

## 3. NHIỆM VỤ — theo thứ tự, không nhảy cóc

### T0 · Chuẩn vàng từ nguồn tổng hợp ngoài — LÀM TRƯỚC T1

> Thêm sau khi Gun chỉ ra bộ skill UpToDate của anh. Nó vá đúng lỗ hổng mà T1
> chỉ vá được một nửa, nên T1 **không còn là việc số một**.

**Vì sao T1 chưa đủ:** T1 lấy danh mục tham khảo của tổng quan hệ thống *trong
kho* — mà bài tổng quan đó được tìm ra **bằng chính truy vấn đang bị kiểm**.
Chuẩn vàng nằm ở **hạ nguồn** của thứ nó kiểm. Truy vấn có điểm mù thì ta không
bao giờ gặp bài tổng quan sẽ phơi bày điểm mù đó → khép kín một phần.

UpToDate phá vòng đó: bài được tìm theo **tên chủ đề**, không qua truy vấn nào
của ta; biên tập viên dựng danh mục mà chưa từng thấy truy vấn của ta. Chuẩn
vàng nằm **hoàn toàn ở thượng nguồn**. Đây là bậc 0 trong `mo_hat_giong.py`.

**Đã dựng sẵn (offline, 17 test xanh):** `tools/nguon_tong_hop.py`
— bóc danh mục tham khảo, nối lại mục bị ngắt dòng, đối chiếu với kho, ba trạng thái.

**Việc của Antigravity** — chỉ phần cần mạng và cần máy Gun:

1. Lấy văn bản danh mục tham khảo từ bài UpToDate Gun đã lưu (PDF trên Gun SSD
   hoặc trang `/print` trong Chrome đã đăng nhập). **Chỉ lấy phần REFERENCES.**
2. `tach_danh_muc()` → mục nào có PMID/DOI thì dùng được ngay.
3. Mục **không** có định danh: tra qua Europe PMC bằng nhan đề dạng cụm từ.
   **Khắt khe hay bỏ, không đoán** — một mục khớp NHẦM tệ hơn một mục không tra
   được: không tra được thì lộ ra ở mẫu số, khớp nhầm thì âm thầm dịch cả tử số
   lẫn mẫu số. Không chắc → để `khong_tra_duoc`.
4. `doi_chieu_voi_kho()` → báo cáo.

**Nghiệm thu**:

1. Chạy được trên ≥1 chủ đề thật, in ra `bao_cao()`
2. Mục không tra được **không** bị tính là sót (đã có test khoá)
3. Dưới `TOI_THIEU_DE_KET_LUAN` mục tra được → **VÔ HIỆU**, độ phủ để trống
4. Báo **đích danh** mã bài bị sót
5. **Không commit** PDF, văn bản, hay khuyến cáo của UpToDate vào repo — chỉ mã bài

**⚠ CẤM TUYỆT ĐỐI — dùng UpToDate để SÀNG:**

Không được giữ bài vì UpToDate có trích, hay loại bài vì UpToDate không trích.
Đó là sàng theo kết luận của người khác: vi phạm nguyên tắc mù kết cục, nhập
luôn thiên lệch của UpToDate, và nếu đầu ra của SR-Agent = trích dẫn của
UpToDate thì **SR-Agent không thêm được gì**.

> UpToDate làm **đề thi** cho bộ sàng, không làm **bộ sàng**.

Dùng đúng: chạy bộ sàng của ta lên các bài UpToDate trích. Bộ sàng loại nhầm một
bài trong đó → cờ đỏ cho **bộ sàng**.

---

### T1 · Lấy danh mục tham khảo từ Europe PMC

**Vì sao vẫn cần dù đã có T0:** T0 phụ thuộc thuê bao UpToDate và máy Gun, và
chỉ phủ được lĩnh vực y. T1 chạy tự động hoàn toàn, phủ mọi chủ đề. Hai cái **bổ
sung nhau**: T0 mạnh hơn nhưng hẹp, T1 yếu hơn nhưng chạy ở đâu cũng được.

Danh mục tham khảo của một bài tổng quan hệ thống là tập bài mà chuyên gia trong
ngành đã chọn — **trỏ ra NGOÀI kho của ta, độc lập với truy vấn của ta**. Đó là
thứ duy nhất hiện có thể đo độ nhạy thật mà không tốn thời gian chuyên gia.

**Điểm cuối**:
```
https://www.ebi.ac.uk/europepmc/webservices/rest/{source}/{id}/references?format=json&pageSize=1000
```

**Việc**: viết `tools/sources/tham_khao.py`

- `lay_tham_khao(fetcher, source_id) -> list[str]` — trả danh sách mã bài được
  trích dẫn, chuẩn hoá về dạng `europepmc:MED:<id>`
- Bài không có danh mục tham khảo (Europe PMC không có dữ liệu) phải phân biệt
  rõ với bài **có danh mục nhưng rỗng** — hai chuyện khác nhau
- Có phân trang; đi hết, cùng lối `quet_toan_bo`

**Nghiệm thu** — viết `tests/test_tham_khao.py`, tất cả phải xanh:

1. Phân tích được phản hồi thật (dùng bản ghi BRIDGE `europepmc:MED:26095867`,
   lưu một mẫu JSON thật vào `tests/fixtures/` làm gốc)
2. Bài KHÔNG có dữ liệu tham khảo → trả về trạng thái riêng, KHÔNG phải danh
   sách rỗng
3. Đi hết nhiều trang
4. Cursor/trang lặp lại → dừng, không lặp vô hạn
5. Phản hồi không phải JSON → `LayoutParseError` kèm 200 ký tự đầu

---

### T2 · Đo độ nhạy bằng danh mục tham khảo

**Việc**: thêm vào `tools/do_nhay.py`

```
do_nhay_bang_tham_khao(fetcher, kho_ids, tong_quan_ids, so_bai=10) -> KetQuaNhay
```

Cách làm:
1. Lấy `so_bai` bài tổng quan có bậc chứng cứ cao nhất trong số đã gặt
2. Lấy danh mục tham khảo của từng bài
3. Gộp lại thành tập "bài mà ngành cho là quan trọng"
4. Đếm bao nhiêu trong tập đó nằm trong kho chính

**Đây mới là độ nhạy thật**, vì tập tham khảo được dựng độc lập với truy vấn.

**Nghiệm thu**:

1. Kho chứa hết tham khảo → độ nhạy 1.0
2. Kho sót một nửa → độ nhạy 0.5
3. **Không lấy được danh mục tham khảo nào → VÔ HIỆU, không phải đạt** (luật L3)
4. Lỗi mạng ở một bài → bài đó tính là sót, không bỏ qua (luật L4)
5. Báo cáo nêu ĐÍCH DANH mã bài bị sót, không chỉ nêu tỷ lệ — sót mà không biết
   sót cái gì thì không sửa được truy vấn

---

### T3 · Chạy lại 17 câu với phép đo thật

**Việc**: nối T2 vào `tools/chay_cau_hoi.py`, thay chỗ phép so đã vô hiệu.

Chạy:
```bash
python3 tools/chay_cau_hoi.py --uu-tien 1 --so-cau 6
python3 tools/chay_cau_hoi.py --uu-tien 2 --so-cau 7
python3 tools/chay_cau_hoi.py --uu-tien 3 --so-cau 4
```

**Nghiệm thu**: ghi báo cáo vào `docs/status/KET_QUA_17_CAU.md` gồm, cho từng câu:

| Cột | Nội dung |
|---|---|
| Độ nhạy tham khảo | tỷ lệ + **danh sách mã bị sót** |
| Kích thước kho | và có chạm trần không |
| Phân bố bậc chứng cứ | kèm số "chưa phân loại" |
| Trạng thái | ĐẠT / TRƯỢT / VÔ HIỆU |

**Với câu TRƯỢT: KHÔNG tự sửa truy vấn.** Ghi lại mã bài bị sót và dừng. Sửa
truy vấn là quyết định phương pháp luận — để Gun và Claude xem số liệu rồi quyết.

Lý do: sửa truy vấn cho đến khi phép đo xanh chính là cách làm hỏng phép đo.

---

### T4 · Tầng 0 sàng lọc — luật xác định, không phán đoán

**Việc**: viết `tools/sang_tang0.py`

Chỉ loại theo tiêu chí **máy kiểm được**, không cần đọc hiểu:

| Luật | Lý do loại |
|---|---|
| Không có tóm tắt | không sàng được bằng tiêu đề+tóm tắt |
| Ngoài khoảng năm đã khai | ngoài phạm vi thời gian |
| Nhãn `Comment` / `Editorial` / `Letter` đơn thuần | không phải báo cáo nghiên cứu |
| Trùng mã trong cùng kho | đã có bản khác |

Mỗi lần loại ghi một dòng vào sổ quyết định (`tools/so_quyet_dinh.py`) với
`nguoi_sang="may:tang0@v1"` và `ly_do` là **tên luật đã khớp**.

**Nghiệm thu**:

1. Chạy lại hai lần cho **kết quả y hệt** — tầng 0 phải xác định
2. Mỗi quyết định loại có `ly_do` ứng với đúng một luật
3. **Bài mồi (nếu đã có từ T2) KHÔNG được lọt vào danh sách loại** — tầng 0 loại
   nhầm bài nền tảng là hỏng nặng hơn không có tầng 0
4. Vân tay kho khớp — không sàng nhầm kho
5. Chạy trên kho thật, báo tỷ lệ loại được

---

### T5 · Vòng lặp hằng ngày

**Chỉ làm sau khi T1-T4 xong và xanh.** Tự động hoá một hệ chưa đo được là nhân
tốc độ cho một hướng chưa biết đúng sai.

**Việc**: `scripts/vong_lap_ngay.sh` + `launchd` plist trên máy Gun.

Mỗi ngày:
1. Quét lại các câu ưu tiên 1
2. Đo độ nhạy bằng tham khảo
3. So kho hôm nay với kho hôm qua qua **vân tay**
4. Nếu có bài mới → chạy tầng 0 → ghi sổ
5. Ghi báo cáo, mở PR nếu có thay đổi

**ĐIỀU KIỆN DỪNG — bắt buộc, vòng lặp phải tự dừng được:**

| Dừng khi | Vì sao |
|---|---|
| Độ nhạy tham khảo tụt so với hôm trước | truy vấn đang xấu đi |
| Kho co lại > 20% mà truy vấn không đổi | nguồn có vấn đề |
| Bất kỳ phép đo nào trả VÔ HIỆU | không có căn cứ để chạy tiếp |
| Test đỏ | mã hỏng |
| Lỗi mạng > 3 lần liên tiếp | nguồn chặn |

Khi dừng: **mở issue, không tự sửa, không chạy tiếp**.

---

## 4. Việc KHÔNG được làm

| Cấm | Vì sao |
|---|---|
| Sửa truy vấn cho tới khi phép đo xanh | Đó là cách làm hỏng phép đo |
| Thêm bài mồi thủ công để đạt độ nhạy | Bài mồi phải độc lập với truy vấn |
| Gộp nhiều câu hỏi vào một kho | Mỗi điểm quyết định một kho |
| Đưa kết cục hoặc thiết kế nghiên cứu vào truy vấn | Ba lần đã sửa, đừng thêm lần thứ tư |
| Commit tệp kho `.json` | 20 MB mỗi câu, đã có trong `.gitignore` |
| Đánh dấu ĐẠT khi phép đo vô hiệu | Luật L3 |

---

## 5. Thứ tự và điều kiện chuyển bước

```
T1 danh mục tham khảo   →  test xanh, phân tích được dữ liệu THẬT
      ↓
T2 đo độ nhạy thật      →  phân biệt được ĐẠT/TRƯỢT/VÔ HIỆU
      ↓
T3 chạy 17 câu          →  báo cáo có SỐ, câu trượt nêu đích danh mã sót
      ↓                     ⛔ DỪNG — Gun + Claude xem số rồi quyết sửa truy vấn
T4 tầng 0 sàng lọc      →  chạy hai lần ra y hệt, không loại nhầm bài mồi
      ↓
T5 vòng lặp hằng ngày   →  chỉ khi mọi thứ trên đã xanh
```

Chốt sau T3 là **cố ý**. Đó là chỗ cần phán đoán phương pháp luận, không phải
chỗ cần tốc độ.

---

## 6. Báo cáo lại

Mỗi nhiệm vụ xong, ghi vào PR:

```
Nhiệm vụ : T<n>
Test     : <trước> -> <sau>
Đo được  : <con số thật, không phải mô tả>
Vướng    : <chỗ không làm được, nói thẳng>
```

**Một lần thất bại báo rõ có ích hơn mười lần thành công được kể lại.** Đây là
câu đã dùng cho Spark và nó đúng nguyên văn ở đây.
