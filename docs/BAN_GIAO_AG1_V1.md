# Bàn giao AG-1 — cài đặt V1 (sổ phủ bằng chứng)

> **Vai của bạn: AG-1 · Viết mã.** Chỉ sửa `tools/**`. **Tuyệt đối không chạm
> `tests/**`.**
> Nhánh: `claude/sr-agent-architecture-audit-scn4v6` · Trạng thái hiện tại:
> **568 xanh + 61 đỏ**.

---

## 1. Việc của bạn, gói gọn

Viết `tools/so_phu_bang_chung.py` sao cho **61 kiểm thử đang đỏ chuyển xanh**, và
568 kiểm thử đang xanh **vẫn xanh**.

```bash
git pull
python3 -m pytest tests/test_so_phu_bang_chung.py    # 61 đỏ — đúng trạng thái xuất phát
```

**Đọc trước khi viết dòng mã đầu tiên:** `docs/DAC_TA_V1_SO_PHU.md`. Đó là nguồn
chân lý. Kiểm thử là bản diễn dịch của đặc tả, không thay thế đặc tả.

---

## 2. Ba điều cấm

| # | Cấm | Vì sao |
|---|---|---|
| **C1** | **Sửa bất cứ tệp nào trong `tests/`** | kiểm thử được viết TRƯỚC khi có mã, bởi người khác. Sửa nó là phá đúng rào cản mà nó tồn tại để dựng |
| **C2** | **Đi tìm bốn con số Đ1–Đ4 rồi cài cho khớp** | xem §3 — đây là điều quan trọng nhất trong tài liệu này |
| **C3** | Thêm thư viện mới, chạm `sr_agent/`, `pipeline.py`, `pyproject.toml` | vùng cấm sửa; chỉ dùng `pydantic` + thư viện chuẩn |

**Nếu bạn tin một kiểm thử SAI:** không sửa nó. Ghi lại bất đồng (tên kiểm thử,
vì sao bạn cho là sai, đặc tả nói gì) rồi **DỪNG**. Đây là chỗ **duy nhất** được
phép dừng giữa chừng.

---

## 3. Điều quan trọng nhất: bốn con số phải do BẠN tự suy ra

Đặc tả §4 nêu bốn con số nghiệm thu (Đ1–Đ4) trên dữ liệu AnesthOS thật. Chúng do
Claude tính khi soạn đặc tả, **bằng một đoạn mã cố ý không đưa vào repo**.

| Nếu bạn cài đặt từ **quy tắc §2** | Nếu bạn dò ngược để khớp số |
|---|---|
| Số khớp = **hai lần đọc dữ liệu độc lập cùng ra một kết quả** | Số khớp **không chứng minh được gì** |
| Lỗi trong cách đọc của Claude sẽ **lộ ra** | Lỗi đó **nhân bản sang bạn** và biến mất khỏi tầm nhìn |

**Bốn con số đó đã sai một lần rồi.** Bản kế hoạch được duyệt ghi 20.416 / 16.562
/ 2.241 — sai vì đếm cả tệp khai xuất xứ, xếp nhầm ba khoá trình bày, và bỏ sót
`timeToDeath` khỏi nhóm chết người. Chúng là **số đo**, không phải chân lý.

> **Số của bạn lệch với Đ1–Đ4 → đó là BẤT ĐỒNG THẬT, không phải lỗi của bạn.**
> Ghi cả hai con số, chỉ ra **khoá nào đếm khác**, rồi chuyển Gun quyết.
> Quy tắc §2 là nguồn chân lý; bốn con số chỉ là hệ quả của nó.

---

## 4. Gợi ý về chỗ dễ cài sai

Ba chỗ kiểm thử nhắm thẳng vào, vì đó là nơi trực giác hay dẫn sai:

| Chỗ | Sai thường gặp | Đặc tả |
|---|---|---|
| Danh sách trong JSON | coi phần tử danh sách là vô danh → **mất khoá** → không xếp được mức rủi ro | §2.1: phần tử **kế thừa khoá của từ điển cha**. `{"routes":["IV","PO"]}` = **2 lá**, cùng khoá `routes` |
| `provenance_manifest.json` | duyệt nó như dữ liệu lâm sàng | §2.2: **loại khỏi phạm vi** — nó là siêu dữ liệu *về* nguồn |
| Khoá lạ | mặc định mức 1 "cho an toàn" | §2.3: **mặc định là 3**. Có 292 khoá hiếm; mặc định cao thổi phồng nhóm nguy hiểm bằng nhiễu và làm hỏng chính công dụng của xếp hạng |

Và một ràng buộc cấu trúc: `muc_phu` phải **suy ra** từ các trường, **không có
setter**. Kiểm thử `test_R1_muc_phu_SUY_RA_khong_gan_tay` chốt đúng điều đó.

**Tái dùng, đừng viết lại:** `tach_trich_dan()` trong `tools/mo_hat_giong.py` đã
bóc được chuỗi trích dẫn ghép nhiều nguồn bằng dấu chấm phẩy.

---

## 5. Xong thì trông như thế nào

| Kiểm | Lệnh | Chuẩn |
|---|---|---|
| Kiểm thử | `python3 -m pytest` | **629 xanh, 0 đỏ** |
| Không lấn vai | `git diff --name-only` | **chỉ** `tools/so_phu_bang_chung.py` |
| Cổng chất lượng | `bash scripts/gate_m6.sh` | qua |

Rồi commit + đẩy lên **cùng nhánh**, thông điệp nêu rõ bốn con số bạn tự đo được.

---

## 6. Sau khi đẩy — chuyển vai AG-3 (chạy nghiệm thu)

Chạy **trên mã đã commit**, và **không sửa gì** dù kết quả ra sao:

```bash
python3 tools/so_phu_bang_chung.py --du-lieu <đường dẫn AnesthOS>/src/domain/data/
```

Báo cáo **số thô**, đối chiếu với đặc tả §4:

| # | Kỳ vọng |
|---|---|
| Đ1 | tổng lá **20.279** |
| Đ2 | nhãn/định danh/trình bày **3.862** |
| Đ3 | mang hệ quả lâm sàng **16.417** |
| Đ4 | ưu tiên 1 **2.271** · ưu tiên 2 **4.908** · ưu tiên 3 **9.238** |
| Đ5 | **0** khẳng định ở mức "có chuỗi bằng chứng đầy đủ" |
| Đ6 | `3.862 + 2.271 + 4.908 + 9.238 == 20.279` |

**Đ5 là cổng quan trọng nhất.** Ra khác 0 nghĩa là bộ tính mức phủ đang tự khai —
chưa có V2/V3 thì không khẳng định nào được phép có chuỗi đầy đủ. Ra khác 0 thì
**dừng và báo**, đừng đi tiếp.

**Lưu ý về tính độc lập:** nếu bạn làm cả AG-1 lẫn AG-3, hãy chạy nghiệm thu
**sau khi đã commit**, trên mã đã đẩy, và **chỉ báo số** — không chỉnh mã cho
số đẹp hơn. Chỉnh mã sau khi thấy số là tự chấm bài mình.
