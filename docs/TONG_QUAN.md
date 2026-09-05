# Tổng quan — SR-Agent & AnesthOS

> **Vai của tài liệu**: bản đồ + hiện trạng. Đọc tệp này trước, rồi mở đúng tài liệu cần.
> Nó **không chép lại** nội dung tài liệu khác — mỗi mục một dòng trạng thái rồi trỏ đi.
>
> **Mọi con số ở §3 đều kèm lệnh tái lập.** Số không có lệnh là số không kiểm được.
>
> **Cập nhật**: 2026-09-04 · **HEAD**: `478a3c3` · **Nhánh**:
> `claude/sr-agent-architecture-audit-scn4v6`

---

## 1 · Hai hệ, một quan hệ

> ### 「Nói đơn giản」
>
> **SR-Agent sinh ra dữ liệu. AnesthOS dùng dữ liệu đó.** Hai hệ không cạnh tranh — một
> cái làm ra cái kia ăn.
>
> Câu hỏi gốc của cả dự án: *UpToDate chỉ là một nguồn tài liệu — có tin nó để điều trị
> không?* SR-Agent tồn tại để mọi con số trong AnesthOS **truy được về gốc**: ai nói, ở
> dòng nào, dựa trên nghiên cứu nào, và đã lỗi thời chưa.

| | SR-Agent | AnesthOS |
|---|---|---|
| Làm gì | tìm · sàng · thẩm định · gắn xuất xứ | tra cứu tại giường |
| Ngôn ngữ | Python | TypeScript · React · Vite |
| Đầu ra | kho JSON có chữ ký | khuyến cáo kèm độ mạnh + nguồn + điều kiện |
| Kho | `/home/user/SRagent` | `/home/user/AnesthOS-app` |

**Hướng đã chốt** (`DECISIONS.md` #7): SR-Agent **sinh dữ liệu mới có bằng chứng, thay dần
dữ liệu dựng** — *không* đi hướng thẩm định ngược 16.417 khẳng định cũ.

**Ràng buộc cứng**: một người ký duy nhất (Gun), hơn 8 giờ mỗi tuần. Mọi thiết kế phải
sống được với ràng buộc đó, hoặc phải nói rõ là không.

**Chỗ máy không được lấn** (`QUY_TRINH_5A.md` §8): đầu ra đúng của AnesthOS không phải
*"hãy làm X"* mà là *"X, độ mạnh Y, dựa trên Z, áp dụng khi điều kiện W — bác sĩ và người
bệnh quyết"*. Bỏ mất "điều kiện W" là biến công cụ **hỗ trợ** quyết định thành công cụ
**thay thế** quyết định.

---

## 2 · Bản đồ tài liệu — cần gì đọc gì

### Đọc trước, luôn có hiệu lực

| Tài liệu | Trả lời câu hỏi |
|---|---|
| `CLAUDE.md` | luật trả lời (L11) — tự nạp mỗi phiên |
| `KE_HOACH_ANTIGRAVITY.md` §1 | **luật vận hành L1–L11** — được phép làm gì, cấm gì |
| `QUY_UOC_KY_HIEU.md` | ký hiệu nào nghĩa gì; luật cấp mã mới; 7 va chạm đã xảy ra |
| `DECISIONS.md` | 13 quyết định đã chốt — **đừng mở lại** |

### Lộ trình và cơ chế

| Tài liệu | Trả lời câu hỏi |
|---|---|
| `LO_TRINH.md` | đang ở đâu, đi đâu tiếp; 6 câu của trạng thái đích; cổng G1/G2 |
| `SO_CO_CHE.md` | **khi có gì đó sai, xem ở đâu** — 8 cơ chế, mỗi cái có dòng lệnh chẩn đoán |
| `QUY_TRINH_5A.md` | đối chiếu hệ với quy trình EBM 5 bước; chỗ nào máy nên thay người |

### Đặc tả

| Tài liệu | Mã | Nội dung |
|---|---|---|
| `DAC_TA_V1_SO_PHU.md` | `V1` | sổ phụ bằng chứng, bản đầu |
| `DAC_TA_A0.md` | `A0` | lược đồ bằng chứng cấp dòng · vân tay bộ ba · 4 trạng thái đồng thuận · thang mức phủ 4 bậc |
| `DAC_TA_H1_PHEP_TINH_LIEU.md` | `H1` | phép tính liều thuốc tê — khoá tra của từng số hạng |
| `DAC_TA_PHAC_DO_NHAP.md` | — | luồng Antigravity + NotebookLM soạn phác đồ nháp; 4 lỗ đã biết |

### Bản giao việc và lượt chạy

| Tài liệu | Nội dung |
|---|---|
| `BAN_GIAO_CHANG_A.md` | bản giao việc Chặng A — phần lâm sàng + phần kỹ thuật |
| `BAN_GIAO_AG1_V1.md` | giao AG-1 cài đặt, kèm điều cấm `X1…X3` |
| `PHAC_DO_01_THUOC_TE.md` | hồ sơ giao việc phác đồ #1 |
| `runs/PHAC_DO_01_*` | dữ liệu lượt chạy thật đầu tiên |

### ⚠ Lịch sử — đừng đọc như hiện trạng

| Tài liệu | Vì sao |
|---|---|
| `HANDOVER.md` | mô tả SR-Agent là pipeline **khoa học máy tính**, "M0–M3, 75 tests", nhánh khác. Đó là hệ **trước khi xoay sang y khoa**. Giữ vì `M0…M6` khai ở đó |
| `docs/specs/` (7 tệp) | đặc tả các đợt cũ `D30…D33`, `TS-·` — không cấp thêm mã |
| `BAN_GIAO_PHIEN_SSD.md` | phiên làm việc cũ |

---

## 3 · Hiện trạng đo được

Chi tiết dữ liệu AnesthOS ở `LO_TRINH.md` §2 — mục này chỉ giữ số tổng và **lệnh tái lập**.

### SR-Agent

| Hạng mục | Số đo | Lệnh |
|---|---|---|
| Mã công cụ | **27** tệp | `ls tools/*.py tools/*/*.py \| wc -l` |
| Mã lõi | **30** tệp | `find sr_agent -name '*.py' \| wc -l` |
| Tệp kiểm thử | **40** | `ls tests/test_*.py \| wc -l` |
| Kiểm thử | **100 đỏ · 652 xanh** | `python3 -m pytest 2>&1 \| tail -1` |
| Phụ thuộc | 7 gói, **không được thêm** (L2) | `pyproject.toml` |

> **100 ca đỏ nằm đúng HAI tệp** — đây là đường ranh, không phải con số suông:
>
> | Tệp | Số ca đỏ |
> |---|---|
> | `tests/test_a0_bang_chung.py` | **94** |
> | `tests/test_so_phu_bang_chung.py` | **6** |
>
> ```
> python3 -m pytest -q 2>&1 | grep "^FAILED" | sed 's/::.*//' | sort | uniq -c
> ```
>
> Cả 100 ca là **kiểm thử viết trước khi có mã**, chờ AG-1 cài `A0` — đỏ **có chủ đích**.
> **Bất kỳ ca đỏ nào ngoài hai tệp đó là tín hiệu mới**, phải xem ngay. Không có ranh giới
> này thì "100 → 100" chỉ là một hằng số không ai kiểm được nguồn gốc.

### AnesthOS

| Hạng mục | Số đo |
|---|---|
| Nhánh dữ liệu thật | `origin/feat/p1-domain` — **52** tệp |
| Dữ liệu miền | **23** tệp JSON trong `src/domain/data/` |
| Calculator | **1** — `src/domain/calculators/ibw.ts` (Devine 1974, kèm ABW) |
| Kiểm thử | **28** ca (domain 9 · clinical_data 13 · boundary 6) |
| Khẳng định lâm sàng | **16.417** · ưu tiên 1: **2.271** |
| Mức phủ bằng chứng | **100%** ở bậc thấp nhất — *"chỉ có nguồn cấp tệp"* |

> **Chính kho AnesthOS tự khai dữ liệu là dựng.** `provenance_manifest.json` ghi
> `"synthetic": true` và `"dataGovernancePolicy": "SYNTHETIC_MOCK_NO_PHI"`. Đó là nền
> trung thực để bắt đầu — và là lý do hướng đã chốt là **thay dần**, không phải kiểm ngược.

---

## 4 · Đã thiết kế gì — trạng thái từng phần

### Chặng A (`LO_TRINH.md` §5.1)

| Mã | Việc | Trạng thái |
|---|---|---|
| `A‑0` | đưa lộ trình vào kho, sửa `EF2`, sửa cổng M6 | **✓ xong** |
| `A0` | lược đồ bằng chứng cấp dòng | **đặc tả xong + 100 kiểm thử đỏ — chờ AG-1 cài** |
| `A3a` | cửa `/references` mức tối thiểu | ○ chưa bắt đầu |
| `A1` | **đo tỷ lệ đo được độc lập** — bước quan trọng nhất, quyết cổng `G1` | ○ |
| `A2` | kiểm biên, đối chiếu trần nhãn | ○ |
| `A3` | `tham_khao.py` — phả hệ cấp khẳng định | ○ |
| `A4` | đo độ nhạy truy vấn | ○ |

Chặng B (chạy thử thuốc tê, `B1…B6`) và Chặng C (`C0…C3`) **chưa bắt đầu**.

### Thiết kế ngoài lộ trình bước

| Thiết kế | Ở đâu | Nội dung một dòng |
|---|---|---|
| **Luật L1–L11** | `KE_HOACH_ANTIGRAVITY.md` §1 | không làm xanh giả · vùng cấm · ba trạng thái · Critic bắt buộc · luật trả lời |
| **Sổ ký hiệu** | `QUY_UOC_KY_HIEU.md` | một chữ một nghĩa vĩnh viễn; 7 va chạm thật ghi làm chứng cứ |
| **4 luồng nguồn `S1…S4`** | `QUY_UOC_KY_HIEU.md` §3.1 · `DECISIONS.md` #13 | bản chất dữ kiện quyết loại nguồn; cả 4 đổ vào **một tầng chung A0** |
| **Luồng phác đồ** | `DAC_TA_PHAC_DO_NHAP.md` | máy soạn nháp từ NotebookLM, Gun duyệt; 4 lỗ đã biết + ca đối chứng `K3` |
| **`H1` phép tính liều** | `DAC_TA_H1_PHEP_TINH_LIEU.md` | khoá tra của từng số hạng, chốt **trước** khi `B4` sinh v2 |
| **Câu 6 của trạng thái đích** | `LO_TRINH.md` §3 | *vì sao ngưỡng là con số này* — A0 chưa có ô chở |

### Ba cơ chế vừa sửa (2026-09-04)

Cả ba cùng một hình dạng: **bản đồ mô tả một tầng bảo vệ không có trên đường chạy**.

| Cơ chế | Hỏng thế nào | Nay |
|---|---|---|
| Tường lửa số `[8]` | không đường chạy sản xuất nào gọi | `tools/kiem_ban_ghi_phac_do.py` — có lệnh chạy, ba trạng thái |
| Sơ đồ PRISMA | hỏi tên sự kiện **không ai ghi** → nhánh dự phòng luôn trả 0 | đếm đúng tên; không đo được thì kêu **VÔ HIỆU** |
| Chống trùng `D34` | tầng 1 không đọc `alternate_uids` | đọc rồi — hai bản của một bài không còn thành hai nguồn |

---

## 5 · Lượt chạy thật đầu tiên — phác đồ #1 thuốc tê

Antigravity + NotebookLM, một notebook chính, ngày 2026-09-02. Kết quả ở
`docs/runs/PHAC_DO_01_*`.

| Số đo | Giá trị |
|---|---|
| Bản ghi nộp | **36** |
| Mã đối chiếu | 25 — **25 mã phân biệt, 0 mã trùng** |
| Tường lửa số | **ĐẠT 31 · TRƯỢT 0 · VÔ HIỆU 5** |
| Điểm quyết định không trả lời được | 3, có nộp kèm |

```
python3 tools/kiem_ban_ghi_phac_do.py docs/runs/PHAC_DO_01_ban_ghi.json
```

### Nó chứng minh gì — và KHÔNG chứng minh gì

| Đọc được | Không đọc được |
|---|---|
| máy lấy được nguyên văn kèm số, không bịa từ trí nhớ | **không** nghĩa là bóc đúng: `don_vi` chưa bao giờ được dùng |
| 31 con số có mặt trong nguyên văn của chính nó | đảo `5` ↔ `7` giữa hai bản ghi **dùng chung một nguyên văn** thì cả hai vẫn ĐẠT |
| 5 khẳng định bằng chữ không neo được — hiện rõ, không bị giấu | `nguon.trang` **null 36/36** → phép kiểm `K1` **TRƯỢT** |

**Ba việc còn tồn từ lượt này:**

- **25 mã phân biệt, 0 mã trùng.** Chạy `A1` trên bộ này thì mọi khẳng định ra `MOT_NGUON`
  và cổng `G1` ra DỪNG — vì **thói quen bóc tách "mỗi trường một nguồn"**, không phải vì
  nền y văn hẹp. Phải hiệu chuẩn công cụ trước khi đọc kết quả như kết luận.
- **`lidocaine 3 mg/kg / 200 mg`** nằm sờ sờ trong nguyên văn `Table 5.2` đã trích nhưng
  **chưa bao giờ thành bản ghi** — trong khi điều cấm `X3` cấm bỏ bản ghi vì mâu thuẫn.
  Nghĩa là con số 3,0 mà cổng `G2` dựa vào hiện **không có bản ghi nào chống lưng**.
- **12.145 ký tự nguyên văn nguồn thương mại** (UpToDate ×5 bài, Hadzic's, Textbook of
  Anaesthesia, Morgan & Mikhail's, Stoelting's) đang nằm trong git, vi phạm điều cấm `X4`.

---

## 6 · Đang mở — chờ quyết

| # | Việc | Vì sao chặn |
|---|---|---|
| 1 | **Ngoại lệ L2** cho `sr_agent/pipeline.py` | trùng lặp tầng 1 không được ghi sự kiện; chỉ mục `alternate_uids` chiều ngược. Cả hai đã có kiểm thử ghi vết |
| 2 | **L2 vs thư viện số** | luồng `S4` và `DECISIONS.md` #4/#9 cần `scipy`/NetworkX, mà L2 cấm thêm phụ thuộc. Sửa luật, hay bỏ phân tích gộp khỏi phạm vi |
| 3 | **Gỡ 12.145 ký tự bản quyền** | gỡ trước thì mất căn cứ cho `H1.Đ2`; nạp trước thì kéo dài vi phạm |
| 4 | **Cài `A0`** (AG-1) | cây đỏ 100 ca qua 12 commit, trong khi `L6` nói đỏ quá một commit là hỏng thật. Chặn `A3a` và `A1` |

---

## 7 · Chế độ hỏng của chính quy trình làm việc

Ghi lại vì nó **lặp năm lần trong một phiên**, cùng một nguyên nhân: **phản biện trước khi
đọc kho**.

| # | Đã khẳng định là thiếu | Thực tế đã có ở |
|---|---|---|
| 1 | "thiếu phép đo recall của chiến lược tìm kiếm" | `tools/do_nhay.py` · `SO_CO_CHE.md` §1 — **đã hỏng thật 2 lần** |
| 2 | "brainstorm 5A đang đặc tả lại thứ đã có" (nói mà chưa đọc) | `QUY_TRINH_5A.md` — đã làm đúng phân tích đó từ trước |
| 3 | "đỉnh tháp và đáy tháp chỉ ngược hướng nhau" | `QUY_TRINH_5A.md` §2.1 — đỉnh tháp là **lớp dẫn đường**, kết luận ngược lại |
| 4 | dùng dải cân nặng 66,7–80 kg làm bằng chứng | `LO_TRINH.md` §9 — phép đo đó **đã chạy và đã bị bác**: không có sức phân biệt |
| 5 | "`H1`: IBW chưa có, hoãn chọn công thức" | `src/domain/calculators/ibw.ts` — **đã có** Devine 1974, xuất xứ đầy đủ, **và cả ABW** |

**Cách chặn**: trước khi khẳng định một cơ chế còn thiếu, chạy

```
grep -rn "<tên cơ chế>" docs/SO_CO_CHE.md docs/QUY_TRINH_5A.md docs/LO_TRINH.md
```

Cùng tinh thần với `L7` — in nguồn dữ liệu trước mọi con số.

> ### 「Nói đơn giản」
>
> Năm lần đều giống nhau: chẩn đoán trước khi xem hồ sơ cũ của bệnh nhân. Bệnh nhân **đã
> làm** xét nghiệm đó rồi, kết quả nằm trong bệnh án — chỉ định lại vừa tốn tiền vừa làm
> chậm điều trị. Tệ hơn: có lần kết quả cũ đã **kết luận ngược lại**, và chẩn đoán mới ghi
> đè lên mà không ai đối chiếu.
