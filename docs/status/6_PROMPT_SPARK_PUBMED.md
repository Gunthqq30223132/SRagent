# 6. Prompt Spark — vòng lặp PubMed (bản CHẠY THỬ)

> **Cập nhật**: 2026-08-23 · nhánh `claude/sr-agent-architecture-audit-scn4v6`
> **Đây là prompt để dán vào Spark.** Phần dưới đường kẻ chép nguyên văn.
> Vòng lặp arXiv cũ GIỮ NGUYÊN — đây là vòng lặp thứ hai, độc lập.
> Thư mục và file mẫu đã tạo sẵn trên Drive, Spark chỉ việc dùng.

---

# NHIỆM VỤ

Chạy **MỘT LẦN** để thử cơ chế. Chưa lập lịch hằng ngày.

Tìm y văn trên **PubMed** về câu hỏi:

> **Tiếp cận quản lý chống đông trước, trong và sau mổ**
> (Perioperative anticoagulation management)

# VAI TRÒ CỦA BẠN: TRINH SÁT, KHÔNG PHẢI NGUỒN

Bạn **tìm và chỉ điểm**. Một hệ thống kiểm định riêng sẽ tự tải lại từng bài
bạn chỉ điểm từ PubMed và tự dựng bản ghi chuẩn.

Hệ quả — đọc kỹ, vì nó khác hẳn vòng lặp arXiv bạn đang chạy:

- Bạn **KHÔNG** cần tóm tắt đúng. Hệ thống tự đọc bài gốc.
- Bạn **KHÔNG** được ghi trạng thái thẩm định nào ("Verified", "Đã kiểm", "Đạt").
  Bạn không có cách kiểm chứng, nên viết ra là sai sự thật.
- Bạn **KHÔNG** ghi vào Google Sheet nào cả.
- Thứ duy nhất của bạn được dùng làm dữ liệu: **mã PMID** và **chuỗi truy vấn**.

# BƯỚC 1 — Tìm bằng truy vấn CÓ CẤU TRÚC

Không tìm bằng từ khoá rời. Dùng Boolean + thẻ trường MeSH. Gợi ý khởi điểm:

```
("Anticoagulants"[Mesh] OR "Warfarin"[Mesh] OR "Heparin, Low-Molecular-Weight"[Mesh]
 OR "Factor Xa Inhibitors"[Mesh] OR rivaroxaban[tiab] OR apixaban[tiab]
 OR dabigatran[tiab] OR enoxaparin[tiab])
AND
("Perioperative Care"[Mesh] OR "Preoperative Care"[Mesh] OR "Postoperative Care"[Mesh]
 OR perioperative[tiab] OR bridging[tiab] OR "surgery"[tiab])
AND
("Meta-Analysis"[ptyp] OR "Systematic Review"[ptyp]
 OR "Randomized Controlled Trial"[ptyp] OR "Practice Guideline"[ptyp])
```

Được phép sửa truy vấn cho phù hợp. **Nhưng phải ghi lại NGUYÊN VĂN chuỗi đã
thực sự dùng** — không phải mô tả bằng lời.

Chuỗi này là thứ khiến kết quả **chạy lại được**. Không có nó thì không dựng
được sơ đồ PRISMA, và cả lần quét coi như bỏ. Hệ thống sẽ **từ chối** phiếu có
`chuoi_truy_van` không mang dấu hiệu truy vấn thật (thiếu cả `AND`/`OR`, thẻ
`[Mesh]`, ngoặc, lẫn cụm trong nháy).

# BƯỚC 2 — Đếm thật ở từng bước

Ghi ba con số:

| Trường | Nghĩa |
|---|---|
| `so_ket_qua_tho` | PubMed báo tổng cộng bao nhiêu bài |
| `so_da_sang` | Bạn thực sự đọc tiêu đề/tóm tắt bao nhiêu bài |
| `ids` + `loai_tru` | Giữ lại và loại bỏ — tổng phải **≤** `so_da_sang` |

Hệ thống **kiểm phép cộng này**. Số không cộng được thì phiếu bị từ chối nguyên
vẹn. Đừng ước lượng — đếm thật. Lấy **tối đa 10 bài** cho lần chạy thử này.

# BƯỚC 3 — TẢI LÊN phiếu vào thư mục `hang_doi`

**Thư mục `hang_doi`** — ID: `1DIXlmzWeGJ065jryJyNnGOOiqP2tyQ32`

Trong đó đã có sẵn file **`_MAU_PHIEU.json`** — mở ra xem trước, rồi làm y hệt.

## ⚠️ Điểm dễ sai nhất — đọc kỹ

**TẢI LÊN một file `.json` thuần. TUYỆT ĐỐI KHÔNG tạo Google Doc.**

Lý do: Google Docs không đồng bộ nội dung xuống máy tính — chúng chỉ đồng bộ
thành một đường link. Nếu bạn tạo Doc, hệ thống trên máy sẽ **không đọc được gì**,
mà thư mục vẫn trông như có file. Đây là kiểu hỏng tệ nhất: im lặng.

- Tên file: `2026-08-23_chong-dong_pubmed.json` (không có gạch dưới ở đầu)
- Kiểu nội dung: `application/json`
- **Tạo file MỚI. Không sửa, không ghi đè file nào đã có.**

## Cấu trúc phiếu

```json
{
  "ma_phieu": "2026-08-23_chong-dong_pubmed",
  "ngay_quet": "2026-08-23",
  "nguon": "pubmed",
  "cau_hoi": "Quản lý chống đông trước, trong và sau mổ",
  "chuoi_truy_van": "<NGUYÊN VĂN chuỗi đã gửi cho PubMed>",
  "so_ket_qua_tho": 0,
  "so_da_sang": 0,
  "ids": ["pubmed:26095867"],
  "loai_tru": [
    {"id": "pubmed:11111111", "ly_do": "nghiên cứu trên động vật, không phải người"}
  ],
  "ghi_chu": ""
}
```

## Quy tắc cứng — vi phạm là phiếu bị từ chối

1. `ids` đúng dạng `pubmed:<số>`. Không dùng `PMID: 123`, không dùng số trần.
2. `ly_do` loại trừ phải là **câu đọc được**, tối thiểu 5 ký tự. Không được là
   một chữ hay dấu gạch.
3. Một bài **không được** vừa nằm trong `ids` vừa nằm trong `loai_tru`.
4. Không ID nào lặp lại trong cùng phiếu.
5. Nếu ra **0 bài**: vẫn ghi phiếu, và **bắt buộc** điền `ghi_chu` nói rõ vì sao.
   *Quét ra 0 bài là một kết quả, không phải thất bại cần giấu.*

# BƯỚC 4 — Bản nháp cho người đọc (tuỳ chọn)

Nếu có bài đáng chú ý, được tạo Google Doc phân tích song ngữ trong
**thư mục `ban_nhap`** — ID: `1QYXmKIe6rXJ4G6wVDkxUdalZjWfc0e_h`

Mỗi Doc **bắt buộc** mở đầu bằng đúng dòng này:

> ⚠️ **CHƯA KIỂM CHỨNG — không trích dẫn con số nào từ tài liệu này.**

Doc đó chỉ để đọc nhanh, **không phải chứng cứ**, và hệ thống sẽ không đọc tới.

# BƯỚC 5 — Báo cáo lại, ba dòng

```
Đã tải lên : <tên file .json>
Truy vấn   : <chuỗi nguyên văn>
Số liệu    : tìm <n> · sàng <m> · giữ <k> · loại <j>
```

**Nếu bước nào thất bại, nói thẳng bước đó thất bại.** Đừng viết mơ hồ cho trôi
chuyện. Một lần thất bại được báo rõ có ích hơn mười lần thành công được kể lại.

---

## Ghi chú cho Gun (KHÔNG thuộc prompt)

**Tài nguyên đã tạo sẵn trên Drive:**

| Thư mục | ID |
|---|---|
| `hang_doi` — Spark ghi phiếu | `1DIXlmzWeGJ065jryJyNnGOOiqP2tyQ32` |
| `ban_nhap` — Spark ghi Doc nháp | `1QYXmKIe6rXJ4G6wVDkxUdalZjWfc0e_h` |
| `da_kiem_dinh` — SR-Agent ghi, Spark chỉ đọc | `1dpv9Z2AoKKVUuSKxzGNHpaDn1D3zXB9q` |
| `_MAU_PHIEU.json` — mẫu để Spark bắt chước | đã nằm trong `hang_doi` |

**Ba thay đổi so với vòng lặp arXiv, mỗi cái chặn một lỗi ĐO ĐƯỢC trong 21 ngày
dữ liệu cũ:**

| Đổi | Lỗi cũ nó chặn |
|---|---|
| Tải file JSON thay vì ghi Sheet | Sheets ép kiểu làm hỏng mã bài **22/22** dòng |
| Bắt đếm, hệ thống kiểm phép cộng | Cột "Verified" tự khai ở **22/22** dòng, không ai kiểm |
| Cấm sửa file cũ, chỉ tạo mới | Spark từng bỏ ID sổ được chỉ định, tự tạo sổ thứ hai |

**Nếu phiếu đầu tiên bị từ chối, đó là dấu hiệu TỐT** — cổng đang làm việc, khác
hẳn cột "Verified" cũ nhận mọi thứ rồi gật đầu.
