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

## Cài đặt (macOS, Python 3.11+)

```bash
uv venv .venv && uv pip install -p .venv/bin/python -e ".[ui,dev]"
cp .env.example .env        # điền IEEE_API_KEY, NOTION_TOKEN, NOTION_PARENT_PAGE_ID
ollama pull qwen2.5:7b-instruct   # hoặc gemma3:4b (profile nhanh)
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

# Xem trạng thái staging / tái xử lý hàng lỗi
.venv/bin/python -m sr_agent.pipeline status
.venv/bin/python -m sr_agent.pipeline retry-dlq

# Mở hàng đợi duyệt (top-5 theo điểm rubric)
.venv/bin/streamlit run ui/app.py

# Test offline (không cần mạng/Ollama/Notion)
.venv/bin/python -m pytest

# Benchmark model trên máy thật
.venv/bin/python tests/bench_parser.py qwen2.5:7b-instruct gemma3:4b
```

Cron gợi ý (chạy 7h sáng hằng ngày):

```cron
0 7 * * * cd /path/to/9router && .venv/bin/python -m sr_agent.pipeline run --query "your standing query" >> staging/cron.log 2>&1
```

## Nguyên tắc thiết kế

- **Rẻ trước, đắt sau**: dedup + rubric (hard rules Python) chạy trước, LLM 7B chỉ đụng vào các bản ghi đã qua gate — tránh nghẽn ở parser trên máy 16GB RAM.
- **Cô lập lỗi từng bản ghi**: 429 → tenacity backoff (2/4/8/16s + jitter); hết lượt → DLQ `retry_eligible`; layout hỏng/schema fail → DLQ + quarantine `staging/quarantine/{uid}.raw`. Một bản ghi lỗi không bao giờ dừng batch; circuit breaker ngắt nguồn sau 3 lỗi liên tiếp.
- **Tất định ở mọi tầng lọc**: ID regex tĩnh, RapidFuzz threshold cố định, rubric là pure functions, LLM chạy temperature 0 + constrained decoding (`format=json schema`) và output vẫn phải qua Pydantic lần cuối.
- **Con người là chốt chặn cuối**: WIP 5 tài liệu/ngày, TTL 72h tự giải phóng hàng đợi tồn; APPROVED/REJECTED giữ vĩnh viễn làm audit log.
