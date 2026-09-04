# Sổ quyết định dự án SR-Agent

> **Tại sao có tài liệu này**: các quyết định trước đây nằm rải trong spec, git log, và hội
> thoại — dẫn tới tình trạng "đã chốt rồi mà không tìm lại được". Từ nay MỌI quyết định
> phạm vi/kiến trúc ghi ở đây, **có tên gọi bằng lời**, mã số chỉ là phụ.
>
> Quy ước: mỗi mục có **Tên gọi** (dùng khi nói chuyện) và *mã* (dùng khi tham chiếu trong code/spec).

---

## ĐÃ CHỐT

### 1. Mở phạm vi y sinh — *mã cũ: D30-S1*
**Chốt ngày**: 2026-08-16 · **Người chốt**: chủ dự án (Gun)

SR-Agent **được phép** xử lý chủ đề và tài liệu y sinh/lâm sàng.

- **Thay thế** ràng buộc CS-only tại `docs/HANDOVER.md:23` và `docs/specs/D30-...md:12-13`.
- **Bằng chứng đã có từ trước**: `AnesthOS-app/README.md:9,48,51` gọi `sr-agent` là
  *"autonomous clinical AI agent"* và là consumer của Clinical Engine. Quyết định đã tồn
  tại ở repo AnesthOS nhưng chưa từng ghi ngược về repo này — đó là lý do nó "mất tích".
- **Mở khoá**: nguồn y khoa, rubric y khoa, Risk of Bias, GRADE, chủ đề lâm sàng.
- **KHÔNG mở**: xử lý dữ liệu bệnh nhân thật (PHI). Ngữ liệu là **bài báo đã xuất bản**.
  Ranh giới này giữ nguyên và cần giữ tường minh.

### 2. Mức chất lượng mục tiêu: "chuẩn Q1" là mức chất lượng, KHÔNG nộp tạp chí
**Chốt ngày**: 2026-08-16

Bài systematic review viết ra nhắm **đạt mức chặt chẽ của tạp chí Q1**, nhưng không nhằm
nộp đăng thực tế.

- **Hệ quả — BỎ**: đăng ký PROSPERO (chỉ cần khi nộp thật).
- **Hệ quả — GIỮ**: PRISMA 2020 (sơ đồ dòng + checklist 27 mục), sàng lọc kép + κ,
  Risk of Bias, GRADE, chiến lược tìm kiếm tái lập được. Đây là cái tạo ra chất lượng thật.

### 3. Nguồn dữ liệu: ưu tiên miễn phí
**Chốt ngày**: 2026-08-16

| Nguồn | Trạng thái | Lý do |
|---|---|---|
| **PubMed / MEDLINE** | ✅ dùng | Miễn phí, API E-utilities ổn định, dialect MeSH đã đặc tả tại `D30:102` |
| **Cochrane CENTRAL** | ✅ dùng | Miễn phí phần tra cứu; nguồn RCT tốt nhất cho câu hỏi can thiệp |
| **Embase** | ❌ loại | Cần license trả phí |
| IEEE, arXiv | ✅ giữ | Đã chạy; hữu ích cho chủ đề giao thoa kỹ thuật |

**Ghi vào Limitations của bản thảo**: thiếu Embase ⇒ có thể bỏ sót tài liệu châu Âu và
tài liệu dược. Đây là hạn chế phải khai báo, không phải giấu.

### 4. Ưu tiên meta-analysis hơn narrative synthesis
**Chốt ngày**: 2026-08-16

Khi dữ liệu cho phép gộp, **ưu tiên meta-analysis** vì bậc chứng cứ cao hơn.
Narrative synthesis là phương án lui khi không đạt điều kiện đồng nhất.

- **Điều kiện gác cổng** (không được bỏ qua): đồng nhất về lâm sàng (population,
  intervention, comparator) và về phương pháp (thiết kế nghiên cứu, cách đo outcome).
  Gộp nghiên cứu không đồng nhất cho ra con số đẹp nhưng **sai khoa học** — đây là lỗi
  nặng nhất mà reviewer bắt được.
- **Kéo theo khối lượng**: random/fixed effects, I², forest plot, funnel plot, Egger's test.

### 5. Ngôn ngữ bản thảo: song ngữ Anh — Việt
**Chốt ngày**: 2026-08-16

Bản thảo sinh ra ở **cả hai ngôn ngữ**, tiếng Anh là bản chuẩn (thuật ngữ khoa học),
tiếng Việt là bản song hành.

- **Bất biến bắt buộc**: hai bản phải dùng **cùng một bộ số** từ tầng extraction. Dịch
  không bao giờ được sinh lại số. Số là slot, chữ là bản dịch.

### 6. Chủ đề bài SR đầu tiên
**Chốt ngày**: 2026-08-16

> **"Tiếp cận quản lý chống đông trước, trong và sau mổ"**
> (Perioperative anticoagulation management)

- Chủ đề lâm sàng thuần túy ⇒ xác nhận quyết định #1.
- **Lưu ý kỹ thuật quan trọng**: chủ đề này chứa dày đặc **liều thuốc, ngưỡng INR, và
  khoảng thời gian** (ngừng thuốc trước mổ bao nhiêu giờ, bắc cầu heparin, thời điểm dùng
  lại). Nghĩa là bản thảo sẽ chứa số lâm sàng trích từ nghiên cứu ⇒ tường lửa số
  (`tools/guard/firewall.py`) **phải bổ sung cả đơn vị lâm sàng lẫn đơn vị thống kê**
  (mg, mcg, IU, mL, giờ, INR, OR, RR, HR, 95% CI, p, I²). Hiện chưa có đơn vị nào trong số đó.

### 7. Kiến trúc: SR-Agent là BỘ MÁY SINH CHỨNG CỨ của AnesthOS
**Chốt ngày**: 2026-08-23

> AnesthOS đưa ra khuyến cáo lâm sàng. Khuyến cáo phải có chứng cứ.
> **Chứng cứ đến từ SR-Agent.** SR-Agent tách riêng KHÔNG phải vì nó là sản phẩm
> khác, mà vì nó **tái dùng được cho mọi lĩnh vực** — đổi nguồn tham khảo là có
> một hệ tri thức hệ thống cho bất kỳ vấn đề nào.

- **Đính chính khung hiểu cũ**: các tài liệu trước mô tả "hai sản phẩm riêng biệt".
  Sai về quan hệ. Đúng là: **một chuỗi giá trị** — SR-Agent (sinh chứng cứ) nuôi
  AnesthOS (ra khuyến cáo). Tách repo là quyết định kỹ thuật để tái dùng, không phải
  ranh giới sản phẩm.
- **Hệ quả trực tiếp lên thiết kế**: lõi SR-Agent phải **mù lĩnh vực**. Mọi thứ đặc
  thù y khoa (nguồn PubMed, đơn vị lâm sàng, bậc chứng cứ) phải nằm ở tầng cắm thêm,
  không được ngấm vào lõi. Đây là lý do `gate_m6.sh` có luật cấm rò thuật ngữ lĩnh
  vực vào `sr_agent/` — luật đó giờ có căn cứ kiến trúc, không chỉ là quy ước.
- **Thứ tự ưu tiên đi kèm**: hoàn thiện SR-Agent chạy thật trước. Lớp A/B/C của
  AnesthOS **chỉ bộc lộ điểm yếu khi có chứng cứ thật chảy vào** — thiết kế thêm
  lúc chưa chạy là đoán.

### 8. Mở khóa danh sách nguồn — bỏ ràng buộc 2 nguồn
**Chốt ngày**: 2026-08-23 · *(thay thế mục "ngoại lệ vùng cấm" đang chờ)*

> Cho phép **tất cả** các nguồn. `config.py` không còn khóa cứng arXiv + IEEE.

- **Trước**: `Document.source` là `Literal["ieee","arxiv"]`, `ID_PATTERNS` là hằng số.
  Thêm một nguồn = sửa mã lõi = đụng vùng cấm. Ràng buộc này sinh ra ở chặng M0-M2
  để giữ staging đồng nhất trong lúc dựng pipeline; nó đã xong vai trò.
- **Sau**: sổ đăng ký mở qua `config.register_source()`. Nguồn tự khai quy tắc ID và
  tier của mình tại module định nghĩa fetcher.
- **Ranh giới còn giữ** (mở khóa không phải bỏ kiểm soát):
  - Nguồn **đã đăng ký** → kiểm quy tắc ID nghiêm ngặt, dùng tier khai báo.
  - Nguồn **chưa đăng ký** → vẫn chạy, nhưng nhận `UNKNOWN_SOURCE_TIER = 5` (hạng
    thấp nhất). Chưa thẩm định thì không được hưởng uy tín — mặc định thận trọng.
  - `source` rỗng vẫn bị từ chối: tài liệu không truy vết được nguồn thì vô giá trị.
- **Kiểm chứng**: 266 test xanh; `ieee` vẫn bắt buộc 8 chữ số, `arxiv` vẫn bắt buộc
  tiền tố — mở khóa không làm lỏng nguồn cũ.

---

### 9. Tầng đồ thị là LỚP SUY RA, không phải kho lưu — và không rút bộ ba bằng LLM
**Chốt ngày**: 2026-08-31 · **Người chốt**: chủ dự án (Gun)

Đề xuất được xét: quy trình `LlamaIndex` → `NetworkX` → `PyVis` (nạp thư mục bằng
`SimpleDirectoryReader`, lập `KnowledgeGraphIndex`, lưu `SimpleGraphStore`, truy vấn
bằng `TreeSummarize`).

**Đó không phải một quyết định mà là ba, bị gói chung trong một thư viện.** Tách ra:

| Tầng | Là gì | Phán quyết |
|---|---|---|
| 1 · Mô hình dữ liệu — đồ thị nút/cạnh | biểu diễn bằng chứng thế nào | **NHẬN** |
| 2 · Cách nạp — LLM sinh bộ ba từ văn bản | dữ kiện vào bằng đường nào | **BỎ** |
| 3 · Cách truy vấn — `TreeSummarize` sinh văn xuôi | dữ kiện ra bằng đường nào | **BỎ** |

**Chốt: lấy NetworkX và PyVis, bỏ LlamaIndex.**

- **Vì sao bỏ tầng 2.** `KnowledgeGraphIndex` gọi `_llm_extract_triplets` cho **mọi
  đoạn văn bản, ngay ở bước nạp** — **đảo ngược** nguyên tắc *"rẻ trước, đắt sau"* đã
  ghi ở `docs/HANDOVER.md` §1. Ba hệ quả cụ thể:
  - Bộ ba `(lidocaine, liều tối đa, 4,5 mg/kg)` do LLM sinh → **con số liều đi qua LLM**.
  - Cùng nguồn + cùng mã rút → bộ ba **khác nhau mỗi lần chạy** → chữ ký khoá theo băm
    mã rút **bảo chứng cho một thứ không lặp lại được**. Đây là hệ quả chết người nhất.
  - Chỉ trỏ tới *đoạn văn bản*, không tới *trích dẫn tại chỗ nêu con số* → **không đo
    được chung tổ tiên**, tức không phát hiện được bẫy đồng thuận ảo.
  - Bản thân LlamaIndex đã thay `KnowledgeGraphIndex` bằng `PropertyGraphIndex`, nhận
    rằng mô hình bộ ba thuần *"hạn chế về khả năng biểu đạt"*.
- **Vì sao bỏ tầng 3.** `TreeSummarize` sinh văn xuôi **tổng hợp chéo nguồn** — đúng chỗ
  ảo giác và trộn lẫn đồng thuận ảo phát sinh. Và AnesthOS **không chạy LLM lúc truy vấn
  được** (BS-F: ngoại tuyến, <1s), nên mọi văn xuôi đều phải tiền tính và có người ký.
- **Vì sao NHẬN tầng 1 — và vì sao không mâu thuẫn với việc từng bác đồ thị.** Ranh giới
  khác nhau, không phải đổi ý:

  | | Bác | Nhận |
  |---|---|---|
  | Đồ thị làm **kho lưu** thay JSON | ✗ | |
  | Đồ thị **dựng lại từ JSON mỗi lần chạy, dùng xong vứt** | | ✓ |

  JSON đã ký là **bản gốc duy nhất**. Đồ thị không được ký, không đẩy sang AnesthOS.
  Đồ thị lệch JSON → **JSON đúng, mã dựng đồ thị sai**. Cùng kỷ luật đã dùng cho
  `muc_phu` trong `tools/so_phu_bang_chung.py`: **suy ra, không có setter**.
- **NetworkX kiếm chỗ đứng bằng đúng bài toán chung tổ tiên.** `ancestors(A) & ancestors(B)`
  — tất định, không LLM. Tự viết phép duyệt nhiều chặng này là chỗ lỗi lệch-một **trả về
  "độc lập" khi thực ra không** — hỏng im lặng, loại nguy hiểm nhất.
  **Ranh giới**: áp chính nguyên tắc *rẻ trước, đắt sau* lên đề xuất này — bước A1
  (54 khẳng định) chạy bằng **phép giao tập hợp thuần, chưa thêm thư viện**. NetworkX
  chỉ vào ở A3 và **chỉ khi** A1 chứng minh có phả hệ nhiều chặng thật.
- **PyVis** nhắm vào nút cổ chai thật — 8 giờ/tuần của một người. Bảng 2.271 dòng không
  đọc nổi; đồ thị **nhìn thấy được** khẳng định mồ côi và cụm khẳng định cùng treo trên
  một bài cũ. **Ranh giới**: PyVis mặc định nạp `vis.js` **từ CDN** — vi phạm ngoại
  tuyến; bắt buộc dùng tài nguyên nội tuyến.
- **LLM còn được dùng ở đâu**: **định vị** đoạn văn chứa con số (kèm `verify_quote()`
  trong `tools/screen_run.py`), và soạn **nháp** lời giải thích cho người ký duyệt.
  Không bao giờ **sinh** con số, không bao giờ tự đưa văn xuôi vào dữ liệu.
- **Ghi chú về khối lượng**: nguồn lớn nhất — nhãn thuốc DailyMed — là **XML có cấu
  trúc**, không phải văn xuôi. Bóc tất định thắng LLM ngay tại chỗ đề xuất kia mạnh nhất.
- **Xem thêm**: `docs/LO_TRINH.md` §5.

---

### 10. Quy ước ký hiệu — một chữ cái, một nghĩa, vĩnh viễn
**Chốt ngày**: 2026-08-31 · **Người chốt**: chủ dự án (Gun)

Ký hiệu trong kho này sinh sôi theo cảm tính lúc viết, không theo quy tắc. Soát lại
tìm được **bốn va chạm thật**, trong đó nặng nhất là chữ `M`: nó vốn đã là chặng phát
triển `M0…M6` (`gate_m6.sh` là cổng của M6), nhưng lại bị dùng làm đích nghiệm thu
`M1…M8` trong `DAC_TA_A0.md` — nên **cùng một tệp có `M6` mang hai nghĩa**.

- **Chốt**: `docs/QUY_UOC_KY_HIEU.md` là nguồn chân lý. Ký hiệu không có dòng trong sổ
  đăng ký ở §3 thì coi như không tồn tại.
- **Hai trục phân loại**: phạm vi (toàn cục / cục bộ) và vai trò (luật · mốc lộ trình ·
  phân loại · ràng buộc bất biến · đích nghiệm thu).
- **Toàn cục** thì một chữ cái mang **một** nghĩa, đời đời, không tái cấp kể cả khi
  series đã ngừng dùng. **Cục bộ** (`R`, `Đ`) thì cố ý khởi động lại từ 1 ở mỗi đặc tả,
  nhưng dẫn từ ngoài **bắt buộc** gắn mã tài liệu: `A0.R4`, `V1.Đ2`.
- **Luật cấp ký hiệu mới, bốn bước**: tra sổ trước · nếu là luật vận hành thì nối vào
  `L` đừng đẻ series mới · cục bộ thì dùng lại `R`/`Đ` và khai rõ · cấp series toàn cục
  mới thì cùng commit phải thêm dòng vào sổ.
- **Đã áp**: `N‑1/N‑2/N‑3` gộp vào series luật thành `L7/L8/L9` (bớt hẳn một series,
  không phải đổi tên nó); `N1…N6` của V1 và `M1…M8` của A0 đều thành `Đ1…`; hai bộ
  `R` được khai rõ là cục bộ và độc lập nhau.
- **Không đụng**: mã bước `A0…C3`, cổng `G1/G2`, `P1/P2/P3`, `M0…M6`. Bốn bộ này không
  có lỗi, chỉ thiếu chỗ khai — đổi tên thứ đang chạy đúng là tự tạo rủi ro.
- **Không sửa kho AnesthOS**: `BS-B/BS-C/BS-F` chỉ được **đăng ký** để tránh đụng.
- **Kiểm chứng**: tập hợp mọi con số trong các tệp bị sửa **y hệt trước và sau** — chỉ
  chữ cái đổi.

---

### 11. Phác đồ do máy soạn nháp từ kho NotebookLM; NotebookLM là BỘ SOẠN NHÁP, không phải nguồn chân lý
**Chốt ngày**: 2026-09-01 · **Người chốt**: chủ dự án (Gun)

Gun đặt câu hỏi nền: *"mình có đang xây một thứ phức tạp trong khi thứ đơn giản có hiệu
quả lại không làm không?"* — kèm bằng chứng: sau nhiều tháng, dự án có ~10 tài liệu và
735 kiểm thử nhưng **0 sản phẩm dùng được tại giường bệnh**.

**Chẩn đoán: đúng nửa TRÌNH TỰ, không đúng nửa CƠ CHẾ.**

- Cơ chế không thừa — mỗi cái mua bằng một lỗi thật đã bắt được: 17 kiểm thử xanh giả ·
  suýt nướng lỗi nghìn lần vào liều carvedilol `3,125` · hai lệnh cổng trượt trên chính
  dữ liệu đúng · cổng dừng thiếu ô cho đúng kết quả đáng sợ nhất.
- Trình tự sai — Chặng A như đã duyệt chạy cả chu kỳ trên **54 khẳng định dựng**, trong
  khi việc Gun thật sự cần (phác đồ cá nhân, thư viện tham khảo) bị hoãn vô hạn.

**Chốt: đảo trình tự, không bỏ cơ chế.** Phác đồ thật đi trước; máy chạy Chặng A trên
chính phác đồ đó thay vì trên dữ liệu dựng.

**Và chốt tiếp: máy soạn nháp, Gun duyệt** — thay vì Gun tự viết từng phác đồ.
Antigravity hỏi NotebookLM trên kho nguồn Gun đã chọn lọc, sinh **bản ghi có toạ độ
nguồn**, Gun duyệt. Đặc tả: `docs/DAC_TA_PHAC_DO_NHAP.md`.

- **Ranh giới quan trọng nhất**: NotebookLM bảo đảm *"câu này dựa trên đoạn kia"* —
  **không** bảo đảm câu đó **giữ nguyên nghĩa** đoạn kia. Nguồn ghi *"7 mg/kg khi có
  adrenaline"* có thể thành *"liều tối đa 7 mg/kg [tr.12]"*: trích dẫn thật, số thật,
  **sai lâm sàng** vì điều kiện bị rơi. Cùng hạng lỗi carvedilol. Nên đầu ra là **ứng
  viên**, bắt buộc qua phép kiểm A0, không phải phác đồ dùng ngay.
- **Đo cổng duyệt trước khi tin nó**: gài 5 lỗi có chủ đích, Gun phải bắt ≥4/5. Bản nháp
  trôi chảy có trích dẫn làm người đọc **dễ gật hơn** — duyệt là phép kiểm yếu hơn tự
  viết, nên phải đo, không giả định.
- **Nói rõ để không kỳ vọng sai**: đây **không** phải tiết kiệm thời gian. Duyệt từng
  khẳng định đối chiếu nguyên văn có thể chậm hơn tự viết. Cái được là **vết bằng
  chứng** — mục đích của cả dự án.
- **Hai tệp sổ notebook + cây Notion KHÔNG vào kho git** (cấu trúc tri thức cá nhân, URL
  riêng, tài khoản). Kho chỉ giữ số đo rút ra.
- **Kiểm chứng**: đo trên tệp thật — 873 notebook · 11.805 tài liệu nguồn · miền gây mê
  35/36 đã liên kết (toàn kho 15%) · chủ đề thí điểm nối được ngay · **nhưng chỉ 112/873
  notebook có URL máy dùng được, và ASRA — nguồn của chủ đề thí điểm — không có trong
  kho.**

---

### 12. Dữ kiện THỊ TRƯỜNG cần loại nguồn thứ ba — sách và hướng dẫn đều không trả lời được
**Chốt ngày**: 2026-09-01 · **Người chốt**: chủ dự án (Gun)

Phát hiện khi chuẩn bị phác đồ #1. Đếm 54 khẳng định ưu tiên 1 của
`local_anesthetics.json` theo **trường cha** — tức theo *bản chất dữ liệu*, không theo
tên lá:

| Số | Trường | Bản chất | Nguồn đúng |
|---:|---|---|---|
| **26** | `concentrations` | **dữ kiện thị trường** — nồng độ nào CÓ BÁN | ⛔ **đăng ký thuốc quốc gia** |
| 14 | `maxDoseMgPerKg` | khuyến cáo lâm sàng | sách / hướng dẫn hội |
| 14 | `absoluteMaxAdult` | khuyến cáo lâm sàng | sách / hướng dẫn hội |

**48% khẳng định chết-người của chủ đề thí điểm không thuộc loại mà cả hệ đang xây để
trả lời.**

Nồng độ lidocaine `[0,5 · 1 · 1,5 · 2 · 4 · 5]` là **danh sách ống thuốc có bán**, không
phải khuyến cáo y khoa. Hỏi NotebookLM trên sách giáo khoa câu *"ở Việt Nam bán nồng độ
nào"* sẽ nhận câu trả lời theo thị trường Mỹ hoặc theo nồng độ *thường dùng* — **có
trích dẫn đầy đủ mà sai ngữ cảnh**. Đúng hạng lỗi cả hệ dựng lên để chặn.

- **Chốt**: `concentrations` **gác lại có tên có lý do**, không hỏi NotebookLM. Chúng
  cần **Luồng S2** — nguồn đăng ký thuốc quốc gia (Cục Quản lý Dược) — là loại nguồn thứ
  ba chưa có trong hệ.
- **Hệ quả rộng hơn**: phân loại **ba luồng** (hằng số lý hoá · dữ kiện thị trường/pháp
  quy · khuyến cáo lâm sàng) từng ghi trong thiết kế nay có **ca thật đầu tiên đo được**.
  Trước đây nó là phân loại trên giấy. *(Ba luồng này nay mang mã `S1/S2/S3`, và có thêm
  `S4` — xem quyết định #13.)*
- **Việc kéo theo**: câu hỏi *"trần liều đúng lâm sàng ở Việt Nam thuộc nguồn quản lý
  dược nào"* — đã nêu ở `docs/BAN_GIAO_CHANG_A.md` A2 — nay không hoãn được nữa; nó
  chặn 26 khẳng định của chính chủ đề thí điểm.
- **Kiểm chứng**: `docs/runs/PHAC_DO_01_doi_chieu.json` khoá phạm vi ở 28, ghi rõ 26 cái
  gác lại và lý do.

---

### 13. Bốn luồng nguồn `S1…S4`, đổ chung MỘT tầng bằng chứng A0
**Chốt ngày**: 2026-09-04 · **Người chốt**: chủ dự án (Gun)

Gun đưa một bộ khung thu thập đa nguồn: nguồn y khoa (SSD · PubMed · Europe PMC) và
nguồn khoa học máy tính (IEEE · arXiv · ACM · DBLP · Papers With Code), quy trình EBM 5A
với PICO ba cấp, cùng năm mô-đun sàng lọc — RoB2 — bóc dữ liệu — phân tích gộp.

Câu hỏi chặn: **bộ máy đó nuôi đích nào?** Chốt: **cả hai, chung một tầng.**

| Mã | Bản chất | Nguồn đúng | Nuôi |
|---|---|---|---|
| `S1` | hằng số lý hoá | dược điển | phép tính liều (H1) |
| `S2` | dữ kiện thị trường / pháp quy | đăng ký thuốc quốc gia | H1 · `LO_TRINH` B1 |
| `S3` | khuyến cáo lâm sàng | đỉnh tháp P5 · nhãn · hướng dẫn hội | H1 · `LO_TRINH` B2 |
| `S4` | **hiệu quả so sánh** | nghiên cứu gốc | bài SR · khuyến cáo chọn thuốc |

- **Chốt**: bộ khung năm mô-đun thuộc **`S4`**, không phải toàn bộ hệ. Mọi luồng đổ vào
  **một tầng chung là A0 `HoSoBangChung`**; AnesthOS đọc tầng đó, **không đọc nguồn**.
- **Hai luận điểm của Claude bị bác, ghi lại để không lặp**: (a) *"không phân tích gộp
  nào sinh ra ngưỡng liều nên `S4` vô dụng với AnesthOS"* — sai, Gun không đòi nó **sinh**
  con số mà đòi nó trả lời **vì sao con số đó là ngưỡng**; (b) *"đỉnh tháp và đáy tháp
  chỉ ngược hướng nhau"* — sai, muốn có đỉnh tháp thì phải có đáy tháp, và
  `docs/QUY_TRINH_5A.md:49-56` đã ghi đúng điều đó từ trước.
- **Ký hiệu**: `S` cấp mới; luồng **không còn** mang mã `A/B/C` vì trùng chặng lộ trình.
  Cùng đợt dọn thêm ba va chạm: `C` (bốn nghĩa) · `Q` · `K`. Xem `QUY_UOC_KY_HIEU.md` §5
  va chạm #5–#7.
- **Chưa gỡ, không thuộc quyết định này**: `S4` cần thư viện số (`scipy`, NetworkX) mà
  **L2 cấm thêm phụ thuộc**. Phải quyết riêng: sửa L2, hay bỏ phân tích gộp khỏi phạm vi.

---

## CHỜ CHỐT

| # | Tên gọi | Vì sao cần chốt |
|---|---|---|
| 8 | **Protocol sửa thì tạo review mới hay sửa tại chỗ** (*mã: D33 Q-1*) | Bất biến nền tảng của schema; sửa sau rất đắt |
| 9 | **Trần lưu giữ kho** (*mã: D33 Q-2*) | SQLite một file, corpus tăng đơn điệu |
| 10 | **Vị trí tài liệu kiểm toán lâm sàng** (*D32 + probe*) | Sau quyết định #1 thì vấn đề này gần như tự tan, xem ghi chú bên dưới |

> Ghi chú mục 10: quyết định #1 đã mở phạm vi y sinh, nên việc D32 và
> `docs/audit/probe_clinical_gaps.py` nằm trong repo SRagent **không còn là vi phạm**.
> Chỉ còn câu hỏi tổ chức thư mục, không còn là câu hỏi tuân thủ.
