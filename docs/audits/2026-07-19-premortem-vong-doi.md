# Premortem toàn hệ & kế hoạch vòng đời — 2026-07-19

**Bối cảnh:** PM hiện tại (Claude, phiên Fable 5) sắp chuyển giao cho PM kế nhiệm
chạy model yếu hơn (Opus 4.8). Tài liệu này là bài tập premortem cuối cùng của PM
đương nhiệm: giả định hệ CHẾT sau 6 tháng, liệt kê mọi nguyên nhân khả dĩ, và
chuyển từng phán đoán "sống trong đầu PM" thành **cơ chế sống trong repo** — để hệ
vận hành tốt bất kể model nào cầm vai PM.

Nguyên tắc xuyên suốt: *trí thông minh của PM là tài nguyên tạm thời; cơ chế
trong repo là tài sản vĩnh viễn.* Mọi mitigation dưới đây phải là một trong ba
dạng: (a) code + test, (b) gate CI, (c) runbook có checklist — không chấp nhận
"PM sẽ để ý".

---

## §1. Điểm mù XÁC NHẬN BẰNG CODE (phiên audit 2026-07-19)

Mỗi mục dưới đây được xác nhận bằng đọc code trực tiếp, không suy đoán.

### B1 — [P0, ĐÃ VÁ TRONG PR NÀY] TTL purge nuốt corpus SR giữa run
- **Bằng chứng:** `purge_expired()` (staging.py) xóa mọi doc quá 72h
  `last_interaction_at` không ở trạng thái terminal. `last_interaction_at` CHỈ
  được cập nhật qua `upsert(touch=True)` — các stage máy (screen/eligibility/
  extract/rob) ghi sidecar table + events, không bao giờ chạm nó. UI gọi
  `purge_expired()` **mỗi lần mở**.
- **Kịch bản chết:** SR run hợp lệ kéo dài >72h (chắc chắn: cổng người +
  escalation) → người mở `make ui` → toàn bộ corpus đang giữa tuyến bị DELETE.
  Sidecar rows thành mồ côi, PRISMA drift, mất `full_text`.
- **Vá:** miễn trừ TTL cho uid có vết trong `screening`/`extraction`/
  `rob_assessment` + test `test_ttl_never_purges_sr_corpus` khóa vĩnh viễn.

### B2 — [P1, MỞ] Outbound Interceptor chưa nối vào đường Notion publish
- **Bằng chứng:** `grep outbound sr_agent/publish/notion_page.py` → 0 kết quả.
- **Hệ quả:** bất biến CLAUDE.md #7 ("Outbound Interceptor áp lên mọi luồng ra
  ngoài") hiện là doctrine, chưa là code. Payload Notion có thể mang secret/PII
  ra ngoài không qua chốt chặn.
- **Mitigation:** việc nối dây là task nhỏ, rõ scope (gọi `check_payload` trước
  mỗi `pages.create`/`blocks.append`, fail-closed) — giao Antigravity được.
  Ghi vào lộ trình Phase B (§4).

### B3 — [P1, MỞ] Doctor không pin model digest — drift âm thầm
- **Bằng chứng:** `doctor.py` chỉ kiểm model *có trong danh sách đã pull*.
  Tag Ollama (`llama3.1:8b`, `gemma4:e4b`) là mutable — một lần `ollama pull`
  là weights đổi, hành vi screening/RoB đổi, κ sập không dấu vết.
- **Kịch bản chết:** hiệu chuẩn κ=0.9042 (M7.2) trở thành số vô nghĩa sau một
  lần update model; không ai biết vì test offline vẫn xanh (mock).
- **Mitigation:** (1) mọi run log phải ghi digest model (`ollama list --digests`);
  (2) doctor so digest hiện tại với digest trong hồ sơ hiệu chuẩn gần nhất,
  lệch → cảnh báo "cần tái hiệu chuẩn". Giao Antigravity được (Phase B).

### B4 — [P2, MỞ] Trạng thái `queued` quá tải ngữ nghĩa
- Hai vòng đời dùng chung một giá trị: (a) hàng đợi triage đơn-tài-liệu chờ
  Approve→Notion; (b) working-set của tuyến SR. Đã gây ra bug cổng-sai-vị-trí
  (PR #21, đã sửa). Hệ quả còn lại: WIP view lẫn doc SR; người bấm **Reject
  trên UI giữa chừng SR** rút doc khỏi mọi stage im lặng → PRISMA đếm hụt không
  cảnh báo.
- **Mitigation tạm (runbook):** trong thời gian một SR run đang mở, UI chỉ dùng
  để đọc/duyệt cổng SR, không Reject doc thuộc corpus. **Mitigation gốc (Phase
  C/D):** tách `sr_membership` (theo run_id) khỏi `status` triage — thay đổi
  schema có chủ đích, cần thiết kế riêng, KHÔNG làm vội.

### B5 — [P2, GIẢM NHẸ BỞI B1] DELETE documents không cascade
- Xóa doc không xóa sidecar rows (không có FK ON DELETE). Sau vá B1, đường
  DELETE duy nhất còn chạm doc-có-sidecar là thao tác tay. Chấp nhận, ghi nhận.

### B6 — [P2, MỞ] Nhiều writer tiềm năng trên một file SQLite
- Orchestrator batch + UI Streamlit + nightly warehouse có thể ghi chéo. WAL +
  busy_timeout (PR #17) làm hệ *không hỏng*, nhưng interleaving vẫn tạo trạng
  thái khó đoán (vd. Reject giữa batch). **Luật single-writer (runbook):** một
  thời điểm chỉ một tiến trình GHI vào staging DB — orchestrator chạy thì không
  thao tác UI ghi; nightly warehouse dùng DB riêng (đã đúng).

### B7 — [VẬN HÀNH, CHƯA ĐO] Tỷ lệ escalation của BS3 chưa có số thật
- Kỷ luật VOID + đồng thuận cấp domain là đúng về nguyên tắc, nhưng nếu
  escalation-rate thực tế ≈100%, cổng người thành nút cổ chai → áp lực nới lỏng
  bất biến = con đường chết kinh điển. **Phải đo ở FL-1 trước khi xây BS4**
  (weighting của BS4 phụ thuộc phân bố verdict thật).

### B8 — [VẬN HÀNH, CHƯA ĐO] Toàn bộ test mock Ollama — chưa có bằng chứng
  structured-output thật khớp schema
- 363 test xanh chứng minh logic đúng *với giả định* Ollama trả JSON đúng
  schema. Giả định đó chưa từng được kiểm trên `gemma4:e4b` cho RoB prompts.
  **FL-1 phải golden-capture** raw response thật vào fixtures để mock hết "tự
  biên tự diễn" (luật Oracle, xem pm-succession.md).

### B9 — [KIẾN TRÚC, MỞ] Warehouse (BS5) xây xong nhưng chưa nối dây
- `grep -rln "tools.warehouse" tools/ sr_agent/` → 0 caller ngoài chính nó.
  Hai nguồn sự thật full-text tiềm năng (staging `full_text` vs warehouse PDF).
  Quyết định nối dây (eligibility/rob đọc warehouse khi thiếu full_text) để
  Phase C, có spec riêng — không nối vội.

### B10 — [VẬN HÀNH, MỞ] Chưa có kỷ luật backup staging DB
- Staging DB giờ là hồ sơ audit của cả SR (screening/extraction/rob/events).
  Mất file = mất toàn bộ vết. **Runbook Phase B:** backup hằng đêm (copy file
  WAL-checkpointed, giữ 7 bản xoay vòng) — script nhỏ, giao Antigravity.

---

## §2. Premortem: "hệ đã chết sau 6 tháng — vì sao?"

Xếp theo xác suất × thiệt hại. Mỗi kịch bản: cơ chế phòng ngừa + người chịu trách nhiệm.

| # | Kịch bản chết | Cơ chế phòng ngừa | Owner |
|---|---|---|---|
| C1 | **Chết vì nút cổ chai người**: escalation dồn, Gun quá tải, hệ bị bỏ xó hoặc bất biến bị nới để "chạy cho xong" | Đo escalation-rate ở FL-1; ngưỡng hành động: >40% → sửa PROMPT (không bao giờ sửa verify_quote); WIP-limit cho hàng escalation; luật "nới bất biến = Gun duyệt bằng văn bản trong docs/audits" | PM + Gun |
| C2 | **Chết vì mất dữ liệu**: TTL (đã vá), disk, tay lỡ | B1 đã vá bằng test; backup xoay vòng (B10); PRISMA report tái sinh được từ events | PM giao AG |
| C3 | **Chết vì model drift**: pull model mới → κ sập âm thầm, verdict đổi | B3: pin digest + doctor cảnh báo + luật "đổi model = tái hiệu chuẩn M7.2-style trước khi chạy SR thật" | PM |
| C4 | **Chết vì PM kế nhiệm yếu hơn duyệt ẩu**: draft lỗi được approve, số tự khai được tin | Toàn bộ phán đoán thẩm định đã thành checklist máy móc: executor-preflight §B + pm-succession.md §3 (giao thức 7 bước, có lệnh cụ thể). PM không cần *thông minh*, chỉ cần *chạy đúng checklist* | PM kế nhiệm |
| C5 | **Chết vì executor tự khai / lách quy trình** | Sổ sẹo F1–F8 + Preflight Gate đã hoạt động (BS3 là lần bàn giao sạch đầu tiên). Giữ nguyên, không nhân nhượng | PM |
| C6 | **Chết vì lẫn miền**: luật app lâm sàng (Next.js/tính liều) tràn vào repo này lần nữa, hoặc ngược lại | CLAUDE.md đã ghi tường minh vụ 2026-07-11; gate_m6 domain-leak check chặn ở CI; luật: script sync trạm dev chỉ được trỏ `backup/*` | Gun + PM |
| C7 | **Chết vì hạ tầng ngoại vi đổi**: Notion API, GitHub Actions, Ollama API | Đường degradation có sẵn (dry-run Notion, doctor OPTIONAL checks); mọi tích hợp ngoài đều fail-soft trừ guard là fail-closed | PM |
| C8 | **Chết vì tri thức chỉ sống trong chat**: context compaction/đổi model xóa trí nhớ, quyết định không truy được | Luật "không gì chỉ sống trong chat": mọi quyết định → docs/ (audits/specs/runs) + PR body; nghi thức nhận vai (pm-succession.md §5) đọc từ repo, cấm tin chat history | PM |

**Kịch bản C4 là lý do tồn tại của tài liệu này.** Hai bug nặng nhất tuần qua
(cổng sai vị trí, fail-open `overall_rule`) đều được bắt bằng *đọc-toàn-file có
chủ đích* — một hành vi phụ thuộc năng lực PM. Phần năng lực đó đã được nén tối
đa thành §3 của pm-succession.md; phần không nén được (trực giác "chỗ này có mùi")
được bù bằng luật: **mọi module mới bắt buộc có ≥1 adversarial test do PM tự viết
trước khi merge** — cơ chế rẻ nhất buộc PM phải thật sự đọc code.

---

## §3. Ma trận vai trò (bất biến với model)

| Vai | Ai (hiện tại) | Được làm | Cấm |
|---|---|---|---|
| **PM / Kiến trúc sư** | Claude (Fable 5 → Opus 4.8) | Thiết kế, viết mandate, thẩm định độc lập, mở PR, merge sau CI xanh, giữ tracker + docs | Push thẳng nhánh design; tin số tự khai; nới bất biến không có văn bản Gun duyệt |
| **Executor** | Antigravity (Mac local) | Thi công theo mandate, chạy Preflight §B, bàn giao nhánh + SHA + output nguyên văn | Mở PR (F1); tự viết oracle duy nhất cho code của mình; chạm guard/, pyproject, đề bài eval |
| **Gate người** | Gun | Duyệt cổng SR (consensus_review), phân xử escalation, duyệt thay đổi bất biến | Bị giả lập bởi bất kỳ script/agent nào (bất biến #6) |

## §4. Lộ trình vòng đời

- **Phase A — hôm nay (Fable còn tại vị):** merge gói này (vá B1 + 3 tài liệu);
  giao mandate **FL-1** cho Antigravity. Di sản Fable = premortem này +
  pm-succession.md + spec BS4 đã thiết kế xong phần khó.
- **Phase B — PM = Opus 4.8:** (1) nghiệm thu FL-1 theo giao thức §3
  pm-succession.md; (2) giao mandate BS4 (spec đã có, chỉ thẩm định theo
  checklist); (3) 3 task nhỏ giao Antigravity: nối Outbound→Notion (B2), pin
  digest (B3), backup script (B10).
- **Phase C — vận hành đều:** cadence: doctor mỗi ngày (launchd đã có) · backup
  đêm · tái hiệu chuẩn khi digest đổi hoặc mỗi quý · audit toàn hệ mỗi quý
  (mẫu: tài liệu này) · single-writer runbook khi chạy batch.
- **Phase D — mở rộng có kiểm soát:** wire warehouse (B9, spec riêng) · tách
  sr_membership khỏi status (B4, schema v2) · RoB QC UI (BS3.1) · nguồn mới.

**Điều kiện hoàn thành vòng đời tối thiểu (Definition of Alive):** một SR thật
chạy từ `sr_run run --query` đến báo cáo tổng hợp có claim-ledger, mọi số qua
firewall, cổng người được người thật bấm, PRISMA khớp events — không cần bất kỳ
model tier nào cao hơn mức chạy được mandate + checklist.
