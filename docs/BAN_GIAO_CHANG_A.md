# Bản giao việc — CHẶNG A

> **Vì sao có tài liệu này.** Bản giao việc trước chỉ nằm ở tệp kế hoạch của phiên làm
> việc. Tệp đó **chết theo phiên** và tác nhân khác không đọc được — đúng hỏng mà
> `docs/DECISIONS.md` được lập ra để chặn: *"đã chốt rồi mà không tìm lại được"*.
>
> **Phần I** — cơ chế bằng ngôn ngữ lâm sàng, cho người ký duyệt.
> **Phần II** — bản giao việc kỹ thuật, cho đội thực hiện.
>
> Tài liệu nói **đích cần tới** và **cách biết đã tới hay chưa**. Nó **không** nói làm
> bằng cách nào — đó là việc của vai PHÂN TÍCH.
>
> **Đã qua hai vòng phản biện độc lập** (luật L10). Vòng hai bắt được 11 lỗi, trong đó
> có hai lệnh cổng môi trường **trượt trên chính dữ liệu đúng**, và một cổng dừng chỉ
> có 2 ô cho phép đo ra 4 kết quả.
>
> **Cập nhật**: 2026-09-01 · **Nền**: `12bbb47`

---
---

# PHẦN I — CƠ CHẾ, BẰNG NGÔN NGỮ LÂM SÀNG

## 1 · Chặng A là gì

> **Một nghiên cứu khả thi, chạy trước chương trình chính.**

Chương trình chính — đã chốt từ trước, không mở lại: SR-Agent **sinh dữ liệu mới có bằng
chứng, thay dần dữ liệu dựng** của AnesthOS. Không đi thẩm định ngược 16.417 khẳng định
cũ; chúng chỉ còn giá trị làm **danh sách đích** — cho biết cần tìm bằng chứng cho
*trường nào*.

Hiện trạng đo được, nói cho chính xác: 2.271 khẳng định chết-người hiện **chưa truy
được tới nghiên cứu gốc** — mỗi cái mới chỉ có tên sách cấp tệp, kiểu "theo Stoelting".
(*Không* phải "không có gì" — hai trạng thái đó khác nhau, và trộn chúng chính là lỗi
từng đảo ngược kết luận của một lượt nghiệm thu trước đây.)

Cả chương trình đứng trên **một giả định chưa kiểm**: khi hai nguồn cùng nói một con
số, ta **đo được** chúng có độc lập không — hay chỉ là một nguồn chép hai lần, như hai
bác sĩ đồng ý nhau vì cùng học một thầy. Chặng A kiểm giả định đó trước khi xây tiếp.

## 2 · Sáu việc, thứ tự và lý do

| | Việc | Đối chiếu lâm sàng |
|---|---|---|
| **A0** | Dựng biểu mẫu ghi bằng chứng | thiết kế **phiếu thu thập số liệu** trước ca đầu |
| **A3a** | Nối cửa lấy danh mục tham khảo | **lắp đầu dò** trước khi đo — không có nó thì A1 không có dữ liệu vào |
| **A1** | Đo: tính độc lập của nguồn có đo được không | **nghiên cứu khả thi** về tiêu chí chính |
| **A2** | Đối chiếu liều với trần nhãn thuốc | **sàng lọc rẻ** — điều dưỡng bắt y lệnh 50 mg morphin tĩnh mạch: không cần hội chẩn mới biết sai |
| **A3** | Truy phả hệ đủ nhiều chặng | dựng **bộ xét nghiệm** hoàn chỉnh cho tiêu chí chính |
| **A4** | Đo độ nhạy phép tìm y văn | đo **độ nhạy của xét nghiệm sàng lọc** |

A2 độc lập với mô hình ký — **dù G1 ra dừng hay đi tiếp, A2 vẫn chạy**.

## 3 · Cổng G1 — quy tắc dừng đặt trước, đủ kín

Phép đo A1 xếp 54 khẳng định vào **bốn** nhóm. Quy tắc dừng phải có ô cho **cả bốn** —
định trước, không nghĩ tiếp sau khi thấy số:

| Kết quả trội (≥28/54) | Nghĩa lâm sàng | Đi tiếp thế nào |
|---|---|---|
| **ĐỘC LẬP** | hai nguồn thật sự là hai bằng chứng | mô hình một-người-ký đứng được → chạy Chặng B |
| **CHUNG TỔ TIÊN** | đo được, nhưng các nguồn cùng chép một gốc — nền bằng chứng thật **hẹp hơn vẻ ngoài** | đối chiếu chéo **không thay được** người ký thứ hai → DỪNG, thiết kế lại mức ký; cân nhắc hội chẩn ngoài cho nhóm này |
| **KHÔNG ĐO ĐƯỢC ĐỘC LẬP** | nguồn không khai nó dẫn từ đâu | như trên — DỪNG, thiết kế lại |
| **MỘT NGUỒN** | chỉ tìm được một nguồn | như trên, kèm câu hỏi riêng: vì sao y văn mỏng ở đây? |
| *(không nhóm nào ≥28)* | bức tranh trộn | **coi như DỪNG** — không đủ căn cứ đi tiếp là dừng, không phải đi |

**Ai quyết:** Gun. Đội chỉ nộp bảng phân bố + danh sách đích danh từng nhóm. Ngưỡng 28
là đa số chặt của 54; mọi ca sát ngưỡng đều đưa Gun kèm số thô.

> Dừng ở G1 **không phải thất bại** — là kết quả đúng của nghiên cứu khả thi. Biết sớm
> tiêu chí chính không đo được thì còn kịp đổi thiết kế.

## 4 · Ba trạng thái — và một chỗ dễ trộn tên

Mọi phép đo trả về **ĐẠT / TRƯỢT / VÔ HIỆU**. *Vô hiệu* = phép đo hỏng, không đủ căn
cứ kết luận — **mẫu bệnh phẩm hỏng không được trả "âm tính"**, phải trả "xin mẫu lại".

⚠ Đừng trộn với `KHONG_DO_DUOC_DOC_LAP`: đó là một **kết quả đo hợp lệ** ở cấp từng
khẳng định ("nguồn này không khai gốc"), nằm **bên trong** một lượt đo ĐẠT. Còn VÔ HIỆU
là cấp **cả bước** — máy hỏng, làm lại. Hai tầng khác nhau, chữ gần giống nhau.

## 5 · Quỹ giờ của Gun — trần, không phải hứa hẹn

Ràng buộc đã chốt: Gun có **trên 8 giờ/tuần**. Thiết kế mỗi bước phải nằm dưới trần đó:

| Bước | Việc của Gun | Trần giờ |
|---|---|---|
| A0 | ký kết quả nghiệm thu | ~0,5 giờ |
| A1 + G1 | đọc xác suất ~10/54 phả hệ · quyết định cổng | ~3 giờ |
| A2 | duyệt danh sách vượt trần **theo lớp** · quyết câu hỏi thị trường VN | ~2 giờ |
| A4 | duyệt tập chuẩn | ~1 giờ |

Vượt trần → dừng và báo lại, không lặng lẽ ăn thêm giờ.

---
---

# PHẦN II — BẢN GIAO VIỆC KỸ THUẬT

## 6 · Cơ cấu đội

| Vai | Được làm | **Cấm** |
|---|---|---|
| **PHÂN TÍCH** | từ bản này → đặc tả + tiêu chí từng bước; **điều phối** câu hỏi của PHẢN BIỆN về đúng vai | viết mã; tự chạy nghiệm thu; **tự xử câu hỏi nhắm vào sản phẩm của chính mình** (chuyển Claude) |
| **THỰC HIỆN · kiểm thử** | kiểm thử **từ đặc tả, trước khi có mã** (commit đỏ theo ngoại lệ L6); viết `scripts/nghiem_thu_*.sh` | đọc mã của người cài đặt; chạm `tools/**` |
| **THỰC HIỆN · mã** | mã cho kiểm thử xanh | chạm `tests/**`, `scripts/nghiem_thu_*`; **dò ngược số nghiệm thu** |
| **NGHIỆM THU** | chạy script nghiệm thu **trên mã đã commit**, ghi kết quả vào `docs/runs/**` | sửa bất cứ gì ngoài `docs/runs/**` |
| **PHẢN BIỆN** | đọc, **chỉ đặt câu hỏi** kèm bằng chứng `tệp:dòng` hoặc số tự đo | sửa tệp; đề xuất bản sửa; viết lời khen |
| **Claude** | kiểm định cuối, **tự tính lại số bằng đường riêng**; phân xử bất đồng | — |
| **Gun** | quyết G1, phân xử số lệch, ký lâm sàng | — |

**PHẢN BIỆN chen vào 2 điểm cố định mỗi bước** — sau khi có đặc tả + kiểm thử (trước
khi cài), và sau khi cài xong (trước khi nộp Claude/Gun). Không bước nào được nhảy cóc.

**Kết quả đo sống ở `docs/runs/A<bước>_*.{md,json}`** — bản `.json` máy đọc lại được,
bản `.md` người đọc. Chỉ vai NGHIỆM THU được ghi vùng này.

## 7 · Tám ràng buộc cứng — không thương lượng

| # | Ràng buộc |
|---|---|
| **1** | **Số không đi qua mô hình ngôn ngữ.** Giá trị lâm sàng phải **chép** từ nguồn; mô hình ngôn ngữ chỉ **định vị**. Áp cho cả **mã định danh** (PMID/DOI): mọi mục phả hệ phải kèm **trích nguyên văn chuỗi trích dẫn** qua được `verify_quote()` — mã số không truy được nguyên văn thì không được ghi |
| **2** | **Ba trạng thái.** ĐẠT / TRƯỢT / VÔ HIỆU. Vô hiệu ≠ đạt |
| **3** | **Rẻ trước, đắt sau.** Bước tất định chạy trước bước mô hình ngôn ngữ |
| **4** | **Không ai chấm bài mình.** Kiểm thử trước mã, bởi người khác; nghiệm thu bởi vai không viết mã |
| **5** | **Không tự khai.** Chỉ số chất lượng phải tính ra, không có ô điền tay |
| **6** | **Không thêm phụ thuộc.** `pydantic` + `httpx` + thư viện chuẩn; `pyproject.toml`, `sr_agent/ingest/`, `sr_agent/pipeline.py` là vùng cấm |
| **7** | **Nghiệm thu in nguồn dữ liệu trước mọi con số.** Thiếu `provenance_manifest.json` → DỪNG. Lỗi mạng = TRƯỢT, không phải bỏ qua |
| **8** | **Bản quyền trích dẫn.** Trích nguyên văn từ nguồn **công vụ Mỹ** (nhãn FDA/DailyMed — public domain) được lưu trong kho. Từ nguồn **thương mại** (UpToDate, Stoelting): kho chỉ lưu *toạ độ + băm của đoạn trích + độ dài* — muốn tái kiểm phải có quyền truy cập nguồn tại chỗ. Tiền lệ đã có: T0 cấm commit văn bản UpToDate |

## 8 · Các bước — đích, và cách biết đạt / trượt / vô hiệu

### A0 · Biểu mẫu bằng chứng cấp dòng

Đặc tả + **100 kiểm thử đỏ** đã sẵn tại `12bbb47`. Còn hai việc: vá một chốt kiểm thử
hở (xem dưới) và viết mã.

**Vá trước khi cài** (vai kiểm thử, sửa có căn cứ theo L1): chốt canh L7 tại
`tests/test_a0_bang_chung.py` có cửa thoát `or "1" in ...` — PHẢN BIỆN đã mô phỏng một
cài đặt in số trước nguồn dữ liệu mà vẫn qua. Vá thành: **không một chữ số nào xuất
hiện trước đường dẫn nguồn**.

| | Điều kiện |
|---|---|
| **ĐẠT** | 734+ kiểm thử xanh · Đ1–Đ6, Đ7a, Đ8 khớp · `git diff 12bbb47 --name-only` ra **đúng 2 tệp**: `tools/so_phu_bang_chung.py` (vai mã) và `scripts/nghiem_thu_a0.sh` (vai kiểm thử) · `bash scripts/gate_m6.sh` qua |
| **TRƯỢT** | kiểm thử đỏ · **Đ2/Đ3 khác 0** · `tests/**` bị vai mã sửa |
| **VÔ HIỆU** | không bày được dữ liệu AnesthOS → báo đúng vậy |

**Đ7 sau phân xử sơ bộ:** hai phép đếm độc lập cùng ra **P1 = 1.630** → **Đ7a = 1.630
là cổng chặn**. Đ7-tổng lệch (Claude 4.016 · PHẢN BIỆN 4.092) — nghi do khác **tập
đếm** (có loại 3.862 lá nhãn ra trước không). Chốt định nghĩa: *đếm trên 16.417 khẳng
định lâm sàng, sau khi loại lá nhãn*. Đội đo theo định nghĩa đó; vẫn lệch → nộp Gun cả
hai số kèm khoá đếm khác nhau, **không chặn A0**.

### A3a · Nối cửa danh mục tham khảo (kéo lên trước A1)

**Đích:** với một bài có PMID, lấy được danh mục tham khảo qua Europe PMC
`/references`. Tối thiểu đủ cho A1 — chưa cần nhiều chặng.

| | Điều kiện |
|---|---|
| **ĐẠT** | với bài kiểm chứng đã biết trước danh mục: trả về **đúng và đủ** các mã |
| **TRƯỢT** | thiếu/thừa mã so với danh mục đã biết |
| **VÔ HIỆU** | Europe PMC không với tới từ môi trường chạy → **báo dừng cả A1**, vì A1 mất dữ liệu vào |

### A1 · Đo tỷ lệ đo-được-độc-lập — bước quan trọng nhất

**Đích:** với **54 khẳng định P1 trong `local_anesthetics.json` (bản EN — ghi rõ tệp,
vì bản `_vi` trùng byte cũng có 54)**: mỗi cái xếp vào 1 trong 4 trạng thái đồng thuận.

**Quy trình đo** (khung, đội chi tiết hoá): nguồn ứng viên của mỗi khẳng định = hướng
dẫn hội (cấp tệp đã khai: ASRA) + nhãn thuốc. Phả hệ lấy **tại chỗ nêu con số**; mỗi
mục phả hệ kèm trích nguyên văn (ràng buộc 1). Nhãn không khai tham khảo →
`KHONG_DO_DUOC_DOC_LAP` — **đó là dữ liệu, không phải thất bại**; đo ra toàn trạng thái
đó chính là điều A1 sinh ra để phát hiện.

**Kiểm rẻ kèm theo:** khẳng định `local_anesthetics.json ≡ local_anesthetics_info_vi.json`
(hiện trùng 100%) thành một kiểm thử tất định — bản dịch lệch một con số là một khẳng
định P1 chưa ai đo.

| | Điều kiện |
|---|---|
| **ĐẠT** | đủ 54, tổng đúng 54 · mỗi xếp loại truy được tới tài liệu + vị trí + trích nguyên văn · xếp `DOC_LAP` phải trưng phả hệ **cả hai** nguồn · **kết quả xấu mà đo đúng vẫn là ĐẠT** |
| **TRƯỢT** | tổng ≠ 54 · xếp loại không truy được · `DOC_LAP` thiếu phả hệ một bên |
| **VÔ HIỆU** | không lấy được nguồn (mạng/quyền) → ghi rõ từng ca |

**→ Cổng G1** — bảng 4+1 hàng ở §3. Đội nộp số; **Gun quyết**.

### A2 · Kiểm biên liều — chạy bất kể G1

**Sửa phạm vi (PHẢN BIỆN C3):** nhãn cũ "1.492 khẳng định liều" **sai** — ~34% trong đó
là `route`/`weightBasis`/`periop` (không có số để so trần), trong khi liều thật ở
`local_anesthetics` (54 — có ca lidocaine 4,5), `nora_locations`, `crisis_protocols`
nằm ngoài. Đây đúng lỗi "đặt nhãn trước khi đo".

**A2.0 — đo phạm vi trước khi chạy:** phạm vi = *mọi khẳng định P1 **chứa chữ số** thuộc
khoá nhóm-liều* (`dose`, `smartDose`, `max`, `maxDoseMgPerKg`, `absoluteMaxAdult`,
`plain`, `withEpi`, `concentrations`, …) trên **toàn bộ 22 tệp**. In con số + phân rã
theo tệp trước khi đối chiếu. Khẳng định P1 không-số **loại có tên có lý do** (kiểm từ
vựng — việc Chặng B), không bỏ im lặng.

**A2.1 — mở một tệp SPL thật trước khi xây:** giả định "trần liều nằm trong trường có
cấu trúc của DailyMed" **chưa ai kiểm** (môi trường soạn bài này bị chặn DailyMed —
403). Việc đầu tiên: tải một SPL thật, xác nhận trần nằm ở đâu. Nếu là văn xuôi trong
XML → báo lại Claude, độ khó cả bước đổi.

| | Điều kiện |
|---|---|
| **ĐẠT** | mỗi khẳng định trong phạm-vi-đã-đo có một kết quả · vượt trần liệt kê **đích danh** kèm trần + nguồn trần · **ca đối chứng dương cài sẵn** (một liều cố ý vượt trần kiểu "morphin 50 mg IV") **bị bắt** |
| **TRƯỢT** | bỏ qua im lặng · báo phần trăm không kèm danh sách · **ca đối chứng dương lọt** |
| **VÔ HIỆU** | tỷ lệ "không tìm được nhãn" cao tới mức phép đo mất nghĩa (kể cả **100% không-đo-được** — một lượt chạy như vậy thoả chữ nhưng vô nghĩa, phải khai VÔ HIỆU, không khai ĐẠT) |

> **Tìm ra vượt trần thì ĐỪNG sửa lẻ** — mỗi chỗ là một mẫu về cách bộ dữ liệu hỏng;
> ghi hết, tìm quy luật, sửa theo lớp.
>
> **Câu hỏi thị trường cho Gun:** DailyMed là trần **Mỹ**; ứng dụng dùng ở Việt Nam thì
> trần đúng lâm sàng thuộc nguồn quản lý dược nào? A2 bản đầu dùng nhãn Mỹ làm **chặn
> thô có khai rõ nguồn**, không làm chân lý.

### A3 · Phả hệ nhiều chặng

| | Điều kiện |
|---|---|
| **ĐẠT** | một con số → bài gốc của **từng** nguồn · bắt chung tổ tiên **≥2 chặng** · có ca dựng sẵn 3 chặng · nguồn không khai tham khảo → `KHONG_DO_DUOC`, không suy đoán |
| **TRƯỢT** | đo trùng lặp **cấp tài liệu** thay vì cấp khẳng định · báo `DOC_LAP` khi một nguồn không có danh mục |
| **VÔ HIỆU** | Europe PMC không với tới |

Thư viện đồ thị chỉ thêm **nếu A1 chứng minh phả hệ nhiều chặng có thật**; không thì
phép giao tập hợp thuần.

### A4 · Độ nhạy phép tìm — đo và cổng tách nhau

| | Điều kiện |
|---|---|
| **ĐẠT** (*phép đo hợp lệ*) | mỗi bài tập chuẩn có phán quyết tìm-thấy / **sót (đích danh mã)** · tập chuẩn phân giải được · **3 bài sót mà báo đúng tên vẫn là ĐẠT** |
| **TRƯỢT** | báo phần trăm không tên bài · **sửa truy vấn sau khi thấy bài sót** (uốn phép đo theo đáp án) |
| **VÔ HIỆU** | tập chuẩn không phân giải được |

**Cổng kết quả (tách khỏi ĐẠT):** 0 sót → phép tìm đạt chuẩn, khoá truy vấn. Có sót →
một vòng sửa cần **tập chuẩn mới** (nguồn: danh mục tham khảo bài tổng hợp từ T0 —
kho có sẵn bao nhiêu dùng bấy nhiêu, hết thì báo). **Trần 2 vòng sửa** — chưa 0 sót
sau 2 vòng thì nộp Gun quyết, không tự lặp vô hạn.

**Cấm:** dùng nguồn tổng hợp ngoài làm **bộ sàng** — nó chỉ làm **đề thi**.

## 9 · Claude kiểm định cuối

| Kiểm | Đạt khi |
|---|---|
| Kiểm thử | xanh, **số chỉ tăng** |
| Vai | `git diff --name-only` từng commit khớp vai người tạo |
| Cổng | `bash scripts/gate_m6.sh` qua |
| Số | tôi **tự tính lại bằng đường riêng** rồi đối chiếu `docs/runs/**` |
| **Ca âm tính L8** | nghiệm thu trên thư mục thiếu manifest → DỪNG |
| **Ca âm tính L7** | cài đặt in số trước nguồn → kiểm thử **phải đỏ** (sau khi vá cửa thoát) |
| **Ca đối chứng A2** | liều cố ý vượt trần → **phải bị bắt** |

Số lệch = **bất đồng thật** → Gun, kèm chỗ đếm khác. Không bên nào tự sửa cho khớp.

## 10 · Môi trường — cổng vào, sửa theo C6

```bash
cd /home/user/SRagent
git pull --ff-only origin claude/sr-agent-architecture-audit-scn4v6   # → 12bbb47
pip install -e ".[dev]"       # kéo ĐỦ 7 phụ thuộc runtime + pytest/respx
python3 -m pytest 2>&1 | tail -1        # PHẢI: 100 failed, 634 passed
```

Chỉ `pip install pytest respx` là **không đủ** — môi trường dựng lại thiếu cả 7 phụ
thuộc runtime, pytest sẽ chết ngay lúc thu thập (29 lỗi), không ra mốc 100/634.

```bash
git -C /home/user/AnesthOS-app ls-tree -r --name-only origin/feat/p1-domain \
  | grep 'domain/data/.*\.json$' | wc -l          # PHẢI: 23
```

Lệnh cũ thiếu `\.json$` nên bắt 25 dòng (dính `index.ts`, `types.ts`) — **trượt trên dữ
liệu đúng**. Cùng lỗi nằm trong `docs/LO_TRINH.md` §7 và `docs/DAC_TA_A0.md` §4 → sửa
hai chỗ đó khi được duyệt.

**Cổng mạng (mới — C11.4):** trước khi chạy A2/A3, môi trường của đội phải với tới
Europe PMC và DailyMed (môi trường soạn bài này: Europe PMC ✓, DailyMed **403**). Không
với tới → bước tương ứng **VÔ HIỆU theo cấu tạo** — biết trước, đừng để đội phát hiện
giữa chừng.

## 11 · Đội phải đọc

`docs/LO_TRINH.md` · `docs/DAC_TA_A0.md` · `docs/KE_HOACH_ANTIGRAVITY.md` §1 (L1–L10) ·
`docs/QUY_UOC_KY_HIEU.md` · `docs/DECISIONS.md` (đã chốt — đừng mở lại)

## 12 · Việc sửa kho ngay khi duyệt (trước khi giao đội)

| Tệp | Sửa |
|---|---|
| `tests/test_a0_bang_chung.py` | vá cửa thoát chốt L7 (vai kiểm thử, căn cứ C9) |
| `docs/LO_TRINH.md` §7, `docs/DAC_TA_A0.md` §4 | lệnh grep thêm `\.json$` (C6) |
| `docs/DAC_TA_A0.md` Đ7 | ghi định nghĩa tập đếm + bất đồng 4.016/4.092 chờ Gun (C7) |
| `docs/LO_TRINH.md` §5.1 | chèn A3a trước A1; G1 bảng 4+1 hàng (C1, C2) |
