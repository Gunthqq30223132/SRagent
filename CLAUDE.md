# SR-Agent (repo AnesthOS) — luật cho agent làm việc trong repo này

## Bản chất repo — ĐỌC TRƯỚC KHI LÀM GÌ
Đây là **SR-Agent**: pipeline systematic review bằng **Python 3.13 + Ollama + SQLite +
Streamlit** (local-first, MacBook Air M4 16GB). Đây KHÔNG phải app Next.js — bộ luật
Next.js/TypeScript/tính liều của app lâm sàng AnesthOS thuộc về repo app riêng và
KHÔNG áp dụng ở đây (một commit sync từng chép nhầm bộ luật đó vào đây, 2026-07-11).

## Lệnh chuẩn
- `make setup` — tạo venv + cài deps (uv)
- `.venv/bin/python -m pytest` — toàn bộ test offline (baseline ghi trong
  `docs/runbooks/M7.1-first-light.md` GĐ0)
- `bash scripts/gate_m6.sh && bash scripts/gate_d32.sh` — hai gate bắt buộc
- `make ui` — hàng đợi duyệt Streamlit · `make doctor` — kiểm tra tiền vận hành

## Bất biến cứng (vi phạm = thay đổi bị từ chối)
1. **Không dependency runtime mới** — parser/so sánh viết tay có chủ đích.
2. **CẤM cosine/fuzzy trong mọi đường verification** — chỉ exact/verify_quote;
   cosine duy nhất được phép ở vai trò recall trong `tools/compliance/kb.py`.
3. `sr_agent/` core (router/config/Pipeline/schemas/DocStatus) **topic-blind** —
   ngữ nghĩa miền (y khoa, chủ đề) nằm trong PROTOCOL JSON và data, không trong code.
4. `tools/guard/` + `pyproject.toml` **zero-touch** (gate D2 sẽ chặn).
5. LLM local qua Ollama: **temperature 0 + structured output**; output không hợp lệ
   = verdict VOID — không bao giờ "sửa lại cho khớp".
6. **Con người duyệt là bất biến nền**: cấm mọi hình thức giả lập thao tác người
   (script bấm Approve, ghi tay trạng thái duyệt vào DB).
7. Dữ liệu bệnh nhân/PII **tuyệt đối ngoài phạm vi** — hệ chỉ xử lý văn liệu đã
   xuất bản; Outbound Interceptor áp lên mọi luồng ra ngoài.

## Quy trình giao nhận
- Mọi thay đổi code: nhánh feature → **PR** vào `claude/sr-agent-pipeline-design-rqtctp`
  → CI xanh → merge. **CẤM push thẳng nhánh design** — kể cả script backup tự động
  (script sync của trạm dev phải trỏ về nhánh `backup/*` riêng).
- Báo cáo hoàn thành phải kèm URL PR + output nguyên văn; số phải đo, không tự khai.
- Khung mandate cho executor: `docs/runbooks/executor-mandate.md`.

## Cấu hình screening song thẩm (chốt sau hiệu chuẩn M7.2, 2026-07-11)
- `SR_SCREEN_MODEL_A=llama3.1:8b` · `SR_SCREEN_MODEL_B=gemma4:e4b` — hai screener
  PHẢI khác model. Hồ sơ hiệu chuẩn: `docs/runs/2026-07-11-m72-calibration.md`.
