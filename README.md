# SR-Agent

**AI truy xuất & lọc nhiễu — Con người duyệt & phân tích sâu.**

Pipeline ETL local-first cho tài liệu Khoa học Máy tính: thu thập từ API học thuật mở, gỡ trùng tất định, chấm điểm rubric, bóc tách cấu trúc bằng LLM local (Ollama), duyệt thủ công qua Streamlit, xuất bản sang Notion.

## Kiến trúc (6 trụ cột)

```
Fetch (IEEE Xplore + arXiv)                 ── rẻ, tất định
  └─> D34 Dedup (exact ID → fuzzy title → authority tier)
        └─> Rubric Score (gate 60 điểm, JSON khai báo)
              └─> Structural Parser (Ollama 7B, structured output)   ── đắt, chạy cuối
                    └─> SQLite Staging (WIP 5/ngày · TTL 72h · DLQ)
                          └─> QC UI (Streamlit) ── Approve → Notion / Reject
```

| Thành phần | Module | Ghi chú |
|---|---|---|
| Multi-source Router | `sr_agent/ingest/` | 2 nguồn khóa cứng: IEEE (`^\d{8}$`), arXiv (`^arxiv:\d{4}\.\d{4,5}$`) |
| Dedup D34 | `sr_agent/dedup/d34.py` | RapidFuzz ratio, cutoff 93; IEEE (tier 1) thay thế arXiv (tier 2), merge metadata |
| Filtering Rubric | `sr_agent/quality/rubric.py` | 5 tiêu chí có trọng số, tất định 100%, kèm JSON Schema |
| Structural Parser | `sr_agent/parser/` | Heuristic tách section trước; LLM chỉ trích `TechnicalMetadata` + sinh 2 câu hỏi phản biện |
| Staging Store | `sr_agent/store/staging.py` | State machine `FETCHED → … → QUEUED → APPROVED/REJECTED`; DLQ; TTL purge |
| Notion Publisher | `sr_agent/publish/notion_page.py` | Trang 3 phần (Metadata / Q&A / My Notes), idempotent, dry-run |

## Quickstart trên MacBook Air M4 (16GB)

```bash
make setup                        # venv + deps + tạo .env từ template
ollama pull qwen2.5:7b-instruct   # ~4.7GB (Q4); gemma3:4b ~3.3GB (profile nhanh)
# điền IEEE_API_KEY / NOTION_TOKEN / NOTION_PARENT_PAGE_ID vào .env
make doctor                       # kiểm tra tiền vận hành — phải "sẵn sàng" mới đi tiếp
make run QUERY="efficient transformer inference"
make ui                           # mở hàng đợi duyệt
```

Cả hai model đều vừa 16GB RAM kể cả khi Streamlit + trình duyệt đang mở. `make doctor` phân biệt lỗi **bắt buộc** (chặn pipeline, exit 1) và **tùy chọn** (thiếu Ollama → chạy tất định thuần; thiếu Notion → Approve dry-run) kèm hướng khắc phục từng mục.

Cài thủ công không qua make:

```bash
uv venv .venv && uv pip install -p .venv/bin/python -e ".[ui,dev]"
cp .env.example .env        # điền IEEE_API_KEY, NOTION_TOKEN, NOTION_PARENT_PAGE_ID
```

| Env var | Bắt buộc | Mô tả |
|---|---|---|
| `IEEE_API_KEY` | để fetch IEEE thật | developer.ieee.org (miễn phí) |
| `NOTION_TOKEN` | không | thiếu → Approve chạy **dry-run** (in payload, status `APPROVED_LOCAL`) |
| `NOTION_PARENT_PAGE_ID` | khi có token | trang cha chứa các trang tài liệu |
| `OLLAMA_MODEL` | không | mặc định `qwen2.5:7b-instruct`; Ollama tắt → pipeline vẫn chạy phần tất định |
| `SR_AGENT_DB` | không | mặc định `staging/sr_agent.db` |

## Sử dụng

```bash
# Chạy 1 batch ingest (cron hằng ngày cũng gọi lệnh này)
.venv/bin/python -m sr_agent.pipeline run --query "efficient transformer inference" --max-results 20

# Xem trạng thái staging / tái xử lý hàng lỗi / kiểm tra môi trường
.venv/bin/python -m sr_agent.pipeline status
.venv/bin/python -m sr_agent.pipeline retry-dlq
.venv/bin/python -m sr_agent.pipeline doctor

# Mở hàng đợi duyệt (top-5 theo điểm rubric)
.venv/bin/streamlit run ui/app.py

# Test offline (không cần mạng/Ollama/Notion)
.venv/bin/python -m pytest

# Benchmark model trên máy thật
.venv/bin/python tests/bench_parser.py qwen2.5:7b-instruct gemma3:4b
```

## Luồng chủ đề → ID → nạp (cầu nối ngữ nghĩa, M5)

Ngữ nghĩa của con người dừng ở tầng ngoại vi `tools/topic_run.py`; mọi thứ đi vào core là **ID khớp regex tĩnh** — core (router/Pipeline/config) không đổi một dòng, per-source query đạt được bằng wrapper `ProfiledFetcher` ở tầng adapter.

```bash
# Một lệnh: terms tiếng Anh -> query riêng từng nguồn (tools/profiles/) -> pipeline thật
make topic TERMS="retrieval augmented generation" TOPIC="tổng hợp công nghệ RAG"

# Đường curation: lập manifest ID -> người xem/sửa file -> nạp
make plan TERMS="agent computer interface"          # in đường dẫn manifest
.venv/bin/python tools/topic_run.py --from-plan staging/inbox/<file>.manifest.json

# Nhờ Ollama sinh biến thể từ khóa từ chủ đề tiếng Việt (suy giảm êm nếu Ollama tắt)
.venv/bin/python tools/topic_run.py --topic "tổng hợp công nghệ RAG" --expand
```

Manifest có provenance (ID nào đến từ query nào) và mảng `rejected` — ID không khớp `ID_PATTERNS` bị chặn tại biên, kể cả khi file bị sửa tay.

## Tầng guard cho luồng cloud (D31)

Hai chốt chặn tất định tại `tools/guard/` cho mọi luồng dữ liệu chạm cloud (thiết kế đầy đủ: `docs/specs/D31-orchestration-cloud-hybrid.md`):

- **Numeric Firewall V24** (`tools/guard/firewall.py`): bóc mọi hằng số kỹ thuật trong đầu ra LLM (độ phức tạp O(…), cổng, %, đơn vị, version) và đối chiếu **nguyên văn byte-exact** với kho nguồn — sai một ký tự số là từ chối toàn bộ (fail-closed, cấm fuzzy/cosine).
- **Outbound Interceptor** (`tools/guard/outbound.py`): linter tiền-xuất chặn API key, đường dẫn lộ username, IP nội bộ, email/SĐT/CCCD (NĐ 13/2023/NĐ-CP) trước khi payload rời máy. `assert_sanitized()` fail-closed; `redact()` che chủ động opt-in; audit local không chứa secret. CLI: `python tools/guard/outbound.py <file>` (exit 0/1).

## Lịch chạy hằng ngày: launchd, không phải cron

Trên macOS, **cron không chạy khi máy ngủ/gập nắp** — với MacBook Air thì job 7h sáng gần như không bao giờ nổ. Dùng launchd LaunchAgent: máy ngủ qua giờ hẹn thì job **tự chạy bù ngay khi thức dậy**.

```bash
make schedule QUERY="your standing query"   # cài com.sragent.daily, chạy 7:00 hằng ngày
launchctl kickstart gui/$(id -u)/com.sragent.daily   # chạy thử ngay không đợi 7h
tail -f staging/launchd.log                 # xem log
make unschedule                             # gỡ
```

Script cài đặt tự chạy `doctor` trước — check bắt buộc nào fail thì dừng, không cài lịch trên máy chưa sẵn sàng. Đổi query chỉ cần chạy lại `make schedule` (idempotent).

## Giám sát & tự phục hồi (M4)

```bash
make health          # snapshot + alert; exit 1 nếu có sự cố mở (dùng được trong script)
make heal            # 1 chu kỳ tự phục hồi ngay (probe -> retry DLQ -> enrich)
make enrich          # tái xử lý doc heuristic-only bằng LLM (cần Ollama)
make schedule-ops    # cài 2 agent nền: heal (15 phút/lần) + enrich (02:00 hằng đêm)
```

- **Báo động chống alarm-fatigue**: máy trạng thái alert chỉ notify khi *chuyển* trạng thái — một tin 🔴 khi sự cố mở (nguồn sập / DLQ tăng đột biến / Ollama sập kèm doc chưa phân tích / 36h không có batch), im lặng khi đang mở, một tin 🟢 khi hồi phục. Sink: Notification Center macOS (mặc định) + `ALERT_WEBHOOK_URL` tùy chọn (ntfy.sh/Slack/Discord — xem `.env.example`).
- **Tự phục hồi**: agent `com.sragent.heal` chạy 15 phút/lần (và ngay khi máy thức dậy) — probe mạng nguồn + Ollama; hạ tầng sống lại thì tự chạy lại standing query cho nguồn từng sập, `retry-dlq` bản ghi lẻ (fail thì tăng `attempts`, trần 5 lần), và enrich trong cửa sổ đêm.
- **Cờ suy giảm**: doc QUEUED xử lý khi Ollama sập có badge ⚠️ "Chưa phân tích LLM" trong UI (suy trực tiếp từ `tech_meta IS NULL`, không thêm cột nào) — người duyệt không nhầm "chưa kiểm tra" với "không có artifact". `pipeline enrich` bổ sung phần LLM cho các doc này khi Ollama hoạt động.
- **Dashboard**: tab "🩺 Sức khỏe hệ thống" trong chính Streamlit UI.

## Nguyên tắc thiết kế

- **Rẻ trước, đắt sau**: dedup + rubric (hard rules Python) chạy trước, LLM 7B chỉ đụng vào các bản ghi đã qua gate — tránh nghẽn ở parser trên máy 16GB RAM.
- **Cô lập lỗi từng bản ghi**: 429 → tenacity backoff (2/4/8/16s + jitter); hết lượt → DLQ `retry_eligible`; layout hỏng/schema fail → DLQ + quarantine `staging/quarantine/{uid}.raw`. Một bản ghi lỗi không bao giờ dừng batch; circuit breaker ngắt nguồn sau 3 lỗi liên tiếp.
- **Tất định ở mọi tầng lọc**: ID regex tĩnh, RapidFuzz threshold cố định, rubric là pure functions, LLM chạy temperature 0 + constrained decoding (`format=json schema`) và output vẫn phải qua Pydantic lần cuối.
- **Con người là chốt chặn cuối**: WIP 5 tài liệu/ngày, TTL 72h tự giải phóng hàng đợi tồn; APPROVED/REJECTED giữ vĩnh viễn làm audit log.
