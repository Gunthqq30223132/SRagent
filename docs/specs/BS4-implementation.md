# BS4-IMPL — Hợp đồng thi công Consensus Generator (implementation-grade)

**Trạng thái:** thiết kế đóng băng 2026-07-20 (PM Fable 5). Đây là tầng thi công
của `BS4-consensus.md` (nguyên tắc, đã đóng băng) — đọc file đó TRƯỚC. Xung đột
giữa hai file: nguyên tắc thắng. **Không thiết kế lại.**
**Điều kiện thi công:** SAU khi D36 merge (cần `run_id` + gate per-run).
**Vị trí trong hệ:** đây là nơi duy nhất SỐ LÂM SÀNG được đưa vào văn bản đầu ra
— mọi lớp phòng thủ của hệ hội tụ về đây. Mọi đường sinh số là code tất định;
LLM chỉ nối văn và LUÔN có đường thoát không-LLM.

## §0. Kiến trúc file

- `tools/consensus_ledger.py` — **thuần túy** (không LLM, không I/O ngoài tham
  số): `build_ledger`, `detect_conflicts`, `build_anchor_set`, `render_table`,
  `rob_weight`. Test đánh chủ yếu vào đây.
- `tools/consensus_run.py` — CLI + orchestration: gate check, đọc DB, gọi
  ledger, gọi LLM narrative, firewall, ghi report + event + state.
- KHÔNG sửa `tools/guard/` (gate D2) — firewall/anchors chỉ IMPORT.

## §1. Cổng vào (bất biến #6 — chỉ ĐỌC trạng thái người tạo)

`consensus_run` từ chối chạy (rc=2, in lý do) khi thiếu BẤT KỲ điều nào:
1. Event `CONSENSUS_APPROVED` tồn tại với `events.run_id = <run>` (chỉ D37
   Tab 3 ghi được event này).
2. `sr_runs.state = 'CONSENSUS_READY'`.
3. Protocol hiện tại khớp `protocol_sha256` của run (lệch = protocol đổi sau
   khi người chốt ⇒ phê duyệt vô hiệu).
KHÔNG tồn tại cờ CLI bỏ qua cổng, không có đường scriptable tạo
`CONSENSUS_APPROVED` (đã cấm ở D37 §2).

## §2. Schema (additive) + khối protocol mới

```sql
CREATE TABLE IF NOT EXISTS consensus_claim (
    claim_id    TEXT PRIMARY KEY,  -- "clm-<run_id>-<seq3>"
    run_id      TEXT NOT NULL,
    outcome_id  TEXT NOT NULL,     -- từ protocol.outcomes; "__unmapped__" nếu không khớp
    uid         TEXT NOT NULL,
    field       TEXT NOT NULL,     -- extraction field id
    value       TEXT NOT NULL,     -- BYTE-EXACT từ bảng extraction, không format lại
    quote       TEXT NOT NULL,
    rob_overall TEXT NOT NULL,     -- Low | Some concerns | High | VOID
    weight      REAL NOT NULL,     -- rob_weight(rob_overall), hợp đồng BS4-consensus
    direction   TEXT,              -- increase | decrease | no_difference | NULL
    conflict_group TEXT,           -- id nhóm xung đột; NULL nếu không
    created_at  TEXT NOT NULL
);
```

Protocol JSON thêm 2 khối (validate trong `protocol_build`, id trùng ⇒ lỗi nạp):
```json
"outcomes": [
  {"id": "primary_recovery", "label_en": "...",
   "match_fields": ["primary_outcome", "recovery_time"],
   "direction_terms": {"decrease": ["reduc", "decreas", "shorten"],
                       "increase": ["increas", "prolong"],
                       "no_difference": ["no significant difference", "similar", "comparable"]}}
],
"unit_lexicon": ["mg", "mcg", "μg", "μg/kg", "mg/kg", "ml", "min", "%", "mac"]
```
`direction_terms` tùy chọn — thiếu ⇒ direction luôn NULL (hai giá trị chỉ được
trưng bày cạnh nhau, không bao giờ bị phán cùng/khác hướng). Ngữ nghĩa miền nằm
trọn trong protocol — core topic-blind (bất biến #3).

## §3. Xây ledger — `build_ledger(extractions, rob_map, protocol) -> list[Claim]`

1. **Đầu vào:** doc của run có `ROB_COMPLETED`; extraction `verified=1` DUY NHẤT
   (`verified=2` "không kiểm chứng được" KHÔNG vào ledger — không có anchor thì
   không được làm số liệu; `verified=0` đã bị hủy).
2. **rob_overall mỗi doc:** ưu tiên `agent='human'` (phán định D37) > `rob_a`
   (đồng thuận máy — ROB_COMPLETED nghĩa là A=B). Hàng `__overall__`.
3. **VOID vẫn vào ledger** với weight 0.0 — minh bạch trong phụ lục "Excluded",
   không bao giờ lặng lẽ biến mất (nguyên tắc BS4-consensus).
4. **outcome mapping tất định:** field ∈ `match_fields` của outcome nào thì
   thuộc outcome đó; một field thuộc ≤1 outcome (validate lúc nạp protocol);
   không khớp ⇒ `__unmapped__` (vào ledger, KHÔNG vào phần số của narrative).
5. **direction tất định:** stem trong `direction_terms` xuất hiện trong quote
   (casefold, substring exact — cùng cơ chế pertinence lint D37 §4, KHÔNG
   cosine/fuzzy); match ≥2 nhóm khác nhau ⇒ NULL (nhập nhằng = không phán);
   match đúng 1 nhóm ⇒ gán. LLM không bao giờ tham gia bước này.

## §4. Phát hiện xung đột — `detect_conflicts(claims) -> claims`

Trong mỗi `outcome_id` (bỏ `__unmapped__`), xét mọi cặp claim từ 2 uid khác
nhau có weight > 0:
- direction đối nghịch (`increase` vs `decrease`, hoặc `no_difference` vs bất
  kỳ hướng nào) ⇒ cả nhóm nhận `conflict_group = "cfl-<outcome_id>"`.
- Cùng direction hoặc có NULL ⇒ KHÔNG phán "consistent" — narrative chỉ được
  liệt kê song song. Hệ không có khái niệm "đồng thuận số học".
- **CẤM mọi phép số học giữa các claim** (mean/pool/so độ lớn) — so sánh giá
  trị giữa study là meta-analysis, vĩnh viễn ngoài đường LLM (BS4-consensus).

## §5. Anchor set + firewall — `build_anchor_set(claims) -> set[str]`

Với mỗi claim weight > 0 và outcome đã map:
- anchor gồm: (a) `value` nguyên văn; (b) mọi token số bóc từ value bằng
  `extract_anchors` (import guard); (c) mọi cặp `<số> <đơn_vị>` với đơn vị
  thuộc `unit_lexicon` (sau NFKC — μ đã chuẩn hóa từ MED-READY).

Kiểm narrative (theo thứ tự, fail bất kỳ bước nào ⇒ reject toàn bộ):
1. **NE1 (xuôi):** mọi token số trong narrative ∈ anchor set — dùng
   `check_output`/`extract_anchors` của `tools/guard/firewall.py`.
2. **Lint ước lượng:** từ thuộc APPROX_LEXICON (hằng trong ledger.py:
   `["approximately", "about", "around", "roughly", "~", "khoảng", "xấp xỉ",
   "gần"]`) đứng trong cùng câu với một token số ⇒ reject (cấm LLM làm mềm số).
3. **NE2 (ngược):** mọi `conflict_group` phải có ≥1 câu chứa các claim_id của
   nhóm — LLM không được "quên" mâu thuẫn cho văn mượt.
4. **NE4/NE5:** mọi câu chứa token số phải chứa ≥1 `[clm-...]`; mọi `[clm-...]`
   trong văn phải resolve về claim_id tồn tại trong ledger.

## §6. Narrative — LLM là trang sức, không phải trụ

1. `render_table(claims)` (thuần) dựng markdown TRƯỚC: nhóm theo outcome, mỗi
   hàng `study · RoB · weight · value · [claim_id]`; nhóm conflict render block
   riêng tiêu đề **"CONFLICTING — not pooled"** liệt kê cả hai phía kèm RoB.
2. LLM (`OLLAMA_MODEL`, temp 0, structured `{narrative: str}`) nhận bảng + luật:
   chỉ dùng số y nguyên từ bảng kèm `[claim_id]`; không từ ước lượng; không
   kết luận hướng cho nhóm không có direction. Prompt qua num_ctx guard
   (MED-READY) — overflow ⇒ nhảy thẳng bước 4.
3. Reject (§5) ⇒ rewrite kèm lý do, tối đa **2 lần** (trần D32).
4. Lần 3 fail (hoặc overflow/Ollama sập) ⇒ **narrative = bảng render sẵn +
   câu khung tất định** ("Bảng dưới trình bày nguyên văn giá trị đã kiểm chứng
   theo outcome; các nhóm CONFLICTING không được gộp.") + event
   `CONSENSUS_NARRATIVE_FALLBACK`. Báo cáo VẪN ra — không có chế độ "chờ LLM".

## §7. Report artifact + event + state

- File `docs/runs/<YYYY-MM-DD>-consensus-<run_id>.md`: header (run_id,
  protocol_sha256, git HEAD, ngày) → số PRISMA per-run → narrative → bảng
  ledger đầy đủ → phụ lục Excluded (mọi claim weight 0 + lý do VOID) → phụ lục
  quote nguyên văn. Ghi LOCAL — không tự publish Notion (muốn publish: đường
  NotionPublisher sẵn có, đã qua Outbound Interceptor — quyết định của người).
- Ghi mọi claim vào `consensus_claim` TRƯỚC khi sinh narrative (ledger là sự
  thật, narrative là dẫn xuất).
- Kết thúc: event `CONSENSUS_COMPLETED` (uid=`consensus:<run_id>`, detail =
  `claims=<n> conflicts=<m> mode=llm|fallback`) + `sr_runs.state = 'CLOSED'`.

## §8. CLI

`python -m tools.consensus_run --protocol <path> --run <id> [--out <path>]`
— không flag nào bỏ gate §1; chạy lại trên run CLOSED ⇒ rc=2 (immutable sau
chốt; muốn làm lại = mở run mới).

## §9. Test offline bắt buộc (`tests/test_consensus.py`, ratio ≥ 2)

(a) ledger chỉ nhận verified=1; human overall thắng rob_a; (b) VOID weight 0
vẫn nằm ledger + phụ lục Excluded; (c) direction: match 1 nhóm ⇒ gán, match 2
nhóm ⇒ NULL, thiếu direction_terms ⇒ NULL; (d) conflict: đối nghịch ⇒ nhóm
đúng, cùng hướng/NULL ⇒ không nhóm; (e) NE1: narrative chứa số lạ ⇒ reject;
(f) lint ước lượng: "approximately 50 mg" ⇒ reject; (g) NE2: conflict vắng
trong narrative ⇒ reject; (h) NE4/NE5: câu có số thiếu [clm] hoặc [clm] mồ côi
⇒ reject; (i) quá 2 rewrite ⇒ fallback + event + báo cáo vẫn ra file; (j) gate:
thiếu CONSENSUS_APPROVED / state sai / protocol_sha256 lệch ⇒ rc=2 không ghi gì;
(k) run CLOSED chạy lại ⇒ rc=2. LLM mock toàn bộ — không gọi Ollama thật.

## §10. Ngoài phạm vi v1

Meta-analysis/pooling (vĩnh viễn ngoài đường LLM) · GRADE scoring · forest
plot · publish Notion tự động · direction bằng LLM · so sánh độ lớn giá trị
giữa study · narrative đa ngôn ngữ (v1 tiếng Anh, khớp ngôn ngữ quote).
