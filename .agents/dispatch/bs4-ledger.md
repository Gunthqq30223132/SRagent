# Dispatch Envelope — bs4-ledger
TASK: [SR-BS4a] Consensus ledger (pure module)
TARGET: kr/claude-sonnet-4.5
BRANCH: attempt/bs4-ledger
---
## Capsule (spec-only)
Viết tools/consensus_ledger.py — module THUẦN (không LLM, không I/O ngoài tham số).
KHÔNG sửa file khác. KHÔNG import/sửa tools/guard/. KHÔNG tự viết test.
Spec đóng băng đầy đủ: docs/specs/BS4-implementation.md §0,§2-§5 (đọc nếu có repo access).

### Chữ ký bắt buộc
- build_ledger(extractions, rob_map, protocol) -> list[Claim]
- detect_conflicts(claims) -> claims
- build_anchor_set(claims) -> set[str]
- render_table(claims) -> str
- rob_weight(rob_overall: str) -> float

### Bất biến tất định (LLM KHÔNG tham gia bất kỳ bước nào ở module này)
- build_ledger: chỉ nhận extraction verified==1 (2/0 loại). rob_overall mỗi doc:
  agent='human' thắng rob_a. VOID vẫn vào ledger weight 0.0 (không biến mất).
- outcome map tất định: field ∈ outcome.match_fields ⇒ thuộc outcome; ≤1 outcome/field;
  không khớp ⇒ "__unmapped__".
- direction tất định: stem ∈ protocol.outcomes[].direction_terms xuất hiện trong quote
  (casefold, substring exact — KHÔNG cosine/fuzzy); ≥2 nhóm ⇒ NULL; đúng 1 ⇒ gán;
  thiếu direction_terms ⇒ NULL.
- detect_conflicts: mỗi outcome_id (bỏ __unmapped__), cặp claim 2 uid khác nhau weight>0
  direction đối nghịch (increase↔decrease; no_difference↔bất kỳ hướng) ⇒ conflict_group
  ="cfl-<outcome_id>". Cùng hướng/có NULL ⇒ không nhóm. CẤM MỌI SỐ HỌC giữa claim.
- build_anchor_set: claim weight>0 + outcome đã map: value nguyên văn + token số +
  cặp <số><đơn_vị> (đơn vị ∈ protocol.unit_lexicon, sau NFKC).
- render_table: markdown nhóm theo outcome, hàng "study·RoB·weight·value·[claim_id]";
  nhóm conflict block riêng tiêu đề "CONFLICTING — not pooled".
- Hằng APPROX_LEXICON=["approximately","about","around","roughly","~","khoảng","xấp xỉ","gần"] export được.
- Claim: dataclass theo schema §2 (claim_id,run_id,outcome_id,uid,field,value BYTE-EXACT,
  quote,rob_overall,weight,direction,conflict_group,created_at).

### Acceptance
- Patch CHỈ chạm tools/consensus_ledger.py. Import sạch Python 3.11; không mạng/Ollama/DB.
- Test do Antigravity viết từ §9(a-h) sẽ chấm; không tự viết test trong patch này.
