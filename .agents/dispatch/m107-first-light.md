# Dispatch Envelope — m107-first-light
TASK: https://github.com/Gunthqq30223132/AnesthOS-app/issues/7 (M1-07 First Light của framework)
TARGET: kiro/claude-sonnet-4.5-thinking
BRANCH: attempt/m107-first-light
---
## Capsule (spec-only)

Viết MỘT file test mới `tests/test_new_attempt_adversarial.py` (pytest, Python 3.11)
kiểm thử đối kháng script `scripts/new-attempt.sh` — KHÔNG sửa bất kỳ file nào khác.

### Hợp đồng của script (đủ để viết test, không cần đọc source)
- Cách gọi: `scripts/new-attempt.sh <task-id>`, chạy trong repo git.
- Exit 0: tạo worktree tại `<repo>/../attempts/<task-id>` + branch `attempt/<task-id>`,
  in dòng `Capsule-SHA256: <12 hex>` — SHA-256 của file `.agents/dispatch/<task-id>.md`
  Ở BẢN ĐÃ COMMIT trong HEAD (không phải bản working tree).
- Exit 1: task-id chứa ký tự ngoài [A-Za-z0-9._-]; hoặc thiếu file phong bì đã commit;
  hoặc branch đã tồn tại (local hoặc origin); hoặc không ở trong repo git.
- Exit 2: lỗi git khi tạo worktree.

### Test cases bắt buộc (mỗi test một temp repo riêng qua tmp_path, độc lập nhau)
1. task-id `..`  → exit ≠ 0, và KHÔNG có thư mục/worktree nào được tạo bên ngoài
   `<repo>/../attempts/` (assert thư mục cha của repo không đổi).
2. task-id `.`   → exit ≠ 0, không side effect.
3. task-id chứa khoảng trắng (`a b`) → exit 1, stderr có thông báo invalid characters.
4. task-id bắt đầu bằng `-` (`-foo`, có phong bì committed hợp lệ) → KHÔNG được
   nổ như option-injection: hoặc exit 0 tạo đúng `attempt/-foo`, hoặc exit sạch ≠ 0 —
   assert không traceback/hành vi ngoài hợp đồng.
5. Phong bì đã commit rồi BỊ SỬA trong working tree (dirty) → SHA in ra phải khớp
   SHA-256 của BẢN COMMITTED (test tự tính expected qua `git show HEAD:...`).
6. Định dạng output: dòng `Capsule-SHA256:` chứa đúng 12 ký tự hex thường.

### Acceptance
- `python3 -m pytest tests/test_new_attempt_adversarial.py -v` → toàn bộ pass.
- Patch chỉ chạm `tests/` (path-guard sẽ tự reject nếu chạm scripts/, .agents/, CI).
- Mỗi test tự dựng temp git repo (git init + commit), không phụ thuộc repo thật.
