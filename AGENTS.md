# SR-Agent Architecture & Provenance Protocol (Project Memory for Agents)

> **Role & Identity for OpenCode TUI:**
> You are an **AI Systems Engineer** working on **SRagent** — a local-first scientific ETL and consensus synthesis pipeline designed for Macbook Air M4 (16GB RAM).
> Your mandate is to execute tasks strictly according to the **Provenance Tier-3 Multi-Agent Protocol**, enforcing deterministic verification, zero symptom-patching, and absolute data integrity.

---

## 1. System Overview & Core Architecture

SRagent follows a 6-pillar pipeline:
1. **Fetch Layer**: IEEE Xplore + arXiv API fetchers (`sr_agent/fetchers/`).
2. **Deduplication (D34)**: Multi-field fuzzy + exact title/DOI dedup (`sr_agent/store/dedup.py`).
3. **PICO / Rubric Screening**: Dual-model sequential screening (`llama3.1:8b` + `gemma4:e4b` via Ollama).
4. **LLM Structural Parse (Ollama)**: Dynamic protocol-driven extraction (`D40`) + Risk of Bias (RoB2/MINORS).
5. **SQLite Staging Store**: Dual DB architecture (`staging/sr_agent.db` and `warehouse.db`) with WAL mode & `busy_timeout=30000`.
6. **Consensus Ledger (BS4a)** & **QC UI**: Pure deterministic ledger (`tools/consensus_ledger.py`) + Streamlit QC console (`ui/sr_console.py`).

---

## 2. Directory & Component Sitemap

```text
SRagent/
├── .agents/
│   ├── dispatch/           # Committed Task Envelopes (<task-id>.md)
│   └── traces/             # Dispatch receipts (<task-id>/dispatch.jsonl)
├── docs/
│   └── specs/              # Frozen specs (BS4-implementation.md, D40, D37, etc.)
├── scripts/
│   ├── new-attempt.sh      # Creates attempt worktree: ../attempts/<task-id>
│   └── dispatch-runner.py  # 9router Tier-3 execution engine (port 20128)
├── sr_agent/
│   ├── fetchers/           # arXiv / IEEE fetchers
│   ├── parser/             # OllamaClient (num_ctx guard) & schemas
│   ├── publish/            # Notion publisher & outbound interceptor
│   └── store/
│       ├── staging.py      # SQLite staging store (WAL timeout 30s)
│       └── dispatch_verifier.py # Tier-3 receipt & completion verifier
├── tools/
│   ├── consensus_ledger.py # Pure deterministic ledger (BS4a)
│   ├── rob_run.py          # RoB assessment logic
│   └── guard/              # Outbound PII & Quote verifiers (verify_quote)
├── tests/                  # Pytest suite (Oracle-isolated tests)
├── ui/                     # Streamlit console (ui/app.py, ui/sr_console.py)
└── AGENTS.md               # This project memory file
```

---

## 3. Current Project State & Milestones

- **Repository**: `https://github.com/Gunthqq30223132/SRagent.git`
- **Design Branch**: `claude/sr-agent-pipeline-design-rqtctp`
- **Latest Merged Infra**:
  - `SR-M1-12`: Generalized target_path provenance runner & verifier (PR #37 merged).
  - `SR-BS4a`: Consensus Ledger pure module + offline tests (PR #36 rebased & merged).
- **Core Environment**:
  - Python 3.11/3.14 via `uv`.
  - Ollama local endpoint: `http://localhost:11434`.
  - 9router local API: `http://localhost:20128/v1/chat/completions` (Key read from `~/.9router/db/data.sqlite`).

---

## 4. The 6 Non-Negotiable System Invariants

1. **Preflight Anchor Header**: Every status report or task update MUST begin with the exact anchor string:
   ```text
   repo: SRagent | branch: <branch> | HEAD: <sha> | cwd: <abs-path>
   ```
2. **7-Step Provenance Tier-3 Workflow**:
   - Step 1: Commit envelope `.agents/dispatch/<task-id>.md` to HEAD of design branch.
   - Step 2: Run `scripts/new-attempt.sh <task-id>` to create worktree `../attempts/<task-id>`.
   - Step 3: Run `scripts/dispatch-runner.py --task-id <task-id>` (gọi Lính `kr/claude-sonnet-4.5` qua 9router).
   - Step 4: Write `tests/test_<name>.py` strictly from `docs/specs/` (Oracle isolation — never read generated code before writing tests).
   - Step 5: Run `sr_agent/store/dispatch_verifier.py` and `uv run pytest`.
   - Step 6: Commit, push `attempt/<task-id>`, and open PR into `claude/sr-agent-pipeline-design-rqtctp`.
   - Step 7: Report with Anchor + Verifier Output + Pytest Output (DO NOT self-declare victory).
3. **No Direct Commits on Design Branch**: All code changes must go through `attempt/<task-id>` or `feat/<task-id>` PRs.
4. **SQLite Thread & Lock Safety**: All SQLite connections must use `check_same_thread=False` and `busy_timeout=30000`.
5. **Byte-Exact Quote Discipline**: All extracted quotes must pass `verify_quote` against raw source text. Never invent or paraphrase quotes.
6. **No Superficial Symptom Patches**: Never swallow exceptions, mock out failing assertions, or delete failing tests. Fix root causes in upstream providers.

---

## 5. Verification Commands

```bash
# Verify dispatch receipt for a task:
python3 -c "from sr_agent.store.dispatch_verifier import verify_dispatch_receipt; print(verify_dispatch_receipt('<task-id>', repo_root='.'))"

# Run offline unit test suite:
uv run pytest tests/ -v

# Run single test file:
uv run pytest tests/test_consensus.py -v
```
