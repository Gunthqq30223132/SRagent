# Chạy thử SR-Agent (hệ M4) — Chủ đề "Agentic AI" (2026-07-06)

> **Yêu cầu**: chạy thử hệ thống mới (đã có lớp giám sát/tự phục hồi M4) với chủ đề: *hiện trạng công nghệ và hướng phát triển của (1) agentic engineering, (2) harness building, (3) model, (4) cách xây dựng một app có nhúng agentic AI vào hệ thống*.
>
> **Điều kiện chạy**: môi trường vẫn bị chặn mạng tới arXiv/IEEE (proxy 403) và không có Ollama → dùng bộ seed offline `demo/agentic_seed.json` (**12 bài arXiv thật**, metadata tái dựng — lần này **không có bản ghi dựng**, các tầng D34 đã demo ở lần RAG) đẩy qua pipeline thật. Khác lần trước: demo script giờ chạy **cả lớp M4** (ghi bảng `runs`, máy trạng thái alert, health snapshot) — đúng những gì `make run` thật làm. Lệnh tương đương trên Mac: `make run QUERY="llm agents harness engineering"`.

---

## Phần 1 — Kết quả chạy thử (M4 hoạt động lần đầu trên dữ liệu thật)

**Batch**: fetched=12, queued=11, rubric_rejected=1, dup/dlq=0.

**Lớp M4 làm đúng cả 3 việc mới:**

1. **Alert đúng một lần, rồi im lặng** — ngay sau batch, máy trạng thái phát đúng 1 tin:
   `🔴 OLLAMA_DEGRADED: Ollama không phản hồi — 11 tài liệu QUEUED chưa qua phân tích LLM (enrich sẽ tự chạy khi Ollama sống lại)`. Chạy `pipeline heal --now` 2 lần liên tiếp sau đó: `alerts: []` — không tin nào lặp lại (chống alarm-fatigue đã kiểm chứng trên dữ liệu thật, không chỉ unit test).
2. **Cờ suy giảm hiển thị đúng** — cả 11 doc trong queue mang badge `⚠️ chưa phân tích LLM` (suy từ `tech_meta IS NULL`, zero-touch). Người duyệt biết rõ: thiếu benchmark/limitations là *chưa kiểm tra*, không phải *không có*. Khi Ollama sống lại, `pipeline enrich` (02:00) sẽ tự bổ sung.
3. **Heartbeat** — batch được ghi vào bảng `runs` kèm standing query; heal giờ biết query nào cần chạy lại nếu nguồn sập, và rule NO_BATCH_36H có mốc để canh.

**Hàng đợi top-5** — tự nó đã kể đúng câu chuyện của chủ đề: 4/5 vị trí đầu là các bài về **harness/đánh giá agent**, không phải về model:

| # | Điểm | Bài | Ghi chú |
|---|---|---|---|
| 1 | 82.91 | **SWE-bench** (`2310.06770`) | duy nhất có cả code + dataset → artifact 100 |
| 2 | 71.62 | **OpenHands** (`2407.16741`) | platform harness mở tham chiếu |
| 3 | 71.21 | **SWE-agent** (`2405.15793`) | khai sinh khái niệm Agent-Computer Interface |
| 4 | 70.81 | **CodeAct** (`2402.01030`) | code làm action space |
| 5 | 69.59 | **AgentBench** (`2308.03688`) | đo "biết làm" tách khỏi "biết nói" |

Ngoài top-5 nhưng qua gate: ReAct, Reflexion, Generative Agents, Voyager, survey Wang, AutoGen. **Bị loại duy nhất: Toolformer** (56.55 — không công bố repo chính thức → mất 25 điểm artifact; đúng pattern rubric-phạt-bài-không-repo đã ghi nhận ở lần chạy RAG, thêm dữ liệu cho brainstorm #3). Dry-run approve bài top-1 → `approved_local`, payload 3 phần chuẩn.

---

## Phần 2 — Tổng hợp 4 nhánh (tính đến 07/2026)

*Nguồn: 12 bài seed (kiến thức model, cutoff 01/2026) + 3 vòng WebSearch 07/2026 — link cuối tài liệu.*

### 2.1 Agentic Engineering — từ prompt pattern thành ngành kỹ thuật

Xương sống khái niệm hình thành 2022–2024, toàn bộ nằm trong seed:

- **Vòng lặp điều khiển**: ReAct (2022) — xen kẽ *suy luận ↔ hành động*, nền của mọi agent loop hiện nay.
- **Tự sửa sai không cần gradient**: Reflexion (2023) — tự phản tư bằng ngôn ngữ sau thất bại, lưu vào memory; "verbal RL".
- **Kiến trúc nhận thức cho agent sống lâu**: Generative Agents (2023) — bộ ba *memory stream → reflection → planning*.
- **Kỹ năng dưới dạng code**: Voyager (2023) — skill library thực thi được, thay cho cập nhật trọng số; CodeAct (2024) — code Python là action space thống nhất (thắng JSON tool call tới 20%).

**Hiện trạng 2026**: trọng tâm dịch từ "viết prompt cho agent" sang **kỹ thuật hóa toàn bộ vòng đời** — thuật ngữ *agentic engineering* / *harness engineering* đã chuẩn hóa, với châm ngôn được cộng đồng trích dẫn rộng rãi: **"if you are not the model, you are the harness"**. Hướng nghiên cứu mới nhất là *tự động tiến hóa harness*: [Agentic Harness Engineering (arXiv 2604.25850)](https://arxiv.org/pdf/2604.25850) giữ model cố định, dùng observability để tự tối ưu system prompt, tool description, middleware, sub-agent, memory — nâng pass@1 của cùng một model gần 8 điểm qua 10 vòng lặp. Kỹ năng đóng gói (skills) cũng đang được hệ thống hóa thành kiến trúc tham chiếu ([arXiv 2606.20631](https://arxiv.org/pdf/2606.20631)).

### 2.2 Harness Building — đòn bẩy ngang hàng với model

Bằng chứng định lượng nền tảng nằm trong seed: **SWE-agent (2024)** chứng minh *cùng một model*, chỉ thay giao diện agent-máy tính (ACI: file viewer phân trang vừa context, search có giới hạn kết quả, editor có syntax-check, guardrail chống lệnh phá hoại) → SWE-bench từ 3.8% lên 12.5%. Báo cáo xu hướng 2026 của Anthropic (dẫn qua [NxCode](https://www.nxcode.io/resources/news/what-is-harness-engineering-complete-guide-2026)) ước lượng riêng cấu hình harness dịch chuyển benchmark **5+ điểm phần trăm**.

Giải phẫu một harness hiện đại (đối chiếu OpenHands trong seed + [tổng quan control plane](https://medium.com/@adnanmasood/agent-harness-engineering-the-rise-of-the-ai-control-plane-938ead884b1d)):

| Lớp | Nhiệm vụ | Ví dụ |
|---|---|---|
| Agent loop | Plan–Execute–Verify có chặn trần vòng lặp | ReAct-style, event-stream (OpenHands) |
| Action space | tool call JSON / code / shell | CodeAct, ACI |
| Sandbox | thực thi an toàn code tùy ý | Docker runtime (OpenHands, AutoGen) |
| Permissions | zero-trust, approval gate cho hành vi rủi ro | allowlist tool, human gate |
| Context management | nén, phân trang, memory dài hạn | condensation, skill library |
| Sub-agents | ủy quyền tác vụ con, cô lập context | delegation (OpenHands, AutoGen group chat) |
| Observability | trace từng bước để debug + tự tiến hóa | AHE 2026 |

Hướng phát triển: harness **composable và tự thích nghi** ([HarnessX, arXiv 2606.14249](https://arxiv.org/pdf/2606.14249)); benchmark chuyển từ SWE-bench gốc sang Terminal-Bench 2, SWE-bench Pro, và chuỗi tác vụ dài ([SWE-Chain](https://arxiv.org/pdf/2605.14415)).

### 2.3 Model — "2026 là năm model thôi làm chatbot, bắt đầu làm công nhân"

Từ WebSearch 07/2026 (nguồn cuối tài liệu):

- **Frontier**: mọi bản phát hành lớn 2026 đều lấy agentic làm năng lực trung tâm — Claude Opus 4.7/4.8 dẫn SWE-bench và tác vụ chuỗi dài, GPT-5.x Codex chạy tác vụ đa bước dài hơi, Gemini 3.x mạnh đa phương thức; computer-use vượt 70%.
- **Open-weight chạm frontier**: DeepSeek V4 (1M context, MIT), Kimi K2.6 (MoE 1T, agentic-first), GLM-5 — lần đầu open-weight đủ làm backbone agent production.
- **Đo lường**: cộng đồng đồng thuận benchmark chat không dự báo năng lực agent (AgentBench trong seed đã chỉ ra từ 2023); chuẩn 2026 là SWE-bench Pro, Terminal Bench, OSWorld Verified, BrowseComp, Toolathlon.
- **Góc nhìn cho SR-Agent (local 16GB)**: khoảng cách agentic giữa model ≤8B và frontier vẫn rất lớn — đúng với thiết kế hiện tại: model 7B local chỉ đảm nhận **trích xuất có ràng buộc schema** (structured output, temperature 0), còn *quyết định* thuộc về tầng tất định + con người. Không nên giao vòng lặp agent tự do cho model 7B.

### 2.4 Xây dựng app nhúng agentic AI — kiến trúc chuẩn 2026

Các pattern production đã hội tụ ([Composio](https://composio.dev/content/mcp-gateways-guide), [Speakeasy](https://www.speakeasy.com/mcp/using-mcp/ai-agents/architecture-patterns/), [mcp-agent](https://github.com/lastmile-ai/mcp-agent)):

1. **Chuẩn kết nối: MCP (Model Context Protocol)** — "USB-C của AI": app expose tool/resource qua MCP server (JSON-RPC 2.0; STDIO cho local, Streamable HTTP cho multi-client); agent là MCP host. App của bạn không "gọi LLM" nữa — app **trở thành bộ tool có chuẩn** để agent thao tác.
2. **Vòng lặp có biên**: Plan–Execute–Verify với trần bước lặp, timeout, budget token — không bao giờ thả vòng lặp không chặn vào production.
3. **Zero-trust tool permissions**: mặc định chặn hết, allowlist từng tool (cách tiếp cận của Claude Agent SDK); hành động không đảo ngược được → **human approval gate**.
4. **Tool thô → workflow tool**: agent gọi *một* tool, server tự dàn xếp nhiều bước bên trong, trả một kết quả có cấu trúc — giảm token, tránh lỗi trạng thái dở dang.
5. **Orchestrator cho đa agent**: một agent điều phối ủy quyền cho agent chuyên trách; thêm agent mới = sửa instruction của orchestrator, không đổi kiến trúc.
6. **Context engineering thay prompt engineering**: tool, resource, memory là công dân hạng nhất của context; gateway tập trung (auth OAuth 2.1, observability, rate limit) khi có nhiều agent/tool.

**Áp vào SR-Agent — lộ trình nhúng agent cụ thể** (SR-Agent hiện đã là "agentic-lite": heal daemon là vòng probe→decide→act tất định; LLM bị giam trong structured output — đúng chỗ):

| Bước | Việc | Pattern áp dụng |
|---|---|---|
| A1 | **SR-Agent MCP server**: expose `search_staging`, `get_document`, `get_health`, `retry_dlq`, `approve/reject (có gate)` làm MCP tools trên SQLite sẵn có | MCP STDIO local; workflow tool |
| A2 | **Reviewer copilot** trong Streamlit: agent (model local hoặc frontier qua API) dùng tools A1 để trả lời "5 bài hôm nay bài nào đáng đọc trước, vì sao?" — chỉ đọc, mọi Approve vẫn qua nút bấm của người | human gate; RAG trên kho APPROVED (báo cáo RAG, hướng (a)) |
| A3 | **Ingest agent có biên**: nâng heal thành vòng Plan–Execute–Verify nhỏ — tự mở rộng query khi kết quả nghèo, tự chọn nguồn khi một nguồn sập — trần 3 vòng, log từng quyết định vào `events` | bounded loop; observability sẵn có |
| A4 | Đo bằng chính staging: tỉ lệ Approve/Reject theo thời gian là eval nội bộ của agent | AHE-style: harness tiến hóa theo số liệu |

Nguyên tắc bất biến khi nhúng: **con người giữ chốt Approve** (triết lý gốc của SR-Agent trùng khớp với human-in-the-loop pattern 2026), và mọi hành động agent đi qua cùng error taxonomy + DLQ + alert đã có — lớp M4 chính là "observability của harness" mà AHE 2026 yêu cầu.

---

## Phần 3 — Giới hạn & cách chạy thật

1. Seed offline: 12 bài **thật** nhưng metadata tái dựng từ kiến thức model — abstract là tóm lược đại diện, cần xác minh bằng live run.
2. Không Ollama → 11 doc queue ở trạng thái degraded (đã flag đúng); trên Mac có Ollama, cùng lệnh sẽ ra đủ tech_meta + câu hỏi phản biện, hoặc `make enrich` bổ sung hồi tố.
3. Nhận định "hiện trạng 2026" phần 2.3–2.4 dựa trên WebSearch (nguồn dưới) — mức tin cậy thấp hơn bài báo đã bình duyệt; các con số benchmark cụ thể nên kiểm tra lại trước khi trích dẫn chính thức.

```bash
make run QUERY="llm agents harness engineering"     # live arXiv (+ IEEE nếu có key)
make run QUERY="agent computer interface"            # nhiều standing query — D34 tự gom
.venv/bin/python demo/rag_demo.py --seed demo/agentic_seed.json \
    --query "llm agents harness engineering" --db staging/demo_agentic.db
make ui                                              # tab Hàng đợi + tab Sức khỏe
```

---

### Nguồn WebSearch (07/2026)

- [Agentic Harness Engineering: Observability-Driven Automatic Evolution of Coding-Agent Harnesses (arXiv 2604.25850)](https://arxiv.org/pdf/2604.25850)
- [HarnessX: A Composable, Adaptive, and Evolvable Agent Harness Foundry (arXiv 2606.14249)](https://arxiv.org/pdf/2606.14249)
- [Harnessing Agent Skills: Architectural Patterns for Skill-Mediated LLM Agents (arXiv 2606.20631)](https://arxiv.org/pdf/2606.20631)
- [What Is Harness Engineering? Complete Guide (NxCode, 2026)](https://www.nxcode.io/resources/news/what-is-harness-engineering-complete-guide-2026)
- [Agent Harness Engineering — The Rise of the AI Control Plane (Medium)](https://medium.com/@adnanmasood/agent-harness-engineering-the-rise-of-the-ai-control-plane-938ead884b1d)
- [awesome-harness-engineering (GitHub)](https://github.com/ai-boost/awesome-harness-engineering)
- [Frontier AI Models 2026 (TeamDay.ai)](https://www.teamday.ai/blog/frontier-ai-models-february-2026)
- [Best AI Models 2026: Claude vs GPT-5 vs Llama 4 vs DeepSeek (Local AI Master)](https://localaimaster.com/blog/best-ai-models-2026)
- [AI Model Benchmarks Jul 2026 (LM Council)](https://lmcouncil.ai/benchmarks)
- [SWE-Chain: Benchmarking Coding Agents on Chained Package Upgrades (arXiv 2605.14415)](https://arxiv.org/pdf/2605.14415)
- [MCP Gateways: A Developer's Guide to AI Agent Architecture in 2026 (Composio)](https://composio.dev/content/mcp-gateways-guide)
- [A practical guide to the architectures of agentic applications (Speakeasy)](https://www.speakeasy.com/mcp/using-mcp/ai-agents/architecture-patterns/)
- [mcp-agent: Build effective agents using MCP (GitHub)](https://github.com/lastmile-ai/mcp-agent)
- [How to build AI agents with MCP: 12 framework comparison (ClickHouse)](https://clickhouse.com/blog/how-to-build-ai-agents-mcp-12-frameworks)
