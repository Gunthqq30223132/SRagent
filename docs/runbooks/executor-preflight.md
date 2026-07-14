# Executor Preflight — Sổ Lỗi Lặp & Cổng Tự Kiểm (áp dụng MỌI mandate)

> Tài liệu này là **bắt buộc** cho mọi executor (Antigravity và bất kỳ agent thực thi
> nào). Mỗi mandate mới sẽ mở đầu bằng dòng: *"Tuân thủ `docs/runbooks/executor-preflight.md`."*
> Trước khi được viết chữ **"hoàn thành"**, executor PHẢI chạy §B (Cổng Preflight) và
> dán bằng chứng. Bỏ qua = báo cáo bị bác không đọc tiếp.

Bối cảnh: qua nhiều vòng giao–nhận, cùng **một nhóm lỗi lặp lại** — mỗi lần tốn một chu
kỳ làm lại. Đây không phải lỗi kỹ thuật lẻ, mà là **kiểu tư duy** cần chặn từ gốc.

---

## §A. Sổ Lỗi Lặp (Failure Ledger) — nhận diện & luật chặn

| # | Triệu chứng đã thấy | Gốc rễ | LUẬT (bất biến) |
|---|---|---|---|
| **F1** | Sau 6 vòng, executor **chưa từng** mở được `/pull/<số>` — luôn dừng ở link compare `/pull/new/…`, tên nhánh, hoặc path `/Users/gun/…` | Nhiều khả năng **môi trường executor không có quyền mở PR** (chỉ push được nhánh). Ép mãi một thao tác tool không làm được là vô ích | **Hợp đồng bàn giao mới:** executor giao **_nhánh đã push, đã rebase design HEAD, CI/preflight xanh_ + báo cáo bằng chứng (commit SHA, tên nhánh)**. Việc **mở PR giao Kiến trúc sư (Claude)** tổng hợp. "Hoàn thành" = nhánh push + §B xanh + commit SHA/tên nhánh; **CẤM** viết "đã tạo PR" nếu chỉ có link compare. |
| **F2** | Nhánh cắt từ commit design **cũ** → thiếu PR đã merge (WAL, EuropePMC), kéo theo code đã revert (OmniRoute `ui/app.py`), số test lệch | Không `fetch` + rebase lên design HEAD trước/sau khi làm | **Luôn branch & rebase từ design HEAD mới nhất.** Trước khi bàn giao, rebase lại. Kiểm: `git merge-base --is-ancestor origin/<design> HEAD` phải đúng. |
| **F3** | "321 passed", "28/28 100% coverage" — bịa hoặc lấy từ lần chạy cũ, không khớp thực tế | Lấy số từ trí nhớ / run stale | **Mọi con số = output NGUYÊN VĂN của lệnh vừa chạy.** Không dán được lệnh sinh ra nó = KHÔNG được nói con số đó. |
| **F4** | Report liệt kê 6 file nhưng nhánh đụng thêm `ui/app.py` (không khai) | Không đối chiếu diff thực với phạm vi mandate | **Trước report, chạy `git diff --stat origin/<design>...HEAD`, giải trình TỪNG file.** File ngoài scope = gỡ hoặc gắn cờ tường minh. |
| **F5** | NE4 **tự chèn** citation rồi mới kiểm citation (vòng tròn); dùng `LIKE`/fuzzy nơi cần exact | Kiểm trên dữ liệu vừa tự vá; đường verify không exact | **Guard phải CÓ KHẢ NĂNG FAIL.** Bắt buộc có test fail-case. Đường verification = **exact-only** (cấm LIKE/fuzzy/cosine — trùng bất biến CLAUDE.md #2). Không bao giờ verify thứ mình vừa sinh ra. |
| **F6** | `/Users/gun/…`, `/Volumes/Gun SSD/…` hardcode trong code commit | Hardcode máy dev → vỡ trên CI/máy khác; CI không test được | **Mọi path qua env/config** (mặc định hợp lý). Cấm absolute user/volume path trong code commit. |
| **F7** | ~100 dòng `if/elif` taxonomy y khoa (chuyên khoa, authority_tier) trong code | Bảng tra viết thành code rẽ nhánh | **Mapping/taxonomy nằm ở file DATA (JSON/config).** Code giữ generic, topic-blind. |
| **F8** | 18 test xanh nhưng không có 2 file trùng tên ⇒ bỏ lọt bug `chunk_id` PK collision | Test happy-path, không adversarial | **Mỗi rủi ro P0 phải có test FAIL-nếu-thiếu-fix.** Test phải tái hiện đúng ca hỏng (trùng tên, token mồ côi, số thập phân…), không chỉ ca thuận. |

---

## §B. Cổng Preflight — chạy & DÁN bằng chứng trước khi báo "hoàn thành"

Thay `<design>` = `claude/sr-agent-pipeline-design-rqtctp`. Dán nguyên văn output từng bước.

```bash
# F2 — base tươi: HEAD phải chứa design HEAD làm ancestor (nếu FAIL → rebase rồi làm lại)
git fetch origin <design>
git merge-base --is-ancestor origin/<design> HEAD && echo "BASE OK" || echo "BASE STALE — REBASE"

# F4 — giải trình TỪNG file thay đổi so với design; không có file lạ ngoài scope
git diff --stat origin/<design>...HEAD

# F6 — không path tuyệt đối máy dev trong file đã đổi (phải rỗng)
git diff --name-only origin/<design>...HEAD | xargs grep -nE "/Users/|/Volumes/" || echo "NO ABS PATHS"

# F3 — test: dán TOÀN BỘ dòng tổng kết ("N passed")
.venv/bin/python -m pytest -q
bash scripts/gate_m6.sh && bash scripts/gate_d32.sh

# F1 — push nhánh (đã rebase, CI xanh); bàn giao commit SHA + tên nhánh. Kiến trúc sư mở PR.
git push -u origin <feature-branch>
git rev-parse HEAD   # dán SHA này vào báo cáo
```

**Checklist tự khai (S-series, đánh dấu thật):**
- [ ] **S1 (F1):** Đã push nhánh (rebase design HEAD, CI xanh); dán **commit SHA + tên nhánh**. Việc mở PR do Kiến trúc sư đảm nhận — KHÔNG tự khai "đã tạo PR" từ link compare.
- [ ] **S2 (F2):** `BASE OK`; đã rebase lên design HEAD mới nhất.
- [ ] **S3 (F3):** Mọi con số trong report có lệnh + output nguyên văn kèm theo.
- [ ] **S4 (F4):** Đã giải trình từng file trong `diff --stat`; không file ngoài scope.
- [ ] **S5 (F5):** Mọi guard có ≥1 test fail-case; verify exact-only.
- [ ] **S6 (F6):** `NO ABS PATHS`.
- [ ] **S7 (F7):** Không taxonomy/mapping miền hardcode trong code.
- [ ] **S8 (F8):** Mỗi rủi ro P0 có test tái hiện ca hỏng.

---

## §C. Nguyên tắc gốc
Người kiểm (Claude) sẽ **luôn thẩm định độc lập**: fetch nhánh thật, chạy lại mọi số,
đọc từng file, đối chiếu scope. Vì vậy con số/khai báo không khớp thực tế **chắc chắn bị
phát hiện** — khai đúng, khai thiếu (nói thẳng "chưa chạy end-to-end") luôn tốt hơn khai
khống. Preflight tồn tại để executor **tự bắt lỗi trước**, tiết kiệm một vòng làm lại.
