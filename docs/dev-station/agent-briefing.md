# AnesthOS Dev Station — Agent Handoff Briefing

> **Purpose**: This document provides all context an AI agent needs to operate on, maintain, or extend the AnesthOS Local AI Dev Station.  
> **Last verified**: 2026-07-12T09:30 ICT  
> **Device**: MacBook Air M4, 16GB RAM, macOS Tahoe 26.3.1  
> **User**: gun (GitHub: gunthqq30223132)

---

## System Overview

AnesthOS is a medical anesthesia application (Next.js + SQLite) with an AI-assisted development station running entirely on-device. The station routes all AI requests through a local proxy (OmniRoute) that cascades through cloud providers with a local LLM fallback for offline operation.

### Architecture

```
Claude Code CLI ──→ OmniRoute (localhost:20128) ──→ Provider Chain
                                                     ├─ 1. Kiro AI (kr/claude-sonnet-4.5)
                                                     ├─ 2. Antigravity (ag/claude-sonnet-4-6)
                                                     ├─ 3. Antigravity (ag/gemini-2.5-pro)
                                                     └─ 4. Ollama Local (ollama/qwen2.5:7b-instruct)
```

Strategy: `priority` — try providers 1→4 sequentially until one responds successfully.

---

## File System Map

```
~/projects/AnesthOS/                    # Project root (APFS internal SSD)
├── CLAUDE.md                           # Project memory (31 lines, clinical rules)
├── .githooks/
│   ├── pre-commit                      # Shell wrapper
│   └── pre-commit-checker.py           # PII/secrets/dependency scanner
├── .anesthos/specs/                    # Medical specification files (source of truth)
├── scripts/
│   └── anesthos-sync.sh               # Pull/push sync + backup script
├── .git/                              # Git repo → github.com/gunthqq30223132/9router
└── [project files: sr_agent/, tests/, docs/, etc.]

~/.claude/profiles/anesthos/            # Isolated Claude Code profile
├── settings.json                       # API endpoint + model config
├── settings.local.json                 # Read permissions
├── .gitattributes                      # merge=union for .jsonl
├── .git/                              # Git repo → github.com/gunthqq30223132/AnesthOS-AI-History
└── [*.jsonl chat history files]

~/.omniroute/                           # OmniRoute config + data
├── storage.sqlite                      # Main database (combos, connections, logs)
├── .env                                # Environment variables
├── .env.secrets                        # Credentials (excluded from iCloud)
├── health.log                          # Health agent log
├── restarts.log                        # Restart timestamp log
├── omniroute.log                       # Server stdout/stderr
└── logs/application/app.log            # Structured application log

~/scripts/
└── omniroute-health.sh                 # Health check + auto-restart script

~/Library/LaunchAgents/
└── com.anesthos.omniroute-health.plist  # launchd agent (runs every 300s)

~/Library/Mobile Documents/com~apple~CloudDocs/Backups/omniroute/
└── [iCloud-synced mirror of ~/.omniroute/]
```

---

## Critical Configuration

### OmniRoute SQLite Schema (Key Tables)

**`combos`** — routing rule definitions:
```sql
SELECT id, data FROM combos WHERE id = 'anesthos-brain';
-- data is JSON: {"id","name","models":["kr/...","ag/...","ollama/..."],"strategy":"priority"}
```

**`provider_connections`** — credentials per provider:
```sql
SELECT id, provider, is_active, test_status, api_key, provider_specific_data
FROM provider_connections WHERE provider = 'ollama-local';
-- ollama-local-conn | ollama-local | 1 | ok | ollama | {"baseUrl":"http://localhost:11434/v1"}
```

> [!IMPORTANT]
> For local providers (ollama-local, lm-studio, etc.), the `baseUrl` MUST be stored inside the `provider_specific_data` JSON column — NOT in `provider_nodes.base_url`. This is the only source OmniRoute reads for the actual endpoint URL.

**`provider_nodes`** — custom endpoint definitions (NOT needed for built-in providers like `ollama-local`):
```sql
-- Node IDs for custom nodes MUST start with "openai-compatible-" prefix
-- Built-in providers (ollama-local, lm-studio, etc.) do NOT need entries here
```

### Environment Variables

| Variable | Value | Where |
|----------|-------|-------|
| `CLAUDE_CONFIG_DIR` | `~/.claude/profiles/anesthos` | Set by `anesthos-start` alias |
| `ANTHROPIC_BASE_URL` | `http://localhost:20128/v1` | In profile `settings.json` |
| `ANTHROPIC_AUTH_TOKEN` | `sk-anesthos-brain-token` | In profile `settings.json` |
| `PORT` | `20128` | OmniRoute startup |
| `DATA_DIR` | `~/.omniroute` | OmniRoute startup |

### Git Remotes

| Repo | Remote URL | Purpose |
|------|-----------|---------|
| `~/projects/AnesthOS` | `git@github.com:gunthqq30223132/9router.git` | Source code |
| `~/.claude/profiles/anesthos` | `git@github.com:gunthqq30223132/AnesthOS-AI-History.git` | AI chat logs |

---

## Constraints & Rules

### Code Safety (enforced by CLAUDE.md + pre-commit hook)
1. **NO PII/PHI** may leave the device — zero tolerance
2. **Clinical math**: native `Math.*` only — NO npm math packages
3. **LaTeX documentation**: all dosage formulas must include LaTeX comments
4. **Dependency whitelist**: Next.js, TailwindCSS, Radix UI, Lucide React, SQLite native
5. **No plagiarism**: do not copy clinical/business logic from open-source repos
6. **Medical rules**: all rules must derive from `.anesthos/specs/` files

### Infrastructure Safety (enforced by scripts)
1. **NEVER delete original data** — archive by renaming to `*.archived`
2. **macOS BSD compatibility**: all shell scripts use `#!/bin/sh`, BSD `sed -i ''`, no GNU-isms
3. **iCloud exclusion**: `.env.secrets` must NEVER sync to iCloud

---

## Services & Ports

| Service | Port | Binary | Auto-start? |
|---------|------|--------|------------|
| OmniRoute | 20128 | `/Users/gun/.nvm/versions/node/v25.9.0/bin/omniroute` | Via health agent (launchd) |
| Ollama | 11434 | `ollama serve` | Via Ollama.app (if installed) |
| Health Agent | — | `~/scripts/omniroute-health.sh` | Via launchd (every 300s) |

### Starting OmniRoute Manually

```bash
PORT=20128 DATA_DIR="$HOME/.omniroute" OMNIROUTE_MAX_PENDING_MIGRATIONS=0 \
  nohup /Users/gun/.nvm/versions/node/v25.9.0/bin/omniroute > "$HOME/.omniroute/omniroute.log" 2>&1 &
```

### Verifying System Health

```bash
# OmniRoute responds
curl -s -o /dev/null -w "%{http_code}" http://localhost:20128/v1/models
# Expected: 200

# Ollama responds
curl -s http://localhost:11434/api/ps | python3 -c "import sys,json; print(json.load(sys.stdin))"
# Expected: {"models": [...]}

# Combo fallback works
curl -s -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-anesthos-brain-token" \
  -d '{"model":"anesthos-brain","messages":[{"role":"user","content":"hi"}],"max_tokens":1}' \
  http://localhost:20128/v1/chat/completions
# Expected: SSE stream with model response
```

---

## Known Issues & Workarounds

### OmniRoute Connection Gets Stuck in "expired" State
When a connection receives a 401 error, OmniRoute sets `test_status='expired'` and `error_code=401.0`. This state persists across restarts.

**Fix**:
```sql
sqlite3 ~/.omniroute/storage.sqlite \
  "UPDATE provider_connections SET test_status='ok', error_code=NULL, last_error=NULL WHERE id='ollama-local-conn';"
```

### Health Agent Enters Alert-Only Mode
After 3+ OmniRoute restarts within 1 hour, the health agent stops restarting and only sends macOS notifications.

**Fix**: Wait 1 hour for the counter to reset, or manually clear:
```bash
echo "" > ~/.omniroute/restarts.log
```

### Ollama Model Takes 5-10s to Load
When `qwen2.5:7b-instruct` is not in memory, first request triggers model loading from disk (SSD → RAM). Subsequent requests respond in ~180ms.

**Preload**: `curl -s http://localhost:11434/api/generate -d '{"model":"qwen2.5:7b-instruct","prompt":"warmup","options":{"num_predict":1}}'`

---

## Remaining Tasks (from MANDATE DEV-STATION-01)

| ID | Task | Priority | Status |
|----|------|----------|--------|
| R1 | Migrate repo off exFAT SSD to internal APFS | P0 | ✅ Done (verified: APFS filesystem) |
| R2 | Seal credential leaks (scan .jsonl history, isolate secrets from iCloud) | P0 | ⏳ Pending |
| R3 | Version-controlled hooks (.githooks/) | P1 | ✅ Done |
| R4 | Anti-conflict for history repo (merge=union + ff-only + awk dedupe) | P1 | ⏳ Partial (.gitattributes exists, sync script not updated) |
| R5 | OmniRoute health check agent (launchd) | P1 | ✅ Done (script + plist deployed) |
| R6 | Local Ollama fallback routing | P0 | ✅ Done + Verified |

### R2 Details (Next Priority)
- Scan all `.jsonl` files in `~/.claude/profiles/anesthos/` for leaked secrets/PII
- Move credentials out of `~/.omniroute/` files that sync to iCloud
- Ensure `.env.secrets` is excluded from iCloud backup path
- Run `pre-commit-checker.py --scan` on history files

### R4 Details
- `~/.claude/profiles/anesthos/.gitattributes` already has `*.jsonl merge=union`
- `anesthos-sync.sh` needs update: `git pull --ff-only` + `awk '!seen[$0]++'` dedupe step

---

## Quick Reference Commands

```bash
# Start coding session
anesthos-start

# End coding session
# (in Claude Code) /exit
anesthos-save

# Restart OmniRoute
kill $(lsof -t -sTCP:LISTEN -i :20128) 2>/dev/null
PORT=20128 DATA_DIR=~/.omniroute nohup omniroute > ~/.omniroute/omniroute.log 2>&1 &

# Check system status
curl -s localhost:20128/v1/models | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin)['data'][:5]]"

# View health log
tail -20 ~/.omniroute/health.log

# Reset stuck Ollama connection
sqlite3 ~/.omniroute/storage.sqlite "UPDATE provider_connections SET test_status='ok', error_code=NULL WHERE provider='ollama-local';"
```
