# SR-Agent — một lệnh cho mỗi thao tác vận hành (macOS/Linux).
# Quickstart trên MacBook: make setup && make doctor && make run QUERY="..."

PY := .venv/bin/python
QUERY ?=

.PHONY: setup doctor run status retry-dlq ui test bench schedule unschedule \
        health heal enrich schedule-ops topic plan

setup:              ## tạo venv + cài deps + khởi tạo .env (không ghi đè)
	uv venv .venv
	uv pip install -p $(PY) -e ".[ui,dev]"
	cp -n .env.example .env || true
	@echo "-> Điền IEEE_API_KEY / NOTION_TOKEN / NOTION_PARENT_PAGE_ID vào .env rồi chạy: make doctor"

doctor:             ## kiểm tra tiền vận hành (env, Ollama, storage)
	$(PY) -m sr_agent.pipeline doctor

run:                ## chạy 1 batch ingest: make run QUERY="efficient transformer inference"
ifeq ($(strip $(QUERY)),)
	$(error Thiếu QUERY. Dùng: make run QUERY="your standing query")
endif
	$(PY) -m sr_agent.pipeline run --query "$(QUERY)"

topic:              ## chạy theo chủ đề qua query profile: make topic TERMS="..." [TOPIC="..."]
ifeq ($(strip $(TERMS)),)
	$(error Thiếu TERMS. Dùng: make topic TERMS="english key phrase" [TOPIC="ý định gốc"])
endif
	$(PY) tools/topic_run.py --terms "$(TERMS)" --topic "$(TOPIC)"

plan:               ## lập manifest ID để duyệt trước khi nạp: make plan TERMS="..."
ifeq ($(strip $(TERMS)),)
	$(error Thiếu TERMS. Dùng: make plan TERMS="english key phrase")
endif
	$(PY) tools/topic_run.py --terms "$(TERMS)" --topic "$(TOPIC)" --plan

status:             ## thống kê staging theo status
	$(PY) -m sr_agent.pipeline status

retry-dlq:          ## tái xử lý các bản ghi DLQ retry_eligible
	$(PY) -m sr_agent.pipeline retry-dlq

health:             ## snapshot sức khỏe + alert (exit 1 nếu có sự cố mở)
	$(PY) -m sr_agent.pipeline health

heal:               ## chạy 1 chu kỳ tự phục hồi ngay (bỏ qua cửa sổ đêm)
	$(PY) -m sr_agent.pipeline heal --now

enrich:             ## tái xử lý doc heuristic-only bằng LLM (cần Ollama)
	$(PY) -m sr_agent.pipeline enrich

ui:                 ## mở hàng đợi duyệt Streamlit (top-5 theo rubric)
	.venv/bin/streamlit run ui/app.py

test:               ## chạy toàn bộ tests offline
	$(PY) -m pytest

bench:              ## so sánh model Ollama trên máy thật (cần Ollama đang chạy)
	$(PY) tests/bench_parser.py qwen2.5:7b-instruct gemma3:4b

schedule:           ## cài launchd chạy hằng ngày 7:00: make schedule QUERY="..."
ifeq ($(strip $(QUERY)),)
	$(error Thiếu QUERY. Dùng: make schedule QUERY="your standing query")
endif
	bash scripts/install_launchd.sh "$(QUERY)"

schedule-ops:       ## cài 2 agent vận hành: heal (15 phút) + enrich (02:00)
	bash scripts/install_ops_agents.sh

unschedule:         ## gỡ toàn bộ launchd agent (daily + heal + enrich)
	bash scripts/uninstall_launchd.sh
