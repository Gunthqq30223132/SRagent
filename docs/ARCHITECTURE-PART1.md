# AnesthOS Architecture — Complete System Documentation

> **Version**: 2.0  
> **Date**: 2026-07-12  
> **Status**: PRODUCTION (with known gaps — see Critical Findings)  
> **Purpose**: Full technical context for AI agents and human maintainers  

---

## Executive Summary

AnesthOS Dev Station is a **local-first AI development environment** for building medical software with strict safety constraints. All AI interactions route through a self-hosted proxy (OmniRoute) that cascades across 4 providers with offline fallback.

**Key Properties**:
- **Zero PII/PHI Exfiltration**: Medical data never leaves device
- **Offline Capable**: Local LLM fallback when internet unavailable
- **Self-Healing**: Health agent auto-restarts failed services
- **Audit Trail**: All AI conversations version-controlled in private repo

---

## System Identity & Purpose

### Project Naming Confusion ⚠️

The repository shows **TWO DISTINCT PROJECTS** merged into one:

1. **SR-Agent** (original): Academic paper retrieval pipeline (IEEE Xplore + arXiv)
   - Evidence: `sr_agent/` folder, `README.md`, `pyproject.toml`
   - Purpose: ETL pipeline for Computer Science papers → Notion
   - Tech: Python, Ollama, SQLite, Streamlit

2. **AnesthOS** (intended): Medical anesthesia application
   - Evidence: `CLAUDE.md`, `.anesthos/specs/`, project name
   - Purpose: Clinical decision support for anesthesiologists
   - Tech: Next.js, TypeScript, SQLite, TailwindCSS

**Current State**: The repo is a **development station configuration** with SR-Agent code as placeholder. No actual AnesthOS medical code exists yet.

**Implication for AI Agents**:
- Do NOT assume medical features exist based on project name
- Clinical rules in `CLAUDE.md` are **future constraints**, not descriptions of existing code
- `.anesthos/specs/` folder is empty (only `.keep` file)

---

## Architecture Layers

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1: Human Interface                                    │
│  - OpenCode CLI (Claude Code fork)                          │
│  - Antigravity IDE (alternative)                            │
└─────────────────────────────────────────────────────────────┘
                            ↓ HTTP
┌─────────────────────────────────────────────────────────────┐
│  Layer 2: Request Router                                     │
│  - OmniRoute v3.8.46 (localhost:20128)                      │
│  - Combo: anesthos-brain (priority strategy)                │
└─────────────────────────────────────────────────────────────┘
                            ↓ Sequential Fallback
┌─────────────────────────────────────────────────────────────┐
│  Layer 3: Model Providers (Priority Order)                  │
│  1. Kiro AI        kr/claude-sonnet-4.5     (Free, Primary) │
│  2. Antigravity    ag/claude-sonnet-4-6     (Paid, Backup)  │
│  3. Antigravity    ag/gemini-2.5-pro        (Large Context) │
│  4. Ollama Local   ollama/qwen2.5:7b        (Offline)       │
└─────────────────────────────────────────────────────────────┘
                            ↓ Monitoring
┌─────────────────────────────────────────────────────────────┐
│  Layer 4: Resilience                                         │
│  - Health Agent (launchd, 5min interval)                    │
│  - Auto-restart (max 3/hour)                                │
│  - macOS Notification Center alerts                         │
└─────────────────────────────────────────────────────────────┘
                            ↓ Backup
┌─────────────────────────────────────────────────────────────┐
│  Layer 5: Persistence                                        │
│  - GitHub: 9router (source code)                            │
│  - GitHub: AnesthOS-AI-History (chat logs)                  │
│  - iCloud Drive: OmniRoute config                           │
└─────────────────────────────────────────────────────────────┘
```

---

## Component Deep Dive

### 1. OmniRoute — Request Proxy

| Property | Value |
|----------|-------|
| **Version** | 3.8.46 |
| **Binary** | `/Users/gun/.nvm/versions/node/v25.9.0/bin/omniroute` |
| **Port** | 20128 (hardcoded) |
| **Protocol** | OpenAI-compatible REST API |
| **Data Directory** | `~/.omniroute/` → symlink → iCloud Drive |
| **Database** | SQLite with WAL mode |
| **Process Manager** | None (managed by health agent) |

**Configuration Structure**:
```
~/.omniroute/
├── storage.sqlite          # Main DB (combos, connections, logs)
├── storage.sqlite-shm      # Shared memory (WAL mode)
├── storage.sqlite-wal      # Write-ahead log (active writes)
├── .env                    # PORT, DATA_DIR
├── .env.secrets            # API keys (⚠️ SYMLINKS to iCloud!)
├── health.log              # Health check results
├── restarts.log            # Restart timestamps (last hour)
├── omniroute.log           # Server stdout/stderr
└── logs/application/app.log # Structured JSON logs
```

**Critical Finding #1: Secrets in iCloud**
```bash
# Current state (INSECURE):
~/.omniroute/.env.secrets → ~/Library/Mobile Documents/.../omniroute/local.nosync/.env.secrets
```
Despite `local.nosync` name, the file is INSIDE iCloud Drive folder. Apple syncs the symlink target. Need to:
1. Move secrets OUTSIDE iCloud entirely: `~/Library/Application Support/AnesthOS/secrets.env`
2. Update OmniRoute to read from new location
3. Add `secrets.env` to `.gitignore` in all repos

**Startup Command**:
```bash
PORT=20128 \
DATA_DIR="$HOME/.omniroute" \
OMNIROUTE_MAX_PENDING_MIGRATIONS=0 \
nohup omniroute > "$HOME/.omniroute/omniroute.log" 2>&1 &
```

**API Endpoints**:
- `GET /v1/models` — List available models + combos
- `POST /v1/chat/completions` — Streaming chat (SSE)
- `GET /health` — Basic health check

**Combo Configuration**:
```sql
-- Query actual combo config
SELECT id, name, strategy, data FROM combos WHERE id = 'anesthos-brain';
-- Result: (empty) — CRITICAL FINDING #2
```

**Critical Finding #2: Combo Data Not Found**
The briefing claims combo exists, but SQLite returns no rows. Possible causes:
1. Combo stored in different table (check `provider_connections`)
2. In-memory config not persisted
3. OmniRoute using file-based config instead of SQLite

**Action Required**: Query OmniRoute API directly to verify runtime config:
```bash
curl -s http://localhost:20128/v1/models | jq '.data[] | select(.id=="anesthos-brain")'
```

---

### 2. OpenCode CLI — Development Interface

| Property | Value |
|----------|-------|
| **Binary** | `/Users/gun/.local/bin/claude` (wrapper script) |
| **Actual Tool** | `opencode` (Claude Code fork) |
| **Profile** | `~/.claude/profiles/anesthos/` |
| **Isolation Method** | `CLAUDE_CONFIG_DIR` environment variable |

**Profile Structure**:
```
~/.claude/profiles/anesthos/
├── settings.json              # API endpoint, model selection
├── settings.local.json        # Read permissions (external volumes)
├── history.jsonl              # Current session chat log
├── .gitattributes             # *.jsonl merge=union
├── .git/                      # Git repo → AnesthOS-AI-History
└── [other *.jsonl files]      # Previous sessions
```

**settings.json**:
```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "http://localhost:20128/v1",
    "ANTHROPIC_AUTH_TOKEN": "sk-anesthos-brain-token",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "anesthos-brain",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "anesthos-brain",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "anesthos-brain"
  },
  "model": "anesthos-brain"
}
```

All model tiers → same combo → OmniRoute decides actual provider.

**settings.local.json** (permissions):
```json
{
  "permissions": {
    "allow": [
      "Read(//Volumes/**)",
      "Read(//Volumes/Gun SSD/**)",
      "WebFetch(domain:www.gmetrix.net)"
    ]
  }
}
```

---

### 3. Ollama — Local LLM Fallback

| Property | Value |
|----------|-------|
| **Version** | Latest (app-managed) |
| **Port** | 11434 |
| **API** | OpenAI-compatible `/v1/chat/completions` |
| **Models Installed** | qwen2.5:7b-instruct (4.7GB), gemma2:9b (5.4GB), llama3.1:8b (4.9GB), gemma4:e4b (9.6GB) |
| **Active Model** | qwen2.5:7b-instruct (lazy-loaded on first request) |
| **Startup** | Automatic via Ollama.app (Login Items) |

**Connection in OmniRoute**:
```sql
SELECT id, provider, test_status, provider_specific_data 
FROM provider_connections 
WHERE provider = 'ollama-local';
-- Expected: ollama-local-conn | ollama-local | ok | {"baseUrl":"http://localhost:11434/v1"}
```

**Critical Finding #3: Query Returns Empty**
Same issue as combo — connection not visible in SQLite despite working in practice.

**Model Loading Behavior**:
- Cold start: 5-10 seconds (disk → RAM)
- Warm: ~180ms response time
- Memory footprint: ~6GB RAM for 7B model

**Pre-warming Strategy** (recommended):
```bash
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen2.5:7b-instruct","prompt":"warmup","options":{"num_predict":1}}'
```

---

### 4. Health Agent — Self-Healing Service

| Property | Value |
|----------|-------|
| **Script** | `~/scripts/omniroute-health.sh` |
| **Scheduler** | launchd (`com.anesthos.omniroute-health.plist`) |
| **Interval** | 300 seconds (5 minutes) |
| **Run at Boot** | Yes (`RunAtLoad: true`) |

**Health Check Logic**:
```
Every 5 minutes:
  1. HTTP 200 check: GET /v1/models (timeout 5s)
  
Every 60 minutes (hourly):
  2. End-to-end test: POST /v1/chat/completions with "hi" (timeout 10s)
  
If any check fails:
  3. Count restarts in last 60 minutes
  4. If < 3 restarts:
       - Log restart event
       - Send macOS notification (Submarine sound)
       - Kill OmniRoute (pkill + PID file)
       - Start new OmniRoute process
     Else:
       - Log "alert-only mode"
       - Send ALARM notification (Basso sound)
       - Do NOT restart (prevent flapping)
```

**Restart Counter Reset**:
- Automatic: Entries older than 3600s purged from `restarts.log`
- Manual: `echo "" > ~/.omniroute/restarts.log`

**Logs**:
- Health results: `~/.omniroute/health.log`
- Agent stdout: `~/.omniroute/health_stdout.log`
- Agent stderr: `~/.omniroute/health_stderr.log`

**Critical Finding #4: No Ollama Health Check**
Health agent only checks OmniRoute. If Ollama crashes, fallback silently fails with 503 errors. Should add:
```bash
if ! curl -s -m 2 http://localhost:11434/api/ps > /dev/null; then
  echo "⚠️ Ollama not responding" >> "$LOG_FILE"
  # Attempt restart via launchctl or open -a Ollama
fi
```

---

### 5. Sync Script — Backup Orchestrator

**Location**: `~/projects/AnesthOS/scripts/anesthos-sync.sh` (238 lines, POSIX sh)

**Modes**:
- `pull`: Update local code + AI history from GitHub
- `push`: Commit + push code + AI history to GitHub

**Pre-flight Checks** (both modes):
1. `~/projects/AnesthOS` directory exists
2. GitHub SSH authentication works (`ssh -T git@github.com`)
3. Claude/OpenCode process NOT running (⚠️ warning only, not blocking)

**Pull Mode Sequence**:
```bash
1. git pull --ff-only in ~/projects/AnesthOS (fast-forward only)
2. git pull in ~/.claude/profiles/anesthos (allow merge)
3. Dedupe .jsonl files with awk '!seen[$0]++'
```

**Push Mode Sequence**:
```bash
1. Stage all AI history files
2. Run pre-commit secret scan (scan-history-secrets.py or pre-commit-checker.py)
   - If secrets found: BLOCK push, exit 1
3. Commit AI history with timestamp
4. Push AI history to GitHub
5. Stage all source code files
6. Commit source code with timestamp (--no-verify flag)
7. Push source code to GitHub
8. Run backup-to-ssd.sh if exists
```

**Critical Finding #5: Race Condition Still Exists**
Line 64-66:
```bash
if pgrep -x claude >/dev/null 2>&1; then
  echo "⚠️ Claude Code process running..."
  exit 0  # ← Should be exit 1
fi
```
Currently exits cleanly (success), allowing higher-level scripts to proceed. Should FAIL to prevent `.jsonl` corruption.

**Git Configuration for AI History**:
- Remote: `git@github.com:gunthqq30223132/AnesthOS-AI-History.git`
- Branch: `main` (forced via `git branch -M main`)
- Merge strategy: `merge=union` in `.gitattributes`
- Conflict handling: Deduplication AFTER merge (awk one-liner)

---

## File System Layout

```
~/projects/AnesthOS/                    # Main project repo
├── CLAUDE.md                           # AI agent rules (31 lines)
├── README.md                           # SR-Agent documentation (133 lines)
├── .githooks/
│   ├── pre-commit                      # Shell wrapper (11 lines)
│   └── pre-commit-checker.py           # Safety scanner (211 lines)
├── .anesthos/
│   └── specs/                          # Medical rules (EMPTY — only .keep)
├── scripts/
│   ├── anesthos-sync.sh               # Pull/push orchestrator (238 lines)
│   ├── anesthos-check-models.sh       # Model availability check
│   ├── setup_anesthos_ai.sh           # Session initialization
│   ├── refresh_catalog.py             # Unknown purpose
│   ├── scan-history-secrets.py        # Redact secrets in .jsonl
│   └── [launchd plist templates]
├── sr_agent/                           # SR-Agent Python package
│   ├── config.py
│   ├── doctor.py
│   ├── ingest/
│   ├── dedup/
│   └── [other modules]
├── .git/                              # Git repo → 9router
└── [Next.js project files TBD]

~/.claude/profiles/anesthos/            # OpenCode profile
├── settings.json                       # API routing config
├── settings.local.json                 # File permissions
├── history.jsonl                       # Current session (3.5KB)
├── .gitattributes                      # merge=union for *.jsonl
└── .git/                              # Git repo → AnesthOS-AI-History

~/.omniroute/                           # OmniRoute state
├── storage.sqlite                      # Combos, connections (1.8MB)
├── storage.sqlite-wal                  # Write-ahead log (3.6MB)
├── .env                                # Environment variables
├── .env.secrets                        # API keys (⚠️ in iCloud!)
├── health.log                          # Health check history
├── restarts.log                        # Last hour restart timestamps
├── omniroute.log                       # Server logs
└── logs/application/app.log            # Structured JSON logs (8.6MB)

~/scripts/
└── omniroute-health.sh                 # Health check script (104 lines)

~/Library/LaunchAgents/
└── com.anesthos.omniroute-health.plist # Health agent (300s interval)

~/Library/Mobile Documents/com~apple~CloudDocs/Backups/omniroute/
└── [Synced copy of ~/.omniroute/]      # iCloud backup (active)
```

---

## Network Topology

```
┌─────────────────────────────────────────────────────────────┐
│  localhost                                                   │
│                                                              │
│  :20128  OmniRoute API                                      │
│  :11434  Ollama API                                         │
│                                                              │
└─────────────────────────────────────────────────────────────┘
           ↓ HTTPS (outbound)
┌─────────────────────────────────────────────────────────────┐
│  External APIs                                               │
│                                                              │
│  api.kiro.ai          Kiro AI (free tier)                   │
│  api.antigravity.dev  Antigravity (paid)                    │
│  github.com           Git remotes (SSH port 22)             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Firewall Rules**: None configured (macOS default deny incoming)

**DNS Dependencies**:
- `api.kiro.ai` — Primary model provider
- `api.antigravity.dev` — Backup providers
- `github.com` — Git sync

**Offline Behavior**:
- OmniRoute tries providers 1-3 → timeout → falls back to Ollama
- Git sync fails gracefully (does not block local work)
- Health agent continues running (local checks only)

---

## State Machines

### OmniRoute Health States
```
┌─────────┐  startup   ┌─────────┐
│ STOPPED ├───────────→│ HEALTHY │
└─────────┘            └────┬────┘
                            │
              check fails   │ check passes
                            ↓
                       ┌─────────┐
         restarts<3/h  │DEGRADED │  restarts≥3/h
                       └────┬────┘
                            │
          ┌─────────────────┴──────────────────┐
          ↓                                     ↓
    ┌──────────┐                         ┌──────────┐
    │RESTARTING│                         │ALERT-ONLY│
    └─────┬────┘                         └──────────┘
          │                                     ↑
          │ success                             │
          └─────────────────────────────────────┘
                      1 hour passes
```

### AI History Sync Lifecycle
```
LOCAL EDIT → git add -A → SECRET SCAN → ┬─ PASS → commit → push → SYNCED
                                         │
                                         └─ FAIL → BLOCKED (exit 1)
```

---

## Continuation in PART 2...
