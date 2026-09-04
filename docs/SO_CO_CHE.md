# Sổ cơ chế vận hành SR-Agent

> **Bản gốc**: `docs/SO_CO_CHE.md` trong kho SRagent, nhánh `claude/sr-agent-architecture-audit-scn4v6`.
> Bản trên Drive là bản **đọc**, có thể cũ hơn. Sửa thì sửa ở kho.
> **Cập nhật**: 2026-08-24

Sổ này **không** giải thích vì sao thiết kế như vậy (chỗ đó là `docs/DECISIONS.md`).
Nó trả lời đúng một câu hỏi: **khi có gì đó sai, xem ở đâu.**

Mỗi cơ chế ghi năm mục: nó làm gì · phụ thuộc gì · hỏng kiểu nào · dấu hiệu ·
xem ở đâu. Mục **dấu hiệu** là mục quan trọng nhất — vì hỏng có dấu hiệu thì
sửa được, hỏng im lặng thì không.

---

## Bản đồ một phút

```
truy vấn ──▶ [1] đo độ nhạy ──▶ [2] quét cả kho ──▶ [3] xếp bậc chứng cứ
                   │ trượt                                │
                   ▼                                      ▼
              [4] soi truy vấn                       kho .json
                                                          │
Spark ──▶ [5] hàng đợi Drive ──▶ [6] cổng 3 tầng ─────────┤
                                                          ▼
                                                   [7] sàng lọc (CHƯA CÓ)
                                                          │
                                                          ▼
                                              [8] tường lửa số ──▶ AnesthOS
```

---

## [1] Đo độ nhạy bằng bài mồi

| | |
|---|---|
| **Làm gì** | Hỏi nguồn 4 bài nền tảng đã biết chắc có thật. Sót bài nào là **chặn cả lần quét**. |
| **Phụ thuộc** | Mạng tới Europe PMC · `tools/do_nhay.py` · danh sách `MOI_CHONG_DONG` |
| **Hỏng kiểu nào** | Truy vấn sai cú pháp → sót hết. Truy vấn quá hẹp → sót vài bài. Mạng lỗi → tính là **sót**, không phải bỏ qua. |
| **Dấu hiệu** | `Bài mồi lôi về được : 0/4` hoặc `2/4` |
| **Xem ở đâu** | `tools/do_nhay.py` · chạy `tools/soi_truy_van.py` để biết mệnh đề nào hỏng |

**Đã hỏng thật 2 lần.** Lần 1: `MESH:` đúng cú pháp nhưng không lôi được bài mồi.
Lần 2: hai đoạn mã dựng truy vấn khác nhau nên hai phép đo cãi nhau (0/4 vs 4/4).

> ⚠️ **Chỉ có MỘT chỗ được dựng câu dò bài mồi**: `cau_truy_van_moi()`.
> Dựng thêm chỗ thứ hai là tái tạo đúng lỗi đã trả giá.

---

## [2] Quét toàn bộ kho

| | |
|---|---|
| **Làm gì** | Đi hết phân trang `cursorMark`, lấy cả kho, không phải 10 bài đầu |
| **Phụ thuộc** | Europe PMC `resultType=core` (trả cả tóm tắt ngay trong kết quả tìm) |
| **Hỏng kiểu nào** | Chạm trần `--tran` → kho thiếu. Cursor trỏ về chính nó → lặp vô hạn (đã chặn). `hitCount` bị trang sau ghi đè → **mẫu số sai** (đã chặn: chỉ lấy ở trang đầu). |
| **Dấu hiệu** | `Độ phủ tải về : 38.0%` kèm `⚠ THIẾU 8.173 bản ghi` |
| **Xem ở đâu** | `tools/sources/europepmc.py::quet_toan_bo` |

> ⚠️ **Đừng sàng trên kho thiếu.** Bài chưa tải về cũng là bài chưa ai nhìn —
> không khác gì bài chưa tìm ra.

---

## [3] Xếp bậc chứng cứ

| | |
|---|---|
| **Làm gì** | Đọc `pubTypeList` → bậc 1 (phân tích gộp) … 9 (báo cáo ca). Không nhận ra thì `None`. |
| **Phụ thuộc** | Bảng `EVIDENCE_RANK` trong `tools/sources/pubmed.py` |
| **Hỏng kiểu nào** | Bảng thiếu nhãn → bài bị xếp `None` oan |
| **Dấu hiệu** | `CHƯA PHÂN LOẠI` chiếm tỷ lệ cao (lần chạy thật: **2.459/5.000 = 49%**) |
| **Xem ở đâu** | Chạy `tools/soi_kho.py` — nó tách "không mang nhãn nào" khỏi "bảng ta thiếu" |

> ⚠️ **`None` nghĩa là CHƯA PHÂN LOẠI, không phải BẬC THẤP.** Gộp hai thứ này là
> lặng lẽ hạ điểm gần nửa kho.

> ⚠️ **Nhãn gốc phải được ghi vào tệp kho** (`loai_bai_goc`). Bảng xếp bậc là
> giả thiết của ta; vứt nhãn gốc là vứt luôn khả năng sửa giả thiết đó.

---

## [4] Soi truy vấn

| | |
|---|---|
| **Làm gì** | Với mỗi mệnh đề hỏi hai câu: đứng riêng có ra gì không · AND với bài mồi có ra không |
| **Hỏng kiểu nào** | — (đây là công cụ chẩn đoán, không nằm trên đường chạy chính) |
| **Đọc kết quả** | riêng=0 → **sai tên trường**. riêng>0 nhưng +mồi=0 → **cú pháp đúng, dữ liệu không có thuộc tính đó** |
| **Xem ở đâu** | `tools/soi_truy_van.py` |

Hai dòng cuối trông giống nhau nếu chỉ nhìn "không ra kết quả", nhưng **cách sửa
ngược nhau**: một bên sửa cú pháp, một bên sửa giả định về dữ liệu.

---

## [5] Hàng đợi Spark ↔ SR-Agent

| | |
|---|---|
| **Làm gì** | Spark ghi phiếu `.json` vào thư mục Drive; SR-Agent đọc qua Drive for Desktop |
| **Phụ thuộc** | Drive for Desktop đang đồng bộ · thư mục `hang_doi` |
| **Hỏng kiểu nào** | Spark tạo **Google Doc** thay vì tệp thật → máy đọc ra rỗng. Phiếu quá cũ → dữ liệu ôi. Số học không cộng được → phiếu bị từ chối. |
| **Dấu hiệu** | `.gdoc` bị bắt kèm thông báo riêng · `kiem_do_tuoi` cảnh báo phiếu cũ |
| **Xem ở đâu** | `tools/sources/hang_doi.py` |

> ⚠️ **Google Docs KHÔNG đồng bộ nội dung xuống máy** — chỉ đồng bộ một đường link.
> Đây là kiểu hỏng tệ nhất: thư mục trông như có tệp, đọc ra không có gì.

**Trạng thái**: từ khi Europe PMC thông, đường này **không còn bắt buộc**. Giữ lại
vì Spark vẫn có ích ở khâu tìm kiếm và ghi Drive.

---

## [6] Cổng kiểm định 3 tầng

| Tầng | Kiểm gì | Cần mạng | Hỏng thì sao |
|---|---|---|---|
| 1 | Cấu trúc phiếu: số học, dạng mã, truy vấn có thật | Không | Phiếu bị từ chối nguyên vẹn |
| 2 | Độ phủ = đã sàng / kho | Không | Dưới 10% → **mẫu, không phải sàng lọc hệ thống** |
| 3 | Từng mã có thật không, đúng bài không | **Có** | Chưa chạy được thì mã vẫn là **lời khai**, chưa phải dữ kiện |

**Xem ở đâu**: `tools/kiem_dinh.py`

> ⚠️ Tầng 3 khớp mã qua `alternate_uids` vì phiếu ghi `pubmed:26095867` còn
> Europe PMC trả `europepmc:MED:26095867`. So thẳng hai chuỗi sẽ **báo oan Spark
> bịa mã**. Cổng hay báo oan là cổng sẽ bị bỏ qua.

---

## [7] Sàng lọc — **CHƯA XÂY**

Chỗ trống lớn nhất hiện nay. Xem phần thiết kế đề xuất ở cuối sổ.

---

## [8] Tường lửa số

| | |
|---|---|
| **Làm gì** | Mọi con số trong bản tóm tắt phải neo được vào con số có trong nguồn |
| **Phụ thuộc** | `tools/guard/firewall.py`, tham số `domain="clinical"` |
| **Hỏng kiểu nào** | Gọi thiếu `domain="clinical"` → liều thuốc, thời gian, INR **lọt hết**. Không ai gọi → tầng này chỉ có trên bản đồ |
| **Dấu hiệu** | `python3 tools/kiem_ban_ghi_phac_do.py docs/runs/PHAC_DO_01_ban_ghi.json` — mã thoát `0` ĐẠT · `1` TRƯỢT · `3` còn VÔ HIỆU · `2` không đọc được |
| **Xem ở đâu** | `tools/guard/firewall.py` · lớp bọc `tools/kiem_ban_ghi_phac_do.py` |

**Đã hỏng thật một lần, im lặng.** Sơ đồ trên vẽ [8] chắn ngay trước AnesthOS, nhưng
`check_output` chỉ được gọi từ `demo/`, `docs/audit/` và `tests/` — **không đường chạy sản
xuất nào gọi nó**. 36 bản ghi thuốc tê, gồm liều nhũ tương lipid cấp cứu LAST, chưa từng
đi qua phép neo nào. Critic (L10) tìm ra, không phải phép kiểm nào.

> ⚠️ **`passed=True` KHÔNG có nghĩa là ĐẠT.** `check_output` trả `passed=True` cho khẳng
> định không bóc được mỏ neo số nào (`"one-third"`, `"CNS symptoms present first"`). Đó là
> **VÔ HIỆU**, không phải đạt — `kiem_ban_ghi_phac_do.py` tách hẳn trạng thái thứ ba ra.
> Gộp hai thứ này là đúng kiểu hỏng cả hệ dựng lên để chặn.

**Số đo lần chạy đầu** (2026-09-04, 36 bản ghi): ĐẠT 31 · TRƯỢT 0 · VÔ HIỆU 5. Khớp với
phép đếm thẻ số viết độc lập trước đó — hai cách đo, cùng một số.

---

## Ba giới hạn hạ tầng — không phải lỗi mã

| Giới hạn | Hệ quả |
|---|---|
| `eutils.ncbi.nlm.nih.gov` chặn máy Gun **và** Spark (302 → misuse.ncbi) | Không dùng E-utilities. Đã chuyển sang Europe PMC. |
| Sandbox của Claude chặn mọi tên miền ngoài danh sách trắng (403 CONNECT) | Claude **không tự gọi được** Europe PMC. Mọi lần chạy thật phải trên máy Gun. |
| `python3 -m pip install` trên macOS báo `externally-managed-environment` | Bỏ qua — `httpx`/`pydantic` đã có sẵn. Cần cài thì dùng `--break-system-packages` hoặc venv. |

---

## Ba nguyên tắc rút ra từ lỗi thật

**1. Đo một thứ bằng hai cách là tốt. Cài đặt một phép đo bằng hai đoạn mã là xấu.**
Vế trên bắt được sai sót; vế dưới tạo ra sai sót. Lỗi 0/4-vs-4/4 là vế dưới.

**2. Đừng vứt tín hiệu thô mà mình vừa suy diễn từ đó.**
Giữ kết luận mà bỏ căn cứ nghĩa là khi giả thiết sai thì không sửa được.

**3. Loại ở cửa tìm kiếm không để lại vết; loại ở vòng sàng thì có.**
Nên mọi tiêu chí cần đếm được phải nằm ở vòng sàng, không nằm trong truy vấn.

**4. Một tầng bảo vệ chỉ có trên bản đồ thì tệ hơn là không vẽ nó.**
Ba lỗi tìm ra ngày 2026-09-04 ([8] không ai gọi · PRISMA hỏi tên sự kiện không ai ghi ·
D34 không đọc `alternate_uids`) đều lọt qua vì **chưa ai đọc đầu ra thật bao giờ** —
kiểm thử xanh, tài liệu đúng, đường chạy rỗng. Vì vậy mục **dấu hiệu** của mỗi cơ chế từ
nay phải là **một dòng lệnh chạy được in ra số thật**, không phải một câu mô tả.
