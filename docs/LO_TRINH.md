# Lộ trình SR-Agent & AnesthOS

> **Vì sao có tài liệu này.** Lộ trình các chặng trước nay chỉ tồn tại trong hội thoại
> và trong tệp kế hoạch của từng phiên. Tệp đó **chết theo phiên**, Antigravity không
> đọc được, nên mỗi vòng phản biện lại phải **viết lại từ đầu** thay vì sửa một mục.
> Đó đúng là hỏng mà `docs/DECISIONS.md` được lập ra để chặn: *"đã chốt rồi mà không
> tìm lại được"*.
>
> **Cách sửa tài liệu này:** mỗi bước có **mã ổn định** (A‑0, A1, B3…). Muốn đổi thì
> sửa **đúng mục đó** và ghi lý do; **không viết lại cả bản**. Mã không bao giờ được
> tái sử dụng cho việc khác — bước bị bỏ thì đánh dấu ✗ và giữ nguyên mã.
>
> **Cập nhật**: 2026-08-31 · **Nhánh gốc**: `claude/sr-agent-architecture-audit-scn4v6`

---

## 1 · Mục tiêu

> **Vấn đề lâm sàng → hướng dẫn xử trí có bằng chứng → tự biết khi lỗi thời → chỉ ra
> khoảng trống y văn để thiết kế nghiên cứu.**

Đầu ra của SR-Agent **chính là** kho dữ liệu tĩnh của AnesthOS. Hai hệ không cạnh tranh —
một cái sinh ra cái kia.

**Hướng đã chốt:** SR-Agent **sinh dữ liệu mới có bằng chứng, thay dần dữ liệu dựng** —
không đi hướng thẩm định ngược 16.417 khẳng định cũ.

**Ràng buộc cứng:** một người ký duy nhất (Gun), >8 giờ/tuần.

---

## 2 · Hiện trạng — đo ngày 2026-08-31

### 2.1 · SR-Agent

| Hạng mục | Số đo |
|---|---|
| Kiểm thử | **629 thu thập · 629 xanh · 0 đỏ** tại `cb86e3a` |
| Phụ thuộc | 7 gói (`pyproject.toml`) |
| Tệp kiểm thử | 39 |

**Chênh lệch 629 vs 644 — đã giải.** AG‑1 báo 644 kiểm thử xanh. Nhánh đã đẩy thu
thập được **629**, tất định: không có `importorskip`, `skipif`, `collect_ignore`, không
kiểm thử nào phụ thuộc biến môi trường, không có tệp `test_*.py` nào ngoài `tests/`.
Nên **15 kiểm thử kia chỉ tồn tại trên máy AG‑1 và chưa từng vào kho.**

> Đây **cùng hạng lỗi** với sự cố thư mục dữ liệu: báo số đo từ một môi trường **không
> phải** môi trường đang được kiểm. Luật N‑1/N‑2/N‑3 (§7) sinh ra để chặn đúng việc này.

### 2.2 · AnesthOS

Dữ liệu thật ở nhánh **`origin/feat/p1-domain`** — **23 tệp** trong `src/domain/data/`.

**16.417 khẳng định lâm sàng · 2.271 ưu tiên 1 · 100% ở mức "chỉ có nguồn cấp tệp".**

| Tệp | Lá lâm sàng | Ưu tiên 1 |
|---|---:|---:|
| `surgeries.json` | 9.645 | **463** |
| `drugs.json` | 1.127 | **683** |
| `nora_locations.json` | 1.040 | 123 |
| `chronic_meds.json` | 673 | 346 |
| `chronic_meds_guidelines_vi.json` | 673 | 346 |
| `lab_tests.json` (+ `_info_vi`) | 258 ×2 | 86 ×2 |
| `crisis_protocols.json` | 150 | 30 |
| `local_anesthetics.json` (+ `_info_vi`) | 108 ×2 | **54** ×2 |
| *(14 tệp còn lại)* | 3.079 | 0 |
| **TỔNG** | **16.417** | **2.271** |

Ba điều bảng này nói ra:

| Quan sát | Hệ quả |
|---|---|
| `drugs.json` chiếm 7% số lá nhưng **30% số P1** | mật độ nguy hiểm ≠ khối lượng → ưu tiên theo P1 |
| 463 P1 của `surgeries.json` **toàn là liều theo loại phẫu thuật** | mỗi cái cần **hai** phép kiểm: trong trần nhãn? đúng phác đồ khuyến cáo? |
| `local_anesthetics.json` chỉ **54** P1 | đúng cỡ chạy thử: nhỏ để xong trong một chu kỳ, nguy hiểm để có ý nghĩa |

### 2.3 · Còn thiếu — đúng ba chỗ

| Thiếu | Hệ quả |
|---|---|
| `tools/sources/tham_khao.py` — cửa `/references` | không lấy được danh mục tham khảo → **không dựng được chuỗi bằng chứng, không đo được chung tổ tiên** |
| Bộ kiểm biên | **1.492** khẳng định liều chưa từng đối chiếu trần nhãn |
| Bước 5 của 5A (*Assess*) | không có gì phát hiện dữ liệu lỗi thời |

### 2.4 · Thang mức phủ hiện không phân biệt được gì

100% khẳng định rơi vào **đúng một** ô (`chỉ có nguồn cấp tệp`). Thang ba mức mà cả kho
nằm một mức thì không đo được tiến độ → tách thành **bốn** mức ở A0.

---

## 3 · Trạng thái đích

Với **một** khẳng định ưu tiên 1, hệ phải trả lời được cả năm câu:

| # | Câu hỏi | Hôm nay |
|---|---|---|
| 1 | Con số là gì? | ✅ |
| 2 | Nguồn nào nêu nó — **ở dòng nào**? | ⛔ chỉ có tên tệp |
| 3 | Nguồn đó dựa trên **nghiên cứu gốc** nào, bậc mấy, GRADE mấy? | ⛔ |
| 4 | Hai nguồn xác nhận nó có **thật sự độc lập** không? | ⛔ chưa từng hỏi |
| 5 | Nó **lỗi thời** chưa? Y văn trống thì **nên nghiên cứu gì**? | ⛔ chưa xây |

Câu 5 là thứ **không công cụ tra cứu nào của con người làm** — giá trị riêng của
SR-Agent. Nhưng nó là **bước cuối**, không phải bước đầu (nguyên tắc 1).

---

## 4 · Bảy nguyên tắc chi phối

**Không mở lại** trừ khi có dữ liệu bác bỏ.

| # | Nguyên tắc | Nghĩa vận hành |
|---|---|---|
| **1** | **ĐÚNG trước MỚI** | không kiểm "có lỗi thời không" trước khi chứng minh "có đúng không". Bảng cũ mà đúng an toàn hơn bảng mới mà bịa → **khoá Chặng C sau Chặng B** |
| **2** | **Số không đi qua LLM** | liều/ngưỡng/nồng độ hiển thị thẳng từ kho có cấu trúc. LLM chỉ được **định vị** văn bản, không được **sinh** giá trị |
| **3** | **Rẻ trước, đắt sau** | mọi bước tất định chạy **trước** bước LLM (`docs/HANDOVER.md` §1). Không đảo |
| **4** | **Ba trạng thái, không phải hai** | ĐẠT / TRƯỢT / **KHÔNG KIỂM ĐƯỢC**. "Không đo được" ≠ "đạt" |
| **5** | **Mù kết cục** | loại nghiên cứu vì nó **nghiên cứu gì**, không vì nó **tìm ra gì** |
| **6** | **Không ai tự chấm bài mình** | bốn vai tách rời (§6) |
| **7** | **Cổng người đóng kín** | chưa ký thì tệp **không dùng được**. Sinh sai (bịa số mới tới tay bệnh nhân) nguy hơn kiểm sót (bỏ lọt lỗi cũ) |

---

## 5 · Lộ trình

### 5.1 · Chặng A — đo trước, xây sau

| Mã | Việc | Nghiệm thu | Trạng thái |
|---|---|---|---|
| **A‑0** | Đưa lộ trình vào kho (`docs/LO_TRINH.md`) + quyết định tầng đồ thị vào `DECISIONS.md`; kéo `cb86e3a`; giải chênh 629/644; sửa `EF2`; **sửa cổng M6** | phiên mới đọc được lộ trình **không cần hỏi lại** | ✓ xong |
| **A0** | Lược đồ **cấp dòng** + băm bộ ba `(nguồn ‖ mã rút ‖ lược đồ)` + **bốn trạng thái đồng thuận** + tách mức phủ thành 4 mức | nguồn đổi **hoặc** mã rút đổi → khẳng định **tự rơi về chưa-thẩm-định** | ⏳ **đặc tả xong** (`docs/DAC_TA_A0.md`) — chờ AG‑2 viết kiểm thử |
| **A1** | **ĐO TỶ LỆ ĐO ĐƯỢC ĐỘC LẬP** trên 54 khẳng định thuốc tê — phép giao tập hợp thuần, **chưa thêm thư viện** | phân bố 4 trạng thái, tổng **= 54** | ○ |
| **A2** | **Kiểm biên** — mọi liều đối chiếu trần nhãn DailyMed (XML, bóc tất định) | chạy trên **1.492** khẳng định; báo **đích danh** cái vượt trần | ○ |
| **A3** | Xây `tools/sources/tham_khao.py`; kiểm phả hệ **cấp khẳng định**. NetworkX vào đây **có điều kiện** | với một con số: trả về bài gốc **mỗi nguồn** dẫn; bắt chung tổ tiên qua ≥2 chặng | ○ |
| **A4** | Đo độ nhạy truy vấn — báo **số bài sót + mã đích danh**, không báo phần trăm | 0 bài sót trên tập chuẩn | ○ |

#### Bốn trạng thái đồng thuận

Thay cho nhị nguyên *đồng ý / không đồng ý* — vì **hai nguồn trùng nhau có thể là một
nguồn chép hai lần** (nhãn FDA và hướng dẫn hội thường cùng dẫn về các công bố thập
niên 1970–80).

| Trạng thái | Điều kiện | Một người ký đủ? |
|---|---|---|
| `DOC_LAP` | hai nguồn, phả hệ **khác nhau** | ✅ |
| `CHUNG_TO_TIEN` | hai nguồn cùng dẫn về một bài gốc | ⛔ tính là **một** nguồn |
| `KHONG_DO_DUOC_DOC_LAP` | ít nhất một nguồn không khai phả hệ | ⛔ **không phải "đã kiểm"** |
| `MOT_NGUON` | chỉ tìm được một | ⛔ |

Phả hệ kiểm **ở cấp khẳng định**, không ở cấp tài liệu: câu hỏi đúng là *"tại chỗ nêu
con số 4,5 mg/kg, nguồn này dẫn bài nào?"* — không phải *"hai tài liệu trùng bao nhiêu
phần trăm danh mục tham khảo?"*

#### Cổng G1

> **A1 là bước quan trọng nhất cả lộ trình.** Nó trả lời câu quyết định toàn bộ mô hình
> ký: *một người ký đủ cho bao nhiêu phần trăm?* **Chưa đo xong thì không hứa khối
> lượng, không hứa thời hạn.**

| Kết quả A1 | Nghĩa | Đi tiếp |
|---|---|---|
| phần lớn `DOC_LAP` | một người ký đủ | chạy Chặng B |
| phần lớn `KHONG_DO_DUOC` | mô hình một-người-ký **không đủ** | **DỪNG**, thiết kế lại mức ký |

### 5.2 · Chặng B — chạy thử chủ đề thuốc tê (108 khẳng định · 54 P1)

| Mã | Việc |
|---|---|
| **B1** | Rút `max_ceiling` từ nhãn thuốc — **Luồng B, tất định**, không LLM |
| **B2** | Rút `clinical_target` từ hướng dẫn hội — **Luồng C, 5A**; LLM chỉ **định vị** + `verify_quote()` |
| **B3** | Kiểm phả hệ **từng khẳng định**, gán 1 trong 4 trạng thái |
| **B4** | Sinh `local_anesthetics.v2.json` — mỗi khẳng định kèm nguồn cấp dòng, bậc chứng cứ, GRADE, trạng thái đồng thuận |
| **B5** | Dựng đồ thị (NetworkX) + hiển thị cho cổng người (PyVis, **tài nguyên nội tuyến**) |
| **B6** | So v2 với tệp dựng cũ — liệt kê **mọi chỗ lệch**, không sửa lặng |

**Vì sao tách `max_ceiling` khỏi `clinical_target`:** ca lidocaine 3,0 vs 4,5 mg/kg
**không phải mâu thuẫn** — nhãn cho trần pháp lý, hướng dẫn cho đích thực hành an toàn
hơn. Gộp một trường là làm mất thông tin.

**Cổng G2:** ca lidocaine phải phân giải rõ **trần 4,5 vs đích 3,0**, kèm toạ độ trích
dẫn **và phả hệ mỗi con số**. Hai nguồn cùng dẫn một bài 1978 thì **phải nói thẳng**.

### 5.3 · Chặng C — quyết định trước, dữ liệu sau

| Mã | Việc |
|---|---|
| **C0** | **Liệt kê N quyết định app phải ra** → suy ra tập cờ tối thiểu. Cờ không quyết định nào cần → thẻ tự do |
| **C1** | Cấu trúc lại bệnh van tim theo **bộ ba huyết động** (tần số · tiền tải · hậu tải · co bóp) |
| **C2** | Mở rộng theo **miền nguồn**: `drugs` (683 P1) → `chronic_meds` (692) → `surgeries` (463) → `nora_locations` (123) → `lab_tests` (172) → `crisis_protocols` (30) |
| **C3** | Rà lỗi thời + tìm khoảng trống y văn + đề xuất thiết kế nghiên cứu — dùng lại `THIET_KE_TOI_UU` trong `tools/dat_cau_hoi.py` |

**Vì sao C0 thay việc "chuẩn hoá 648 cờ":** đã đo — 648 cờ / 2.098 lượt dùng; top 40
chỉ phủ **46%**; **391/648 (60%) dùng đúng một lần**. Và cả `src/domain/` chỉ có 3 tệp
`.ts`, **không tệp nào rẽ nhánh theo cờ** — cờ hiện **không điều khiển gì**. Dọn trước
khi biết dùng làm gì là dọn mù.

**Vì sao mở rộng theo miền nguồn, không theo nhóm thuốc:** nhóm thuốc chỉ phủ
`drugs` + `local_anesthetics` = **791/2.271 = 35%** số P1.

---

## 6 · Vai — chống tự chấm bài mình

| Vai | Được làm | **Cấm** |
|---|---|---|
| **Claude** | viết đặc tả, tính số nghiệm thu | viết mã cài đặt, tự chạy nghiệm thu |
| **AG‑2** | viết kiểm thử **từ đặc tả, trước khi có mã** | đọc mã AG‑1, chạm `tools/**` |
| **AG‑1** | viết mã cho kiểm thử xanh | chạm `tests/**`, **dò ngược số của Claude để khớp** |
| **AG‑3** | chạy nghiệm thu trên mã đã commit, chỉ báo số | sửa bất cứ thứ gì |
| **Gun** | ký lâm sàng — cổng cuối | — |

**Số lệch giữa Claude và AG‑1 là BẤT ĐỒNG THẬT**, không phải lỗi của AG‑1 — ghi cả hai
số, chỉ ra khoá nào đếm khác, chuyển Gun quyết. Số nghiệm thu **đã sai một lần rồi**
(20.416/16.562/2.241 → 20.279/16.417/2.271): chúng là **số đo, không phải chân lý**.

---

## 7 · Kiểm chứng

| Bước | Lệnh | Đạt khi |
|---|---|---|
| mọi bước | `python3 -m pytest` | xanh hết; **số kiểm thử chỉ tăng** (luật L6) |
| mọi bước | `bash scripts/gate_m6.sh` | qua — cổng **đóng khi không kiểm được** |
| A1 | `python3 tools/<bộ đo>.py --chu-de thuoc-te` | in đường dẫn tuyệt đối + số tệp **trước** mọi con số (N‑1); tổng 4 trạng thái **= 54** |
| A2 | `python3 tools/<kiểm biên>.py --du-lieu .../src/domain/data/` | **dừng** nếu thiếu `provenance_manifest.json` (N‑2); liệt kê **đích danh** cái vượt trần |
| A3 | kiểm thử phả hệ có ca dựng sẵn **3 chặng** | bắt chung tổ tiên qua ≥2 chặng; ca thiếu danh mục → `KHONG_DO_DUOC`, **không** → `DOC_LAP` |

**Ba luật nguồn dữ liệu** — sinh ra sau sự cố AG‑1 chạy nhầm vào thư mục thiếu
`provenance_manifest.json`, khiến **kết luận chính bị đảo ngược** dù cả 6 số thô đều khớp:

| Luật | Nội dung |
|---|---|
| **N‑1** | mọi lệnh nghiệm thu in **đường dẫn tuyệt đối + số tệp JSON đọc được** trước mọi con số khác |
| **N‑2** | thiếu `provenance_manifest.json` → **DỪNG**, không im lặng chạy tiếp như "không có nguồn" |
| **N‑3** | báo cáo ghi số kiểm thử `--collect-only` **thu thập được**, không chỉ số xanh |

**Nguồn dữ liệu chốt bằng git, không bằng đường dẫn ổ đĩa:**

```bash
git -C <AnesthOS-app> ls-tree -r --name-only origin/feat/p1-domain | grep domain/data
# phải ra 23 tệp, có provenance_manifest.json
```

**Ca kiểm thử quan trọng nhất Chặng A** là ca âm tính: hai nguồn cùng dẫn một bài 1978
**phải** ra `CHUNG_TO_TIEN`. Ra `DOC_LAP` nghĩa là bẫy đồng thuận ảo vẫn còn nguyên,
chỉ là lần này có mã che.

---

## 8 · Điều có thể bác bỏ chính lộ trình này

| Rủi ro | Dấu hiệu | Xử |
|---|---|---|
| **Mô hình một-người-ký không đứng được** | A1 cho phần lớn `KHONG_DO_DUOC` | **Dừng ở G1.** Kết quả đúng, không phải thất bại — biết sớm còn hơn ký 2.271 khẳng định trên một nền độc lập không tồn tại |
| **Nhãn thuốc không khai phả hệ** | A3 không lấy được danh mục của nguồn Luồng B | ghi `KHONG_DO_DUOC`, **không** suy ra là độc lập |
| **`drugs.json` dẫn sách giáo khoa** (683 P1, Stoelting's) | không có cửa tự động nào tới sách | coi sách là **tài liệu cấp ba**, truy ngược lên nguồn gốc của nó (FDA SPL, hội chuyên ngành) |
| **Hàng chờ duyệt phình vô hạn** | cổng người chủ đề trước chưa thông mà máy đã chạy chủ đề mới | **giới hạn công việc dở**: máy sang **chế độ tiền xử lý nền** — nạp thô, dựng cây câu hỏi, **nhưng chưa tạo bản ghi** |

**Thống nhất trước khi chạy A2:** kiểm biên nhiều khả năng tìm ra khẳng định vượt trần
nhãn. Phản xạ tự nhiên là sửa nhanh cho sạch. **Đừng.** Mỗi chỗ vượt trần là một mẫu về
**cách bộ dữ liệu này hỏng**; sửa lẻ xoá mất thông tin đó. Ghi hết, tìm quy luật, sửa
theo lớp.

---

## 9 · Đã bỏ khỏi lộ trình — và vì sao

Giữ mục này để **không ai đề xuất lại** mà không biết nó từng bị bác vì lý do gì.

| Bỏ | Vì sao |
|---|---|
| LlamaIndex `KnowledgeGraphIndex` | rút bộ ba **bằng LLM ở bước nạp** — đảo ngược nguyên tắc 3; chữ ký bảo chứng cho phép rút không lặp lại được. Xem `DECISIONS.md` |
| `TreeSummarize` làm tầng trả lời | sinh văn xuôi **tổng hợp chéo nguồn** — đúng chỗ ảo giác và trộn đồng thuận ảo phát sinh; AnesthOS không chạy LLM lúc truy vấn được (BS-F) |
| `SimpleGraphStore` làm kho lưu | yếu hơn JSON đã ký, lại thêm bản sao chân lý thứ hai |
| Kiểm nhất quán nội tại `mg/kg × cân nặng ↔ trần` | **đã chạy thử**: 14/14 cặp nhất quán ở 66,7–80 kg → **không có sức phân biệt** |
| Đóng băng "top 40 cờ" | đã đo: top 40 chỉ phủ **46%**; 60% cờ dùng đúng một lần |
| Ngưỡng trùng lặp danh mục 0,3 **ở cấp tài liệu** | đo sai cấp — phải đo **tại chỗ nêu con số**; và nhãn FDA thường không có danh mục để đo |
| Hứa "50–150 ca hội chẩn ngoài" | con số đoán khi chưa đo. **A1 sẽ cho số thật** |
| Thẩm định ngược 16.417 khẳng định cũ | đã chốt hướng: **sinh dữ liệu mới thay dần** |
