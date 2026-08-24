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
| **Hỏng kiểu nào** | Gọi thiếu `domain="clinical"` → liều thuốc, thời gian, INR **lọt hết** |
| **Dấu hiệu** | `anchors_checked=0` trên văn bản rõ ràng có số lâm sàng |
| **Xem ở đâu** | `tools/guard/firewall.py` |

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
