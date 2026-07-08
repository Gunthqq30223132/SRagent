# D31 — Điều phối đa thiết bị (Mobile ↔ Mac ↔ GitHub) & Tầng tổng hợp Cloud Hybrid

> **Vai trò tài liệu**: thiết kế kiến trúc + spec hiện thực cho 2 subsystem mới; 2 tầng guard
> (§4, §5) **đã được hiện thực chạy được** tại `tools/guard/` kèm `tests/test_guards.py`.
> **Nền tảng**: `docs/HANDOVER.md` (6 trụ cột), D30 (multi-agent SR), TS-D30 (hợp đồng M6).
> **Bất biến kế thừa**: mù chủ đề của core, vùng cấm `router.py`/`config.py`, con người là
> chốt chặn cuối, tất định ở mọi tầng lọc, credentials không bao giờ nằm ngoài Keychain/.env local.

---

## §0. Phán quyết phê bình đề xuất ban đầu (đọc trước khi hiện thực bất kỳ phần nào)

Đề xuất gốc đúng hướng ở: relay outbound-only (không mở port inbound), worktree cô lập,
Docling PDF→Markdown giữ cấu trúc, firewall fail-closed, sanitize trước khi xuất. Nhưng có
**7 điểm phải chỉnh trước khi code**, mỗi điểm đều va vào một bất biến sẵn có của hệ:

| # | Đề xuất gốc | Phán quyết | Lý do gắn với bất biến hiện có |
|---|---|---|---|
| 1 | Technical anchors `[#bold/brackets]` chèn **inline** vào Markdown | **BÁC — anchors phải là sidecar metadata** | Mutate văn bản canonical phá `verify_quote` substring (M6c) và mọi so khớp verbatim: quote trích từ bản đã chèn tag sẽ không bao giờ khớp bản gốc, và ngược lại. Văn bản canonical là bất biến; chỉ số/anchor sống ở bảng phụ (uid, span, kind) — đúng pattern sidecar `screening`/`extraction` đã dùng. |
| 2 | "Automated semantic merge flow" tự giải conflict | **BÁC auto-resolve — thay bằng merge queue + gate trọng tài** | AI tự quyết semantic conflict = AI tự quyết đúng/sai kiến trúc, trái "con người là chốt chặn cuối". AI chỉ *viết* commit message; *quyết* merge là gate (PASS/FAIL tất định) + con người. Chi tiết §2. |
| 3 | Worktrees song song, mỗi cái node_modules/.env riêng | **CHỈNH 2 chỗ** | (a) SQLite staging KHÔNG được chia sẻ giữa agent song song (lock contention + trộn state) — mỗi worktree một `SR_AGENT_DB` (env override có sẵn trong `config.py`). (b) 16GB RAM không chạy nổi 2 phiên LLM 7B song song — **song song chỉ dành cho tác vụ non-LLM**; Ollama là tài nguyên tuần tự, ai cần thì xếp hàng. |
| 4 | `.env` riêng cho từng worktree | **BÁC — secrets không được nhân bản** | Mỗi bản copy `.env` là một điểm rò rỉ mới (và là thứ interceptor §5 phải chặn). Dùng macOS Keychain (`security find-generic-password -s sr-agent -a IEEE_API_KEY -w`) hoặc env user-level duy nhất; worktree chỉ chứa config KHÔNG nhạy cảm. |
| 5 | Mobile rớt kết nối → cần cơ chế "agent stalls safely" | **ĐÚNG, nhưng cơ chế an toàn số 1 không phải tmux** | Safe-stall thật sự đến từ **permission mode** của Claude Code: thao tác ngoài allowlist chặn ở prompt phê duyệt — mobile rớt thì agent tự đứng ở checkpoint kế tiếp theo thiết kế. tmux chỉ giải quyết *persistence* của terminal, không giải quyết *safety*. Không bao giờ auto-restart agent LLM (§1). |
| 6 | LLMProvider chuyển đổi seamless local ↔ cloud | **CHỈNH: fallback phải BẤT ĐỐI XỨNG** | Cloud→local tự động là suy giảm *riêng tư hóa* — an toàn, cho phép. Local→cloud tự động là **âm thầm xuất dữ liệu ra ngoài** khi Ollama sập — cấm; phải opt-in tường minh mỗi lần chạy và ồn ào như `single_model_mode` của M6-hotfix. "Seamless" đúng ở API code, sai ở chính sách dữ liệu. |
| 7 | NotebookLM là một provider trong adapter | **CHỈNH: NotebookLM không có API — nó là ĐƯỜNG EXPORT** | Ép nó vào interface provider tạo abstraction giả. Nó là `NotebookLMExporter`: sinh bundle Markdown đã sanitize + Source Map để người dùng tự upload thủ công (§3). |

---

## §1. Suy giảm êm khi rớt kết nối (Graceful Connection Degradation)

### Mô hình 3 tầng — mỗi tầng một trách nhiệm, không chồng vai

```
Tầng an toàn  : Claude Code permission mode  → agent TỰ ĐỨNG ở prompt phê duyệt
                (mobile rớt = không ai bấm approve = agent stall đúng thiết kế)
Tầng bền vững : tmux session "sr-agent"      → terminal + process sống qua ngắt kết nối,
                pipe-pane ghi log xoay vòng   output không mất một dòng nào
Tầng canh gác : launchd watchdog (KeepAlive   → giữ TMUX SERVER sống + bắn alert dead-man;
                cho tmux, KHÔNG cho agent)      TUYỆT ĐỐI không tự khởi động lại agent
```

### Runbook (Mac M4)

```bash
# Khởi tạo phiên điều khiển từ xa (chạy 1 lần sau mỗi lần boot)
tmux new-session -d -s sr-agent -c ~/projects/9router
tmux pipe-pane -t sr-agent -o 'cat >> ~/projects/9router/staging/agent-console.log'
tmux send-keys -t sr-agent 'claude' Enter
# Mobile rớt → mở lại app → tmux attach -t sr-agent: nguyên hiện trường.
```

### Watchdog + dead-man alert (spec, theo pattern plist M3/M4 sẵn có)

- Template mới `scripts/com.sragent.watchdog.plist.template`: `StartInterval` 300,
  script kiểm tra `tmux has-session -t sr-agent`; session chết → notify qua
  `sr_agent.monitor.alerts.notify()` sẵn có (Notification Center + webhook về điện thoại).
- Rule alert mới `SESSION_STALLED` (additive vào `desired_alerts`): console log không có
  dòng mới > N giờ **và** tmux session tồn tại ⇒ agent đang treo chờ phê duyệt lâu bất
  thường → một notify duy nhất (máy trạng thái M4 chống alarm-fatigue lo phần còn lại).
- **Điều cấm ghi thành văn**: watchdog không có quyền `tmux send-keys` — gõ phím vào phiên
  agent là hành động của con người. Auto-restart một agent đang giữa chừng suy luận là
  cách nhanh nhất biến sự cố nhỏ thành sự cố dữ liệu.

---

## §2. Worktree song song & merge có kỷ luật (Worktree Sync & Semantic Commits)

### Quy ước worktree

```bash
git worktree add ../9router-parser  agent/parser-bench     # mỗi agent 1 worktree + 1 nhánh agent/<task>
git worktree add ../9router-adapter agent/acm-adapter
```

- Mỗi worktree: `SR_AGENT_DB=$PWD/staging/dev.db` (env override sẵn có) — **không bao giờ**
  trỏ chung DB; artifact build/venv riêng; secrets KHÔNG copy (đọc Keychain, phán quyết #4).
- Phân vùng file ownership **disjoint ghi trong task spec** (đúng pattern vùng cấm
  TS-D29/D30): hai agent không bao giờ được giao cùng file — đây là cách *tránh* conflict
  rẻ hơn mọi cách *giải* conflict.
- Ollama: tài nguyên tuần tự (phán quyết #3). Tác vụ LLM xếp hàng qua lock file
  `staging/.ollama.lock` (flock) — đơn giản, tất định, đủ cho 1 máy.

### Luồng merge 4 bước (thay cho "automated semantic merge")

```
1. REBASE   : agent rebase nhánh mình lên target mới nhất (rerere bật sẵn:
              git config rerere.enabled true — conflict lặp lại tự giải bằng lời giải CŨ
              của con người, không phải lời giải MỚI của AI)
2. GATE     : bash scripts/gate_m6.sh trong worktree — FAIL thì không có quyền xin merge
3. PR       : mô tả theo template 4 phần (tiền lệ PR #2); AI VIẾT commit message ngữ nghĩa
              theo convention đã dùng (M6a-FR-a1:.../T1:...), diff là bằng chứng
4. TRỌNG TÀI: conflict content thật sự → mở PHIÊN GIẢI CONFLICT RIÊNG có người duyệt từng
              hunk; không agent nào tự merge conflict của agent khác
```

**Commit ngữ nghĩa**: message mô tả *thay đổi kiến trúc/hợp đồng*, không mô tả *diff* —
mẫu: `<task-id>: <hành vi mới/bất biến mới> — <ranh giới không đổi>`; trailer đã chuẩn hóa.
Lịch sử git là state machine của dự án — đúng đề xuất gốc — nên message là API, không phải nhãn.

---

## §3. `SynthesisProvider` — adapter Layer C với fallback bất đối xứng

### Hợp đồng (đặt tại `tools/synthesis/provider.py` khi hiện thực — ngoài core)

```python
class SourceDoc(BaseModel):
    uid: str                  # ieee:… | arxiv:… — nối về staging store
    markdown: str             # Docling output, CANONICAL, không chèn anchor inline
    source_map_entry: str     # 1 dòng mô tả trong Source Map

class SynthesisResult(BaseModel):
    text: str
    citations: list[str]      # uid các nguồn được viện dẫn — BẮT BUỘC khác rỗng
    provider: str
    firewall: "FirewallVerdict"   # đính kèm verdict — không có verdict = không có kết quả

class SynthesisProvider(Protocol):
    name: str
    is_local: bool
    def is_available(self) -> bool: ...
    def synthesize(self, question: str, sources: list[SourceDoc],
                   schema_model: type[BaseModel] | None = None) -> SynthesisResult: ...
```

### Ba hiện thực

| Provider | is_local | Ghi chú hiện thực |
|---|---|---|
| `OllamaProvider` | ✅ | Bọc `OllamaClient.generate_structured` sẵn có (temp 0, schema). Model từ env `SR_SYNTH_MODEL` — **không hard-code tên model** (bài học `gemma3:4b`→`gemma4:e4b` của M6-hotfix); model vắng trong tags → báo ồn ào, không âm thầm đổi model. |
| `GeminiFileSearchProvider` | ❌ | httpx tới Gemini File Search API: upload `SourceDoc.markdown` (đã qua §5) → hỏi có grounding → **đòi citations**; không citation = kết quả không hợp lệ. Key từ Keychain/env `GEMINI_API_KEY`; retry theo tenacity taxonomy sẵn có; circuit breaker chi phí: trần N call/ngày trong config tool. |
| `NotebookLMExporter` | — | KHÔNG phải provider (phán quyết #7). CLI sinh `staging/export/<slug>/`: các file Markdown đã `assert_sanitized` + `SOURCE_MAP.md` (1 trang: uid, title, năm, 1 câu tóm tắt, chunk overlap kề nhau theo đề xuất gốc). Người tự upload; kết quả NotebookLM quay về hệ qua đường thủ công + firewall §4 khi trích số liệu. |

### Chính sách định tuyến (phần quan trọng nhất — chép nguyên văn khi hiện thực)

```
cloud → local : TỰ ĐỘNG. Gemini lỗi/hết quota → OllamaProvider. Suy giảm riêng tư hóa,
                chỉ mất độ rộng suy luận, không mất an toàn. In cảnh báo 1 dòng.
local → cloud : KHÔNG BAO GIỜ TỰ ĐỘNG. Ollama sập không phải lý do xuất dữ liệu ra ngoài.
                Cloud chỉ chạy khi lệnh gọi mang cờ tường minh --allow-cloud, và payload
                đã qua assert_sanitized() (§5). Vi phạm nguyên tắc này = vi phạm cùng loại
                với "fake fetcher tự động" đã bị cấm từ M1.
mọi kết quả   : bất kể provider nào → qua Firewall V24 (§4); schema_model có thì thêm
                Pydantic validate — đúng học thuyết "LLM đề xuất, verifier tất định định đoạt".
```

---

## §4. Numeric Firewall V24 — ĐÃ HIỆN THỰC (`tools/guard/firewall.py`)

Đây là tổng quát hóa của verifier M6c (`verify_quote`) từ *trích dẫn văn bản* sang
*hằng số kỹ thuật*: LLM (local hay cloud) nói ra bất kỳ con số nào thì con số đó phải
tồn tại **nguyên văn** trong kho nguồn Layer A.

- **Schema**: `NumericAnchor{kind, raw, span}` với kind ∈ {complexity, ip, port,
  percentage, unit, version, number_series}; `FirewallVerdict{passed, anchors_checked,
  violations[], warnings[]}`.
- **Thuật toán**: `extract_anchors()` battery regex (O(…)/Θ/Ω, IP:port, %, đơn vị
  ms/GB/GHz/tokens…, version, port) với luật span-dài-thắng khi chồng lấn →
  `check_output(llm_output, source_texts, strict=True)`: từng anchor phải là substring
  của ≥1 nguồn sau chuẩn hóa NHẸ (chỉ whitespace/nháy/gạch — **chữ số byte-exact,
  không fuzzy, cấm cosine** — sai MỘT ký tự là từ chối toàn bộ, fail-closed).
- **strict=False**: anchor vắng nguồn hạ thành warning (dùng cho văn tổng quan);
  mismatch thì không bao giờ được tha ở bất kỳ mode nào.
- Điểm cắm: `SynthesisResult.firewall` (§3) — kết quả tổng hợp không kèm verdict là
  kết quả không tồn tại. Test: `tests/test_guards.py::TestFirewall*` (đổi 8080→8081,
  O(n log n)→O(n²), 99.9→99.8 đều bị chặn).

## §5. Outbound Interceptor — ĐÃ HIỆN THỰC (`tools/guard/outbound.py`)

Chốt chặn cuối trước socket cho MỌI payload rời máy (Gemini upload, bundle NotebookLM,
kể cả log dán tay lên cloud).

- **Battery rule tất định**: key prefix (sk-, ghp_/github_pat_, AKIA, xox?-, AIza),
  chuỗi entropy cao ≥40 ký tự (Shannon ≥4.0 bits/char — bắt token không rõ prefix),
  đường dẫn `/Users/…`·`/home/…` lộ username, IP RFC1918 + `localhost:port`, email,
  SĐT Việt Nam, chuỗi 12 số dạng CCCD (NĐ 13/2023/NĐ-CP), và dạng **gán giá trị**
  `IEEE_API_KEY=…` (nhắc *tên* biến trong tài liệu thì hợp lệ).
- **Fail-closed**: `assert_sanitized(payload)` raise `OutboundViolation` — không
  auto-redact ngầm; `redact()` là chế độ che chủ động opt-in (`«REDACTED:rule_id»`).
- **Không rò rỉ lần hai**: thông điệp lỗi/report chỉ chứa match đã che một phần;
  audit JSONL local (`staging/guard_audit.jsonl`) chỉ ghi rule_id + SHA-256 rút gọn.
- CLI pre-flight: `python tools/guard/outbound.py <file>` → exit 0/1, pipe được vào script.
- **Giới hạn khai thật**: regex bắt *định dạng*, không bắt *ngữ nghĩa* — tên người trong
  văn xuôi tự do cần tầng NER local (đề cử: model NER onnx nhỏ, chạy offline) — là phần
  mở rộng tương lai, KHÔNG phải lý do trì hoãn tầng regex đã chạy được hôm nay.

---

## §6. Lộ trình hiện thực phần còn lại & phân công

| Bước | Nội dung | Ai | Điều kiện |
|---|---|---|---|
| D31.1 ✅ | Guard firewall + outbound + 30 tests (tài liệu này §4–§5) | xong in-house | — |
| D31.2 | `tools/synthesis/provider.py` (OllamaProvider + policy router, chưa cần cloud) + NotebookLMExporter | Antygravity (spec-able: hợp đồng §3 đã đóng cứng, guard đã có test) | merge PR #2 trước để dùng chung gate |
| D31.3 | GeminiFileSearchProvider + trần chi phí | Antygravity | user cấp `GEMINI_API_KEY` vào Keychain + chốt opt-in `--allow-cloud` |
| D31.4 | Watchdog plist + rule `SESSION_STALLED` + runbook tmux vào README | Antygravity | cần Mac thật để test launchd |
| D31.5 | Docling pipeline PDF→Markdown + anchors sidecar | thiết kế riêng khi đến lượt (đụng dedup/section — cần spec cẩn thận) | sau First Light M7.1 |

**Nhắc phạm vi**: mọi thứ trong D31 là hạ tầng — không đổi phạm vi dữ liệu CS-only;
quyết định D30-S1 (y sinh) vẫn treo, không bị ảnh hưởng bởi tài liệu này.
