# Bàn giao phiên mới — có quyền đọc Gun SSD

> Dành cho phiên Claude được cấp quyền thư mục local (Gun SSD), tiếp nối nhiệm
> vụ **T0** trong `docs/KE_HOACH_ANTIGRAVITY.md`.
> Nhánh: `claude/sr-agent-architecture-audit-scn4v6` · Mốc: 568 test xanh.

---

## 1. Đọc trước, theo đúng thứ tự

| Tệp | Cho biết |
|---|---|
| `docs/KE_HOACH_ANTIGRAVITY.md` §0-1 | sáu luật cứng L1-L6 — **bắt buộc** |
| `docs/KE_HOACH_ANTIGRAVITY.md` §T0 | nhiệm vụ của phiên này, kèm nghiệm thu |
| `tools/nguon_tong_hop.py` (docstring đầu tệp) | vì sao phép đo chạy một chiều |
| `docs/SO_CO_CHE.md` | tám cơ chế, hỏng kiểu nào, xem ở đâu |

Đừng viết mã trước khi đọc xong bốn thứ trên. Mọi lỗi đáng giá của dự án này đều
do **phép đo** bắt, không do đọc mã — nên hiểu phép đo là điều kiện để không phá nó.

---

## 2. Bốn điều không được vi phạm

**a. UpToDate làm ĐỀ THI cho bộ sàng, KHÔNG làm bộ sàng.**
Cấm giữ bài vì UpToDate có trích, cấm loại bài vì UpToDate không trích. Đó là
sàng theo kết luận của người khác → vi phạm mù kết cục, nhập thiên lệch, và nếu
đầu ra của SR-Agent = trích dẫn UpToDate thì SR-Agent **không thêm được gì**.

**b. Phép đo này chạy MỘT CHIỀU.**
Kho sót bài nguồn ngoài trích → lỗ hổng **đã xác nhận**.
Kho chứa đủ → **không** chứng minh kho đã đủ (nguồn tam cấp chỉ trích bài biên
tập viên chọn). Trạng thái tốt nhất tên là `KHONG_PHAT_HIEN_LO_HONG`. **Không
được đổi thành `ĐẠT`** — có test khoá đúng tên gọi đó.

**c. Bản quyền.**
Chỉ đưa **mã bài** (PMID/DOI) vào repo. Không commit PDF, văn bản, khuyến cáo,
hay danh mục nguyên văn của UpToDate. Gun có thuê bao hợp lệ; điều đó cho phép
đọc, không cho phép tái phân phối.

**d. Không tự sửa truy vấn cho phép đo xanh.**
Câu nào trượt → ghi **đích danh** mã bài bị sót rồi **dừng**. Sửa truy vấn là
quyết định phương pháp luận, thuộc về Gun. Sửa cho tới khi đo xanh chính là cách
làm hỏng phép đo.

---

## 3. Kiểm tra môi trường trước khi làm

Ba câu hỏi, trả lời bằng lệnh chứ không bằng phỏng đoán:

```bash
# 1. Mạng tới Europe PMC có thông không? (sandbox trên web thì KHÔNG)
curl -s -o /dev/null -w '%{http_code}\n' \
  'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=EXT_ID:26095867&format=json'

# 2. Kho đã quét còn trên máy không? (kho KHÔNG commit vào repo)
ls -la kho_*.json 2>/dev/null || echo "chưa có kho — cần chạy tools/quet_that.py"

# 3. Có bài UpToDate nào trên SSD trùng với 17 câu hỏi tiền mê không?
find "<đường dẫn Gun SSD>" -name "*UPTODATE*.pdf" | head -40
```

Kết quả quyết định làm được tới đâu:

| `200` + có kho | làm trọn T0, tra được cả mục không có PMID |
| `200`, chưa có kho | chạy `tools/quet_that.py` trước |
| **không** `200` | vẫn làm được phần bóc + đối chiếu offline; mục thiếu PMID để `khong_tra_duoc`, **không đoán** |

---

## 4. Việc chính

1. **Chọn chủ đề.** Đối chiếu danh sách PDF UpToDate trên SSD với
   `tools/profiles/tien_me_cau_hoi.json` (17 câu). Ưu tiên **kháng đông chu phẫu**
   nếu có — đó là chủ đề duy nhất đã có 4 bài mồi xác minh độc lập
   (`MOI_CHONG_DONG` trong `tools/do_nhay.py`), nên nếu phép đo mới mâu thuẫn với
   phép cũ thì **mâu thuẫn đó tự nó là thông tin**. Không có thì chọn chủ đề trùng
   nhiều nhất và nói rõ đã chọn gì, vì sao.

2. **Bóc riêng phần REFERENCES** của bài đó. PDF bản in UpToDate dài; danh mục
   nằm ở cuối — đọc từ trang cuối ngược lên, đừng đọc cả bài.

3. **Chạy qua công cụ đã có** (đừng viết lại):
   ```python
   from tools.nguon_tong_hop import tach_danh_muc, doi_chieu_voi_kho, bao_cao
   muc = tach_danh_muc(van_ban_references)
   kq  = doi_chieu_voi_kho(muc, kho_ids, ten_chu_de="...")
   print(bao_cao(kq))
   ```

4. **Mục không có PMID/DOI**: nếu có mạng thì tra Europe PMC bằng nhan đề dạng
   cụm từ, **khắt khe hay bỏ**. Một mục khớp NHẦM tệ hơn một mục không tra được:
   không tra được thì lộ ra ở mẫu số; khớp nhầm thì âm thầm dịch cả tử số lẫn mẫu
   số mà không ai thấy. Không chắc → để `khong_tra_duoc`.

5. **Báo cáo**: `bao_cao()` + danh sách **đích danh** mã bài bị sót + tỷ lệ tra
   được. Ghi vào `docs/status/` và commit (chỉ mã bài).

---

## 5. Brainstorm tiếp — ba câu còn mở

Gun muốn phiên này **bàn tiếp**, không chỉ chạy. Ba chỗ đang thiếu thiết kế:

**a. Cây chủ đề → điểm quyết định (phép đo thứ hai, chưa có).**
Mục lục UpToDate cho một lĩnh vực chính là danh sách điểm quyết định đã được
chuyên gia thẩm định. 17 câu hỏi hiện tại bóc tay từ feature map của Gun. Đối
chiếu hai bên cho ra phép đo **khác loại**: không phải "sót bài nào" mà **"sót
câu hỏi nào"** — loại lỗi mà đo độ nhạy không bao giờ bắt được. Rẻ và đáng làm.

**b. Chiến lược tra ngược trích dẫn không có định danh.**
Bao nhiêu phần trăm danh mục UpToDate có sẵn PMID? Nếu thấp, phép đo mất lực và
cần cách tra khác. Đây là **số đo được**, hãy đo rồi mới bàn.

**c. Ngưỡng `TOI_THIEU_DE_KET_LUAN = 5` là tự khai, chưa có căn cứ.**
Nó chặn kiểu hỏng "tra được 2/150 rồi báo không phát hiện lỗ hổng". Nhưng 5 là
số tôi đặt ra, không phải số tìm ra. Có dữ liệu thật rồi thì bàn lại.

---

## 6. Xong thì trông như thế nào

- `bao_cao()` chạy được trên ≥1 chủ đề thật, in ra số thật
- mục không tra được **không** bị tính là sót
- dưới ngưỡng → **VÔ HIỆU**, độ phủ để trống, không phải `0%`
- `python3 -m pytest` xanh, số test **chỉ tăng**
- commit không chứa PDF/văn bản UpToDate
- có nhận định về ba câu ở §5
