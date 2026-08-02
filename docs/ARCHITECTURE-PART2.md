# AnesthOS Architecture — Part 2: Operations & Safety

> Continuation from PART 1  
> **Date**: 2026-07-12  

---

## Security & Safety Mechanisms

### 1. Pre-commit Hook — Code Safety Gate

**Location**: `.githooks/pre-commit` (11 lines shell) + `.githooks/pre-commit-checker.py` (211 lines Python)

**Activation**: `git config core.hooksPath .githooks`

**Checks Performed** (on staged files only):

#### A. PII Detection
```python
# Patterns checked:
EMAIL_REGEX = r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'
ID_REGEX = r'\b\d{9}\b|\b\d{12}\b'  # Vietnamese CMND/CCCD
PHONE_REGEX = r'(?<!\d)(?:\+?\d{1,3}[- .]?)?\(?\d{2,4}\)?[- .]?\d{3,4}[- .]?\d{3,4}\b'
```
**Action on Match**: Block commit, print line number + matched value

#### B. Secret Detection
```python
# Patterns checked:
- r'\bsk-[a-zA-Z0-9]{24,}\b'  # Anthropic/OpenAI API keys
- r'\bAIzaSy[A-Za-z0-9_-]{33}\b'  # Google API keys
- r'(?i)(?:secret|api)_?(?:key|token|secret)\s*[:=]\s*["\'][a-zA-Z0-9_\-\.@\/]{8,}["\']'
```
**Action on Match**: Block commit, print masked value (`sk-XXXX...YYYY`)

#### C. Dependency Whitelist
For `package.json` changes only:
```python
approved_patterns = [
    'next', 'react', 'react-dom', 'tailwindcss', 'lucide-react',
    'better-sqlite3', 'sqlite3', 'typescript', 'eslint', 'postcss',
    'autoprefixer', 'jest', '@radix-ui/*', '@types/*', 'prettier',
    # ... (see line 66-89 of pre-commit-checker.py)
]
```
**Logic**: Compare `git show HEAD:package.json` vs staged version, block if new dependencies not in whitelist.

#### D. LaTeX Documentation Check
For files containing clinical keywords (`dose`, `calculation`, `formula`, `dosing`, `infusion`, `weight-based`):
```python
LATEX_REGEX = r'\$[A-Za-z0-9_ += \\times \\div \\cdot * / \- \(\) \^ \{ \} \[ \] \. , \\ ]+\$'
```
**Action**: If keyword found but no LaTeX comment, block commit.

**Bypass Method**:
```bash
git commit --no-verify -m "message"
```

**Critical Finding #6: No Bypass Audit**
`--no-verify` leaves no trace. Recommended: wrap `git` command in shell function to log bypasses.

**Skip Conditions**:
- Binary files (contain `\0` byte)
- Lock files (`package-lock.json`, `*.lock`)
- Media files (`.png`, `.jpg`, `.pdf`, `.zip`, etc.)

---

### 2. AI History Secret Scan

**Script**: `scripts/scan-history-secrets.py` (not yet read — need implementation details)

**Trigger**: Called by `anesthos-sync.sh` before pushing AI history

**Logic** (inferred from sync script):
```python
# Scan all staged .jsonl files
# If secrets found:
#   - Block push (exit 1)
#   - Suggest: python3 scan-history-secrets.py --fix <dir>
#   - --fix mode: create backup, redact secrets in-place
```

**Fallback**: If scanner not found, uses `pre-commit-checker.py` on `.jsonl` files.

**Critical Finding #7: Scanner Not Verified**
Script exists but not tested. Need to verify:
- Does it parse JSON correctly?
- Does it handle multi-line strings in chat messages?
- Does it preserve .jsonl format after redaction?

---

### 3. CLAUDE.md — AI Agent Constraints

**Location**: `~/projects/AnesthOS/CLAUDE.md` (31 lines)

**Purpose**: Instruction file read by Claude Code/OpenCode to enforce project rules.

**Rules Defined**:

#### Medical Safety
```markdown
- No PII/PHI Outbound: Never send patient data to external APIs
```
**Enforcement**: Honor system (AI reads file) + pre-commit hooks (hard block)

#### Tech Stack Constraints
```markdown
- Framework: Next.js (App Router)
- Styling: TailwindCSS
- Database: SQLite (native addon)
- UI Components: Radix UI
- Icons: Lucide React
```

#### Code Quality Rules
```markdown
- TypeScript strict mode, `any` type forbidden
- Clinical math: native Math.* only, no npm math packages
- LaTeX documentation for all dosage formulas
- No plagiarism from open-source medical repos
- No arbitrary shell script execution
- Rules must derive from .anesthos/specs/ files
```

**Enforcement Method**:
- AI self-enforcement (unreliable)
- Pre-commit hooks (reliable for commits)
- No runtime enforcement (gap)

**Critical Finding #8: `.anesthos/specs/` is Empty**
CLAUDE.md says "rules must derive from specs", but folder only contains `.keep` file. Either:
- Specs not written yet (project in early stage)
- Specs stored elsewhere
- Rule is aspirational

---

### 4. iCloud Backup Strategy

**What is Backed Up**:
```
~/.omniroute/              → iCloud Drive/Backups/omniroute/
  ├── storage.sqlite       ✅ Synced
  ├── storage.sqlite-wal   ✅ Synced
  ├── .env                 ✅ Synced
  ├── .env.secrets         ⚠️ Synced (security issue)
  ├── *.log                ❌ Excluded by rsync
  └── [all other files]    ✅ Synced
```

**Implementation**: Symlink created by `anesthos-sync.sh` on first run:
```bash
mv ~/.omniroute ~/.omniroute_local_backup
ln -s ~/Library/Mobile\ Documents/.../Backups/omniroute ~/.omniroute
```

**Sync Frequency**: Real-time (iCloud Drive automatic sync)

**What is NOT Backed Up**:
- `~/.claude/profiles/anesthos/` → backed up via Git, not iCloud
- `~/projects/AnesthOS/` → backed up via Git, not iCloud
- `~/scripts/` → NOT backed up anywhere ⚠️

**Critical Finding #9: Health Script Not Backed Up**
`~/scripts/omniroute-health.sh` is critical infrastructure but not in version control or backup. If laptop dies, must recreate from memory.

**Recovery Procedure** (if device lost):
1. Clone `9router` repo → source code
2. Clone `AnesthOS-AI-History` repo → chat history
3. iCloud restores `~/.omniroute/` automatically
4. Manually recreate:
   - `~/scripts/omniroute-health.sh` ❌
   - `~/Library/LaunchAgents/*.plist` ❌
   - Aliases in `~/.zshrc` ❌

---

## Operational Workflows

### Daily Development Session

**Start Sequence** (via `anesthos-start` alias):
```bash
# Alias definition in ~/.zshrc:
alias anesthos-start='
  ~/projects/AnesthOS/scripts/setup_anesthos_ai.sh && 
  python3 ~/projects/AnesthOS/scripts/refresh_catalog.py && 
  ~/projects/AnesthOS/scripts/anesthos-sync.sh pull && 
  opencode
'
```

**Step-by-Step**:
1. `setup_anesthos_ai.sh` — Unknown purpose (not yet read)
2. `refresh_catalog.py` — Unknown purpose (SR-Agent related?)
3. `anesthos-sync.sh pull`:
   - Pull source code updates (fast-forward only)
   - Pull AI history updates (allow merge)
   - Deduplicate merged `.jsonl` files
4. `opencode` — Launch OpenCode CLI with profile isolation

**Environment Setup**:
- `CLAUDE_CONFIG_DIR` set by alias (inferred, not explicitly in alias text)
- Working directory: `~/projects/AnesthOS`

---

**End Sequence** (via `anesthos-save` alias):
```bash
# Alias definition in ~/.zshrc:
alias anesthos-save='
  echo "⚠️ Please ensure OpenCode is closed." && 
  read -q "?Are you ready to commit and backup? (y/n) " && 
  echo "" && 
  ~/projects/AnesthOS/scripts/anesthos-sync.sh push
'
```

**Step-by-Step**:
1. Prompt user to close OpenCode (warning only)
2. Ask for confirmation (y/n)
3. `anesthos-sync.sh push`:
   - Scan AI history for secrets → block if found
   - Commit + push AI history
   - Commit + push source code
   - Run SSD backup if configured

**Critical Finding #10: User Can Ignore Warning**
Prompt is advisory only. User can press `y` while OpenCode still running, causing race condition.

**Recommended Fix**:
```bash
if pgrep -qf "opencode.*anesthos"; then
  echo "❌ OpenCode is still running. Exit it first."
  return 1
fi
```

---

### Emergency Recovery

#### Scenario 1: OmniRoute Won't Start
```bash
# Check port conflict
lsof -i :20128

# Check logs
tail -50 ~/.omniroute/logs/application/app.log

# Manual start
PORT=20128 DATA_DIR=~/.omniroute OMNIROUTE_MAX_PENDING_MIGRATIONS=0 \
  /Users/gun/.nvm/versions/node/v25.9.0/bin/omniroute
```

#### Scenario 2: Combo Not Found
```bash
# Verify via API
curl -s http://localhost:20128/v1/models | jq '.data[] | select(.id=="anesthos-brain")'

# Check SQLite (may not match runtime state)
sqlite3 ~/.omniroute/storage.sqlite "SELECT * FROM combos;"

# Workaround: Use provider directly
# Edit ~/.claude/profiles/anesthos/settings.json:
#   "model": "kr/claude-sonnet-4.5"  # bypass combo
```

#### Scenario 3: iCloud Sync Conflict
```bash
# Symptoms: OmniRoute fails with "database locked"

# Stop OmniRoute
pkill -f omniroute

# Check for conflict files
ls ~/.omniroute/*.icloud

# Resolve: Keep local version
mv ~/.omniroute/storage.sqlite.icloud ~/.omniroute/storage.sqlite.backup
# Let iCloud re-download, or force local upload

# Restart OmniRoute
```

#### Scenario 4: Git History Merge Conflict
```bash
# During pull mode, if merge fails:
cd ~/.claude/profiles/anesthos

# Check conflict
git status

# Strategy 1: Accept both versions (merge=union should prevent this)
git merge --strategy-option theirs origin/main

# Strategy 2: Dedupe manually
awk '!seen[$0]++' history.jsonl > history.jsonl.tmp
mv history.jsonl.tmp history.jsonl
git add history.jsonl
git commit -m "Resolve merge conflict via deduplication"
```

#### Scenario 5: Health Agent Flapping
```bash
# Symptoms: 3+ restarts in 1 hour, agent in alert-only mode

# Check root cause
tail -50 ~/.omniroute/health.log

# Common causes:
# - Provider API rate limit → wait or disable provider
# - Network issue → check wifi
# - OmniRoute bug → update omniroute: npm update -g omniroute

# Reset counter to allow restarts again
echo "" > ~/.omniroute/restarts.log

# Or wait 1 hour for automatic reset
```

---

## Performance Characteristics

### Response Time Baselines (from logs)

| Provider | Model | Typical Response | P95 | Status |
|----------|-------|------------------|-----|--------|
| Kiro AI | kr/claude-sonnet-4.5 | 2.9s | ~5s | ✅ Verified (2026-07-12 04:12) |
| Antigravity | ag/claude-sonnet-4-6 | Unknown | Unknown | ⚠️ Not tested |
| Antigravity | ag/gemini-2.5-pro | Unknown | Unknown | ⚠️ Not tested |
| Ollama | qwen2.5:7b-instruct | 180ms (warm) | 10s (cold) | ✅ Verified |

**Fallback Trigger Latency**:
- Unknown — need to test scenario where provider 1 is slow but not failing
- Risk: 30s timeout on provider 1 → 30s wait before trying provider 2

**Health Check Overhead**:
- Models endpoint: ~50ms (local only)
- Completion probe: ~3s (goes to actual provider)
- Total agent cycle: <5s (normal), ~15s (with hourly probe)

---

## Known Limitations & Gaps

### Functional Gaps

1. **No Automatic OmniRoute Startup**
   - Health agent can restart, but if OmniRoute never started, agent does nothing
   - Need: launchd agent to start OmniRoute at login

2. **No Ollama Health Monitoring**
   - Health agent only checks OmniRoute
   - If Ollama crashes, fallback fails silently with 503

3. **No Rate Limit Tracking**
   - Unknown when approaching Kiro AI free tier limit
   - No cost projection for paid providers

4. **No AI History Size Management**
   - `.jsonl` files grow indefinitely
   - No rotation, compression, or archival strategy

5. **No Medical Code Exists**
   - Despite AnesthOS name, repo only contains SR-Agent (paper pipeline)
   - `.anesthos/specs/` folder is empty

### Security Gaps

6. **Credentials in iCloud**
   - `.env.secrets` syncs to iCloud despite `local.nosync` folder name
   - Apple can access API keys

7. **No Bypass Audit Trail**
   - `git commit --no-verify` leaves no log
   - No weekly report of bypassed commits

8. **Pre-commit Hook Not Tested**
   - 100+ edge cases (email+, phone leading zeros, etc.) not covered
   - No unit test suite for pre-commit-checker.py

9. **Secret Scanner Unverified**
   - `scan-history-secrets.py` exists but never tested
   - May corrupt `.jsonl` files during redaction

### Operational Gaps

10. **No Infrastructure-as-Code**
    - `~/scripts/omniroute-health.sh` not in version control
    - `~/Library/LaunchAgents/*.plist` not backed up
    - `~/.zshrc` aliases not backed up

11. **No Disaster Recovery Playbook**
    - If laptop stolen/destroyed, recovery time unknown
    - Manual steps not documented

12. **No Monitoring Dashboard**
    - Can't see fallback rate, success rate, cost per day
    - No alerting for anomalies (sudden spike in failures)

13. **Ollama Models Not Pre-warmed**
    - First fallback request takes 10s (model loading)
    - Should pre-warm at boot or after health agent restart

---

## Technical Debt Inventory

| ID | Issue | Impact | Effort |
|----|-------|--------|--------|
| TD-1 | SQLite queries return empty (combo, connection) | 🔴 High | 2h |
| TD-2 | Credentials in iCloud sync path | 🔴 High | 1h |
| TD-3 | Race condition in anesthos-save | 🔴 High | 15m |
| TD-4 | No Ollama health check | 🟡 Medium | 30m |
| TD-5 | No rate limit monitoring | 🟡 Medium | 2h |
| TD-6 | No AI history rotation | 🟡 Medium | 1h |
| TD-7 | Health script not in version control | 🟡 Medium | 10m |
| TD-8 | No pre-commit hook tests | 🟡 Medium | 3h |
| TD-9 | No bypass audit trail | 🟠 Low | 1h |
| TD-10 | No Ollama pre-warming | 🟠 Low | 30m |
| TD-11 | No disaster recovery docs | 🟠 Low | 2h |
| TD-12 | No monitoring dashboard | 🟠 Low | 4h |

**Total Estimated Effort**: ~18 hours

---

## Design Decisions & Rationale

### Why OmniRoute Instead of Direct Provider Calls?

**Pros**:
- Single endpoint for all models
- Fallback without code changes
- Centralized logging
- Rate limit handling
- Cost tracking potential

**Cons**:
- Single point of failure
- Additional latency (~50ms)
- Complex debugging (two layers)

**Verdict**: Worth it for resilience, but needs better monitoring.

---

### Why Priority Strategy Instead of Load Balancing?

**Current**: Try provider 1 → 2 → 3 → 4 sequentially

**Alternative**: Round-robin or least-latency routing

**Rationale**:
- Provider 1 (Kiro) is free — maximize free tier usage
- Provider 2-3 (Antigravity) cost money — use only when needed
- Provider 4 (Ollama) is limited quality — last resort

**Trade-off**: If provider 1 is slow (not failing), all requests wait. No escape hatch to skip to provider 2.

---

### Why Git for AI History Instead of Database?

**Pros**:
- Text format easy to read/grep
- Git provides versioning, branching, merging
- GitHub provides free unlimited private repos
- `merge=union` handles concurrent sessions

**Cons**:
- Large files slow down git operations
- No structured queries (must parse JSON)
- Deduplication needed after merge

**Verdict**: Works for single developer, would not scale to team.

---

### Why launchd Instead of cron?

**Rationale**: On macOS, cron jobs do NOT run when laptop is asleep. With MacBook Air (frequently closed), 7am daily job would never fire. launchd agents run immediately when device wakes up after scheduled time.

**Trade-off**: launchd more complex syntax, but necessary for laptop workflows.

---

## Future Architecture Considerations

### If Scaling to Team (2+ Developers)

**Problems**:
1. AI history merge conflicts (union merge not enough)
2. OmniRoute on each developer's laptop (credential duplication)
3. Cost tracking per developer

**Recommended Changes**:
- Centralized OmniRoute server (e.g., on NAS or VPS)
- Separate AI history repos per developer
- Prometheus metrics + Grafana dashboard

---

### If Moving to Production (Actual Patients)

**Required Changes**:
1. ❌ **Remove all cloud providers** — PII cannot leave device
   - Only Ollama allowed
   - Or on-premise Claude deployment (Anthropic Enterprise)

2. ❌ **Remove GitHub sync** — patient data cannot go to GitHub
   - Local Git only, or self-hosted GitLab

3. ✅ **Add HIPAA compliance**:
   - Encrypted disk (FileVault)
   - Audit logs (who accessed what patient data)
   - Data retention policies

4. ✅ **Add clinical validation**:
   - Medical device certification (FDA/CE)
   - Algorithm validation studies
   - Peer review

**Estimated Effort**: 500+ hours of compliance work.

---

## Critical Findings Summary

| ID | Finding | Severity | Fix Effort |
|----|---------|----------|------------|
| #1 | Credentials sync to iCloud | 🔴 Critical | 1h |
| #2 | Combo config not in SQLite | 🔴 Critical | 2h investigation |
| #3 | Ollama connection not in SQLite | 🟡 Medium | Same as #2 |
| #4 | No Ollama health monitoring | 🟡 Medium | 30m |
| #5 | Race condition in sync script | 🔴 Critical | 15m |
| #6 | No bypass audit trail | 🟠 Low | 1h |
| #7 | Secret scanner not verified | 🟡 Medium | 1h testing |
| #8 | Medical specs folder empty | 🟡 Medium | Clarify project status |
| #9 | Health script not backed up | 🟡 Medium | 10m |
| #10 | User can ignore OpenCode warning | 🔴 Critical | 15m |

---

## Recommendations for Next AI Agent

### Before Making Changes

1. **Verify OmniRoute Runtime State**:
   ```bash
   curl -s http://localhost:20128/v1/models | jq .
   ```
   Compare with SQLite schema to understand config storage.

2. **Test Fallback Chain**:
   - Disable Kiro API key temporarily
   - Trigger request
   - Verify falls back to Antigravity, not Ollama

3. **Read Missing Scripts**:
   - `setup_anesthos_ai.sh`
   - `refresh_catalog.py`
   - `scan-history-secrets.py`

### When Implementing Fixes

1. **Start with P0 Critical Items**:
   - Fix #1: Move credentials out of iCloud
   - Fix #5: Block sync when OpenCode running
   - Fix #10: Same as #5 (in alias)

2. **Add Tests Before Changing Pre-commit Hook**:
   ```bash
   # Create tests/test_pre_commit.py
   # 100+ test cases for PII/secret patterns
   ```

3. **Version Control Infrastructure**:
   ```bash
   mkdir -p ~/projects/AnesthOS/infra
   cp ~/scripts/* ~/projects/AnesthOS/infra/
   cp ~/Library/LaunchAgents/com.anesthos.* ~/projects/AnesthOS/infra/
   # Extract aliases from ~/.zshrc
   ```

---

## Appendix: Command Reference

### OmniRoute Management
```bash
# Start
PORT=20128 DATA_DIR=~/.omniroute OMNIROUTE_MAX_PENDING_MIGRATIONS=0 \
  nohup omniroute > ~/.omniroute/omniroute.log 2>&1 &

# Stop
pkill -f "[o]mniroute"

# Status
curl -s http://localhost:20128/v1/models | jq '.data[0]'

# Logs
tail -f ~/.omniroute/logs/application/app.log
```

### Health Agent Management
```bash
# Load
launchctl load ~/Library/LaunchAgents/com.anesthos.omniroute-health.plist

# Unload
launchctl unload ~/Library/LaunchAgents/com.anesthos.omniroute-health.plist

# Status
launchctl list | grep anesthos

# Trigger manually
sh ~/scripts/omniroute-health.sh

# View logs
tail -f ~/.omniroute/health.log
```

### Ollama Management
```bash
# List models
ollama list

# Check running status
curl -s http://localhost:11434/api/ps | jq .

# Pre-warm model
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen2.5:7b-instruct","prompt":"test","options":{"num_predict":1}}'
```

### Git Operations
```bash
# Source code
cd ~/projects/AnesthOS
git status
git log --oneline -10

# AI history
cd ~/.claude/profiles/anesthos
git status
git log --oneline -10

# Dedupe manually
awk '!seen[$0]++' history.jsonl > history.jsonl.tmp && mv history.jsonl.tmp history.jsonl
```

---

## Document Changelog

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-07-12 | Original briefing | Initial handoff doc |
| 2.0 | 2026-07-12 | Kiro AI | Full analysis + critical findings |

---

**End of Part 2**

**Next Steps for Implementation Team**:
1. Review Critical Findings #1, #5, #10 (security risks)
2. Investigate Findings #2, #3 (SQLite mystery)
3. Decide: Continue SR-Agent development OR pivot to AnesthOS medical app
4. If medical app: populate `.anesthos/specs/` with clinical rules
5. If paper pipeline: rename project to avoid confusion

**Estimated Reading Time**: 45 minutes  
**Estimated Fix Time for P0 Issues**: 3-4 hours
