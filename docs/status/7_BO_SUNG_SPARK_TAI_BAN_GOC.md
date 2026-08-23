# 7. Bổ sung cho Spark — tải hộ bản gốc

> **Cập nhật**: 2026-08-23 · nhánh `claude/sr-agent-architecture-audit-scn4v6`
> **Đây là đoạn BỔ SUNG**, dán thêm vào vòng lặp PubMed đã có (tài liệu 6).
> Không thay thế gì cả — chỉ thêm một bước giữa bước 3 và bước 4.

---

# BỔ SUNG: BƯỚC 3B — TẢI HỘ BẢN GỐC

Sau khi đã tải lên phiếu JSON ở bước 3, làm thêm việc này.

## Vì sao giao thêm việc này cho bạn

Hệ thống kiểm định hiện **không tự với tới PubMed được** — IP của nó bị NCBI
chặn. Bạn thì gọi được. Nên bạn tải hộ.

Nhưng vai trò của bạn **không đổi**: bạn chỉ **vận chuyển**, không diễn giải.
Bạn lấy byte từ NCBI và giao lại y nguyên. Việc đọc hiểu vẫn là của hệ thống.

## Việc cụ thể

Gọi PubMed efetch cho **đúng những mã đã ghi trong `ids` của phiếu** — không
thêm, không bớt:

```
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=<CÁC-MÃ-CÁCH-NHAU-BẰNG-DẤU-PHẨY>&retmode=xml&tool=sr-agent&email=tranngochoangthanh30@gmail.com
```

Ví dụ, nếu `ids` là bốn mã `40448969`, `34108229`, `26095867`, `36462533`:

```
https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=40448969,34108229,26095867,36462533&retmode=xml&tool=sr-agent&email=tranngochoangthanh30@gmail.com
```

Lấy **toàn bộ thân phản hồi** và tải lên thư mục `hang_doi`
(ID: `1DIXlmzWeGJ065jryJyNnGOOiqP2tyQ32`):

- **Tên tệp**: `<mã-phiếu>_efetch.xml`
  → ví dụ `2026-08-23_chong-dong_pubmed_efetch.xml`
- **Kiểu nội dung**: `application/xml`
- **TẢI LÊN tệp thật.** Không tạo Google Doc — Google Docs không đồng bộ nội
  dung xuống máy tính, nên tệp sẽ đọc ra rỗng.

## ⚠️ QUY TẮC QUAN TRỌNG NHẤT CỦA CẢ ĐOẠN NÀY

**Giao lại NGUYÊN VĂN, từng byte một.**

- **Không** định dạng lại cho đẹp, không thụt lề lại, không xuống dòng lại.
- **Không** cắt bớt phần nào, kể cả phần trông có vẻ thừa.
- **Không** dịch, không tóm tắt, không thêm ghi chú của bạn vào tệp.
- **Không** sắp xếp lại thứ tự các bản ghi.

Lý do: hệ thống sẽ **đối chiếu từng trường** giữa bản bạn nộp và bản chính thống
khi nào nó tự tải được. Mọi khác biệt đều bị ghi nhận. Một lần "sửa cho gọn"
sẽ hiện ra thành sai lệch dữ liệu.

## 🚨 NẾU KHÔNG TẢI LÊN ĐƯỢC XML NGUYÊN VĂN

**Hãy nói thẳng là không làm được.**

**TUYỆT ĐỐI KHÔNG dựng lại XML từ những gì bạn đọc được.** Một bản dựng lại
trông y hệt bản thật nhưng là bịa — và nó nguy hiểm hơn hẳn việc không có gì,
vì không ai phân biệt được bằng mắt.

Không nộp tệp nào cả vẫn tốt hơn nộp một tệp trông đúng mà sai.

## Tự kiểm trước khi báo cáo

Ghi lại **hai con số** và so chúng:

| Con số | Nghĩa |
|---|---|
| Dung lượng phản hồi NCBI trả về | bao nhiêu byte bạn nhận được |
| Dung lượng tệp đã tải lên | bao nhiêu byte bạn giao đi |

**Hai số này phải bằng nhau.** Lệch nghĩa là có gì đó đã bị đổi trên đường đi —
báo lại con số lệch, đừng giấu.

# BÁO CÁO — thêm hai dòng vào bản cũ

```
Đã tải lên : <tên tệp .json>
Bản gốc    : <tên tệp .xml> · nhận <n> byte · nộp <m> byte
Truy vấn   : <chuỗi nguyên văn>
Số liệu    : tìm <n> · sàng <m> · giữ <k> · loại <j>
```

Nếu bước 3B thất bại, ghi đúng một dòng:

```
Bản gốc    : KHÔNG TẢI ĐƯỢC — <lý do cụ thể>
```

---

## Ghi chú cho Gun (KHÔNG thuộc prompt)

**Bản ghi thu theo đường này mang nguồn riêng `pubmed-qua-spark`, hạng uy tín 3**
thay vì hạng 1 của bản SR-Agent tự tải. Hai hệ quả xảy ra tự động:

- Khi nào SR-Agent tự tải được, bản hạng 1 sẽ **thay thế** bản qua trung gian,
  giữ vết trong `alternate_uids`.
- Rubric chấm nó thấp hơn.

**Mục đích thật của bước này không phải là lấy dữ liệu** — mà là tạo ra phép đo.
Khi có `NCBI_API_KEY`, chạy `so_khop_ban_chinh_thong()` sẽ cho **tỷ lệ sai lệch
thật** của Spark khi làm nhiệm vụ vận chuyển, thay vì linh cảm.

Đã kiểm chứng bằng mô phỏng — bắt được cả bốn kiểu bóp méo:

| Kiểu | Bị bắt bằng |
|---|---|
| Đổi một từ trong tiêu đề | so tiêu đề |
| Đảo `noninferior` → `superior` | so tóm tắt |
| Nâng RCT thành phân tích gộp | so bậc chứng cứ |
| Bịa hẳn mã bài | không tồn tại ở nguồn |
