# AnesthOS — Project Charter

> **Version**: 1.0  
> **Date**: 2026-07-12  
> **Trạng thái**: APPROVED  
> **PM**: Claude Project Manager Agent  

---

## 1. Phạm vi dự án (Scope)

### 1.1 Mục tiêu tổng thể

Biến AnesthOS Dev Station từ một **development station đang hoạt động nhưng chứa nhiều lỗ hổng** thành một **hệ thống local-first AI development environment an toàn, đáng tin cậy, có khả năng phục hồi và monitor được**.

Cụ thể:
1. **Loại bỏ mọi lỗ hổng bảo mật** — credentials không được đồng bộ lên iCloud
2. **Sửa mọi lỗi nghiêm trọng (Critical)** — race condition, exit code sai, auth failures
3. **Đưa infrastructure vào version control** — health script, launchd plist, aliases
4. **Thêm monitoring cơ bản** — health check cho Ollama, rate limit tracking
5. **Xác định rõ identity dự án** — tách SR-Agent khỏi AnesthOS hoặc hợp nhất có chủ đích
6. **Thiết lập nền tảng cho medical code** — populate `.anesthos/specs/`

### 1.2 WBS — Work Breakdown Structure

```
AnesthOS Project Charter
│
├── WBS-1: Security Hardening (P0)
│   ├── 1.1 Move credentials out of iCloud
│   ├── 1.2 Add bypass audit trail for --no-verify
│   └── 1.3 Harden file permissions (644 → 600 cho secrets)
│
├── WBS-2: Critical Bug Fixes (P0)
│   ├── 2.1 Fix race condition: exit 0 → exit 1
│   ├── 2.2 Block sync when OpenCode running (alias level)
│   └── 2.3 Investigate combo "anesthos-brain" missing at runtime
│
├── WBS-3: Infrastructure as Code (P1)
│   ├── 3.1 Add health script to repo
│   ├── 3.2 Add launchd plist to repo
│   ├── 3.3 Extract aliases to dotfile
│   └── 3.4 Create infra/ directory with setup/teardown scripts
│
├── WBS-4: Availability & Resilience (P1)
│   ├── 4.1 Add Ollama health monitoring
│   ├── 4.2 Add Ollama pre-warming at boot
│   ├── 4.3 Add automatic OmniRoute startup at login
│   └── 4.4 Fix hourly 401 error in health check
│
├── WBS-5: Monitoring & Observability (P2)
│   ├── 5.1 Add rate limit tracking
│   ├── 5.2 Add AI history size management (rotation/archival)
│   ├── 5.3 Create basic health dashboard
│   └── 5.4 Add cost projection tracking
│
├── WBS-6: Code Quality & Testing (P2)
│   ├── 6.1 Write unit tests for pre-commit-checker.py
│   ├── 6.2 Verify and test scan-history-secrets.py
│   └── 6.3 Add pre-commit hook integration tests
│
├── WBS-7: Project Identity & Documentation (P3)
│   ├── 7.1 Decide: separate SR-Agent or rename project
│   ├── 7.2 Populate .anesthos/specs/ with medical rules
│   ├── 7.3 Create disaster recovery playbook
│   └── 7.4 Create onboarding docs
│
└── WBS-8: Performance Optimization (P3)
    ├── 8.1 Test fallback chain latency
    ├── 8.2 Optimize Ollama model loading
    └── 8.3 Profile OmniRoute overhead
```

### 1.3 Priority Classification

| Priority | Definition | Items | Total Effort |
|----------|-----------|-------|-------------|
| **P0** | Must fix NOW — security risk or data loss | WBS-1, WBS-2 | ~4h |
| **P1** | Must fix SOON — operational reliability | WBS-3, WBS-4 | ~3h |
| **P2** | Should fix — quality of life | WBS-5, WBS-6 | ~8h |
| **P3** | Nice to have — strategic | WBS-7, WBS-8 | ~6h |

### 1.4 Out of Scope

- ❌ Viết medical application code (Next.js components, clinical logic)
- ❌ HIPAA/FDA compliance certification
- ❌ Team collaboration features (multi-user)
- ❌ UI dashboard (web UI cho monitoring)
- ❌ SR-Agent feature development
- ❌ CI/CD pipeline setup
- ❌ Containerization (Docker/Kubernetes)

---

## 2. Tiêu chuẩn nghiệm thu (Acceptance Criteria)

### 2.1 WBS-1: Security Hardening

#### 1.1 Move credentials out of iCloud

**Definition of Done**:
- [ ] `.env.secrets` moved từ `~/Library/Mobile Documents/com~apple~CloudDocs/Backups/omniroute/local.nosync/.env.secrets` ra `~/Library/Application Support/AnesthOS/secrets.env`
- [ ] Symlink cũ đã được xóa, không còn đường dẫn nào trỏ vào iCloud
- [ ] `secrets.env` được thêm vào `.gitignore` của mọi repo (AnesthOS, AnesthOS-AI-History)
- [ ] OmniRoute startup command/health script được cập nhật để đọc từ đường dẫn mới
- [ ] iCloud backup script (anesthos-sync.sh) được cập nhật — không copy secrets

**Test Cases**:
```bash
# TC-1.1.1: Verify no symlink to iCloud
readlink ~/.omniroute/.env.secrets 2>/dev/null
# Expected: not contains "Mobile Documents" or "CloudDocs"

# TC-1.1.2: Verify file is outside iCloud
ls ~/Library/Application\ Support/AnesthOS/secrets.env
# Expected: file exists

# TC-1.1.3: Verify OmniRoute still works
curl -s http://localhost:20128/v1/models | python3 -c "import sys,json; d=json.load(sys.stdin); assert len(d.get('data',[])) > 0"
# Expected: HTTP 200, non-empty data

# TC-1.1.4: Verify .gitignore contains secrets.env
grep "secrets.env" ~/projects/AnesthOS/.gitignore
# Expected: match found

# TC-1.1.5: Verify iCloud no longer has secrets
find ~/Library/Mobile\ Documents/com~apple~CloudDocs/ -name "*secret*" -o -name "*.env*" 2>/dev/null | grep -v ".gitignore" || echo "No secrets in iCloud"
# Expected: "No secrets in iCloud" or only expected files
```

**Security Check**:
- [ ] file permissions: `600` (owner read/write only)
- [ ] directory permissions: `700`
- [ ] No world-readable flag
- [ ] `fs_usage` check: không có process nào đọc file ngoại trừ OmniRoute

---

#### 1.2 Add bypass audit trail

**Definition of Done**:
- [ ] `git` command được wrap trong shell function (`.zshrc` hoặc script riêng)
- [ ] Khi `--no-verify` được dùng, log entry được ghi vào `~/.anesthos/bypass-audit.log`
- [ ] Log entry bao gồm: timestamp, working directory, commit message (truncated), user

**Test Cases**:
```bash
# TC-1.2.1: Verify bypass is logged
git commit --no-verify -m "test bypass" 2>/dev/null || true
cat ~/.anesthos/bypass-audit.log 2>/dev/null | tail -1
# Expected: entry with timestamp + message "test bypass"

# TC-1.2.2: Verify normal commit is NOT logged
git commit -m "normal commit" 2>/dev/null || true
grep "normal commit" ~/.anesthos/bypass-audit.log 2>/dev/null
# Expected: no match (or only from --no-verify test)
```

**Security Check**:
- [ ] Audit log không thể bị xóa bởi non-root user (hoặc có cơ chế append-only)
- [ ] Audit log không tự động rotate hoặc xóa (cần manual cleanup)

---

#### 1.3 Harden file permissions

**Definition of Done**:
- [ ] Mọi file `.env*`, `*secret*`, `*key*` trong `~/.omniroute/` và `~/.anesthos/` có permission `600`
- [ ] Mọi file script trong `~/scripts/` có permission `700`
- [ ] Script kiểm tra permissions được chạy định kỳ (có thể tích hợp vào health check)

**Test Cases**:
```bash
# TC-1.3.1: Check critical file permissions
stat -f "%p %N" ~/.omniroute/.env*
# Expected: 100600 for .env files

# TC-1.3.2: Check script permissions
stat -f "%p %N" ~/scripts/omniroute-health.sh
# Expected: 100700
```

---

### 2.2 WBS-2: Critical Bug Fixes

#### 2.1 Fix race condition: exit 0 → exit 1

**Definition of Done**:
- [ ] Dòng `exit 0` tại line 66 của `anesthos-sync.sh` được đổi thành `exit 1`
- [ ] Script kiểm tra `pgrep -x claude` được mở rộng thêm `pgrep -qf "opencode.*anesthos"`
- [ ] Test thủ công: chạy sync khi OpenCode đang chạy → script fail với exit code 1

**Test Cases**:
```bash
# TC-2.1.1: Verify exit code when process running
opencode --version 2>/dev/null &
sleep 1
~/projects/AnesthOS/scripts/anesthos-sync.sh push; echo "Exit: $?"
# Expected: "Exit: 1"

# TC-2.1.2: Verify exit code when no process running
~/projects/AnesthOS/scripts/anesthos-sync.sh push 2>&1; echo "Exit: $?"
# Expected: 0 (or other failure unrelated to race condition)
```

---

#### 2.2 Block sync at alias level

**Definition of Done**:
- [ ] `anesthos-save` alias được cập nhật: kiểm tra `pgrep -qf "opencode.*anesthos"` TRƯỚC khi cho phép sync
- [ ] Nếu OpenCode đang chạy: in message lỗi, `return 1`
- [ ] Không prompt hỏi user — block cứng

**Test Cases**:
```bash
# TC-2.2.1: Test alias blocks when OpenCode running
# (manual test with OpenCode open)
anesthos-save
# Expected: "❌ OpenCode is still running. Exit it first."

# TC-2.2.2: Test alias works when OpenCode closed
anesthos-save
# Expected: proceeds to confirmation prompt
```

---

#### 2.3 Investigate combo "anesthos-brain"

**Definition of Done**:
- [ ] Xác định tại sao `anesthos-brain` combo không xuất hiện trong API `/v1/models`
- [ ] Xác định config hiện tại của combo đang dùng (`claude-sonnet-4.5` với `owned_by: combo`)
- [ ] Fix: tạo lại combo đúng tên, hoặc cập nhật `settings.json` dùng combo name đúng
- [ ] Health check dùng `sk-anesthos-brain-token` không bị 401

**Root Cause Analysis Required**:
```bash
# Query SQLite for combo config
sqlite3 ~/.omniroute/storage.sqlite ".tables"
sqlite3 ~/.omniroute/storage.sqlite "SELECT * FROM sqlite_master WHERE type='table';"
sqlite3 ~/.omniroute/storage.sqlite "SELECT * FROM combos;" 2>/dev/null
sqlite3 ~/.omniroute/storage.sqlite "SELECT * FROM provider_connections;" 2>/dev/null

# Check if combo is in-memory only (OmniRoute bug)
# Check runtime config
curl -s http://localhost:20128/v1/models | python3 -c "
import sys, json
d = json.load(sys.stdin)
combos = [x for x in d['data'] if x.get('owned_by') == 'combo']
print('Combos found:', len(combos))
for c in combos: print(c['id'])
"
```

**Test Cases**:
```bash
# TC-2.3.1: Verify combo exists at runtime
curl -s http://localhost:20128/v1/models | python3 -c "
import sys, json
d = json.load(sys.stdin)
combos = [x['id'] for x in d['data'] if x.get('owned_by') == 'combo']
assert len(combos) > 0, 'No combos found'
print('Combos:', combos)
"

# TC-2.3.2: Verify health check passes
curl -s -o /dev/null -w "%{http_code}" -m 10 \
  -X POST -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-anesthos-brain-token" \
  -d '{"model": "anesthos-brain", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1}' \
  http://localhost:20128/v1/chat/completions
# Expected: 200

# TC-2.3.3: Verify settings.json points to working model
grep '"model"' ~/.claude/profiles/anesthos/settings.json
# Expected: valid combo ID that exists in API
```

---

### 2.3 WBS-3: Infrastructure as Code

#### 3.1 Add health script to repo

**Definition of Done**:
- [ ] `~/scripts/omniroute-health.sh` được copy vào `~/projects/AnesthOS/infra/omniroute-health.sh`
- [ ] Symlink hoặc install script được tạo: `ln -sf` từ repo vào `~/scripts/`
- [ ] Script trong repo là source of truth

**Test Cases**:
```bash
# TC-3.1.1: Verify file exists in repo
ls -la ~/projects/AnesthOS/infra/omniroute-health.sh
# Expected: file exists

# TC-3.1.2: Verify symlink points to repo
readlink ~/scripts/omniroute-health.sh
# Expected: ~/projects/AnesthOS/infra/omniroute-health.sh (or repo path)
```

---

#### 3.2 Add launchd plist to repo

**Definition of Done**:
- [ ] `com.anesthos.omniroute-health.plist` được copy vào `~/projects/AnesthOS/infra/`
- [ ] Install script được tạo: `cp` hoặc `ln` plist vào `~/Library/LaunchAgents/`

---

#### 3.3 Extract aliases to dotfile

**Definition of Done**:
- [ ] Aliases `anesthos-start`, `anesthos-save` được extract vào file riêng: `~/.anesthos/aliases.sh`
- [ ] `~/.zshrc` source file đó: `source ~/.anesthos/aliases.sh`

---

#### 3.4 Create infra/ setup/teardown

**Definition of Done**:
- [ ] `~/projects/AnesthOS/infra/setup.sh` — cài đặt mọi thứ (symlink, launchd load, copy scripts)
- [ ] `~/projects/AnesthOS/infra/teardown.sh` — gỡ cài đặt (clean, unload launchd, remove symlinks)

---

### 2.4 WBS-4: Availability & Resilience

#### 4.1 Add Ollama health monitoring

**Definition of Done**:
- [ ] Health script kiểm tra Ollama mỗi 5 phút: `curl -s -m 2 http://localhost:11434/api/ps`
- [ ] Nếu Ollama không respond: log warning + thử restart qua `open -a Ollama`
- [ ] Nếu restart fail: log ALARM (không restart loop — giống cơ chế OmniRoute)

**Test Cases**:
```bash
# TC-4.1.1: Ollama health check in log
grep "Ollama" ~/.omniroute/health.log | tail -3
# Expected: "✅ Ollama operational" or "⚠️ Ollama not responding"

# TC-4.1.2: Simulate Ollama crash (manual test)
pkill -f ollama
# Wait for health check cycle (≤5 min)
grep "ollama" ~/.omniroute/health.log | tail -3
# Expected: "⚠️ Ollama not responding"
```

---

#### 4.2 Add Ollama pre-warming

**Definition of Done**:
- [ ] Boot/login script gọi API pre-warm: `curl -s http://localhost:11434/api/generate -d '{"model":"qwen2.5:7b-instruct","prompt":"warmup","options":{"num_predict":1}}'`
- [ ] Health check pre-warm nếu model chưa loaded
- [ ] Pre-warm sau khi restart OmniRoute (trong health script)

**Performance Criteria**:
- [ ] First fallback request latency < 1s (thay vì 5-10s)

---

#### 4.3 Add automatic OmniRoute startup

**Definition of Done**:
- [ ] Launchd agent cho OmniRoute startup: `com.anesthos.omniroute.plist`
- [ ] `RunAtLoad: true`, `KeepAlive: true`
- [ ] Không conflict với health agent restart logic

---

#### 4.4 Fix hourly 401 error

**Definition of Done**:
- [ ] Debug: tại sao `Authorization: Bearer sk-anesthos-brain-token` bị 401
- [ ] Fix: cập nhật token, hoặc tạo combo đúng, hoặc sửa health check logic
- [ ] Sau fix: hourly completion probe pass với HTTP 200

**Test Cases**:
```bash
# TC-4.4.1: Verify hourly probe passes
# Wait for next hourly cycle or force:
echo "0" > ~/.omniroute/last_completion_check.txt
sh ~/scripts/omniroute-health.sh
grep "completion probe passed" ~/.omniroute/health.log | tail -1
# Expected: "✅ End-to-end completion probe passed successfully."
```

---

### 2.5 WBS-5: Monitoring & Observability

#### 5.1 Add rate limit tracking

**Definition of Done**:
- [ ] API calls count được log mỗi ngày
- [ ] Estimate: Kiro AI free tier limit, số calls còn lại
- [ ] Alert khi gần đạt limit (80%)

---

#### 5.2 Add AI history size management

**Definition of Done**:
- [ ] Script kiểm tra `.jsonl` file size
- [ ] Nếu > 50MB: archive (compress + move) và start file mới
- [ ] Retention: 6 tháng, archive cũ hơn auto-delete

---

#### 5.3 Create basic health dashboard

**Definition of Done**:
- [ ] Script parse `health.log` và xuất JSON metrics
- [ ] Có thể dùng `cat ~/.omniroute/summary.json` để xem health status

---

#### 5.4 Add cost projection tracking

**Definition of Done**:
- [ ] Log số lượng request mỗi provider mỗi ngày
- [ ] Estimate monthly cost cho Antigravity (paid providers)

---

### 2.6 WBS-6: Code Quality & Testing

#### 6.1 Unit tests for pre-commit-checker.py

**Definition of Done**:
- [ ] File `tests/test_pre_commit.py` với 50+ test cases
- [ ] Coverage: PII patterns, secret patterns, dependency whitelist, LaTeX check
- [ ] `npm run test` hoặc `python3 -m pytest tests/` pass

---

#### 6.2 Verify scan-history-secrets.py

**Definition of Done**:
- [ ] Chạy scanner trên file `.jsonl` test
- [ ] Verify: JSON parse đúng, multi-line strings handled, file format preserved
- [ ] `--fix` mode tạo backup và redact đúng

---

#### 6.3 Pre-commit hook integration tests

**Definition of Done**:
- [ ] Test script tạo commit với PII → verify bị block
- [ ] Test script tạo commit clean → verify pass
- [ ] Test bypass logging (WBS-1.2)

---

### 2.7 WBS-7: Project Identity

#### 7.1 Decide: SR-Agent vs AnesthOS

**Definition of Done**:
- [ ] Decision document: `ADR-001-project-identity.md`
- [ ] Nếu separate: tạo repo riêng, clean up repo hiện tại
- [ ] Nếu merge: rename project, update docs

---

#### 7.2 Populate .anesthos/specs/

**Definition of Done**:
- [ ] File `anesthesia-formulas.md` — công thức tính liều cơ bản
- [ ] File `medication-limits.md` — giới hạn liều an toàn
- [ ] File `clinical-rules.yaml` — rules machine-readable
- [ ] File `index.md` — spec index with versioning

**Content Requirements** (tối thiểu 1 file):
- Drug dosing formulas with LaTeX
- Safety limits (max dose per kg, per hour)
- References (sources for each rule)

---

#### 7.3 Disaster recovery playbook

**Definition of Done**:
- [ ] `docs/disaster-recovery.md`
- [ ] Recovery steps cho từng scenario
- [ ] Estimated RTO (khôi phục) cho mỗi scenario

---

### 2.8 WBS-8: Performance Optimization

#### 8.1 Test fallback chain latency

**Definition of Done**:
- [ ] Test script gọi completion với provider 1 chậm
- [ ] Đo latency fallback → provider 2, 3, 4
- [ ] Document timeout config hiện tại

---

#### 8.2 Optimize Ollama model loading

**Definition of Done**:
- [ ] Test different keep-alive settings
- [ ] Evaluate: `num_keep` options, model quantization

---

## 3. Lộ trình thực thi (Roadmap)

### 3.1 Pha 0 — Foundation (Day 1, ~2h)

**Mục tiêu**: Fix critical security + race condition ngay lập tức

| Thứ tự | Item | Dependencies | Thời gian |
|--------|------|-------------|-----------|
| 1 | 2.1 Fix race condition (exit 0 → 1) | None | 15m |
| 2 | 2.2 Block sync at alias level | (1) | 15m |
| 3 | 1.1 Move credentials out of iCloud | None | 1h |
| 4 | 1.3 Harden file permissions | (3) | 15m |
| 5 | 1.2 Add bypass audit trail | None | 30m |

**Handoff Criteria (sang Pha 1)**:
- [x] `exit 0` đã sửa thành `exit 1`
- [x] `anesthos-save` alias block cứng khi OpenCode running
- [x] `.env.secrets` không còn trong iCloud
- [x] File permissions đã harden
- [x] Bypass audit trail hoạt động

**Rủi ro chính**:
- Moving secrets có thể làm OmniRoute crash nếu config không đúng → cần test ngay sau khi deploy

---

### 3.2 Pha 1 — Infrastructure as Code (Day 1-2, ~3h)

**Mục tiêu**: Đưa toàn bộ infrastructure vào Git

| Thứ tự | Item | Dependencies | Thời gian |
|--------|------|-------------|-----------|
| 6 | 3.1 Add health script to repo | Pha 0 | 10m |
| 7 | 3.2 Add launchd plist to repo | (6) | 10m |
| 8 | 3.3 Extract aliases to dotfile | (7) | 15m |
| 9 | 3.4 Create infra/ setup/teardown | (6,7,8) | 30m |
| 10 | 2.3 Investigate combo missing | Pha 0 | 2h |

**Handoff Criteria (sang Pha 2)**:
- [x] Infra scripts version-controlled
- [x] `setup.sh` cài đặt được mọi thứ từ clean state
- [x] Root cause của combo missing đã xác định (hoặc workaround)

**Rủi ro chính**:
- Combo investigation (2.3) có thể kéo dài nếu OmniRoute có bug internal
- Nếu cần fix OmniRoute source: cần npm update hoặc patch

---

### 3.3 Pha 2 — Availability & Resilience (Day 2, ~3h)

**Mục tiêu**: Ollama + OmniRoute luôn available

| Thứ tự | Item | Dependencies | Thời gian |
|--------|------|-------------|-----------|
| 11 | 4.1 Add Ollama health monitoring | Pha 1 (health script) | 30m |
| 12 | 4.2 Add Ollama pre-warming | (11) | 30m |
| 13 | 4.3 Add OmniRoute launchd agent | Pha 1 | 1h |
| 14 | 4.4 Fix hourly 401 | Pha 1 (2.3) | 1h |

**Handoff Criteria (sang Pha 3)**:
- [x] Health check bao gồm cả OmniRoute + Ollama
- [x] Ollama pre-warm at boot
- [x] Hourly completion probe pass
- [x] OmniRoute auto-start at login

---

### 3.4 Pha 3 — Quality & Monitoring (Day 3-4, ~8h)

**Mục tiêu**: Visibility + code quality

| Thứ tự | Item | Dependencies | Thời gian |
|--------|------|-------------|-----------|
| 15 | 6.1 Unit tests for pre-commit hook | Pha 0 | 3h |
| 16 | 6.2 Verify scan-history-secrets.py | Pha 1 | 1h |
| 17 | 6.3 Integration tests | (15,16) | 1h |
| 18 | 5.1 Rate limit tracking | Pha 2 | 2h |
| 19 | 5.2 AI history rotation | Pha 1 | 1h |

**Handoff Criteria (sang Pha 4)**:
- [x] Pre-commit hook test suite pass
- [x] Secret scanner verified
- [x] Rate limit tracking operational

---

### 3.5 Pha 4 — Strategic (Day 5+, ~6h)

**Mục tiêu**: Project identity + docs + performance

| Thứ tự | Item | Dependencies | Thời gian |
|--------|------|-------------|-----------|
| 20 | 7.1 Project identity decision | Pha 0-3 | 1h |
| 21 | 7.2 Populate specs/ | (20) | 2h |
| 22 | 5.3 Health dashboard | Pha 2 | 2h |
| 23 | 7.3 Disaster recovery playbook | Pha 1 | 1h |
| 24 | 8.1-8.2 Performance optimization | Pha 2 | 2h |

---

### 3.6 Risk Register

| ID | Risk | Probability | Impact | Mitigation |
|----|------|------------|--------|------------|
| R-01 | OmniRoute crash khi move secrets | Medium | 🔴 High | Test ngay, có rollback plan |
| R-02 | Combo missing là OmniRoute bug (cần update npm) | Medium | 🟡 Medium | Workaround: update settings.json dùng provider model trực tiếp |
| R-03 | Ollama pre-warm gây memory pressure | Low | 🟡 Medium | Pre-warm chỉ 1 model, có thể config |
| R-04 | `.anesthos/specs/` effort underestimate | Medium | 🟡 Medium | Bắt đầu với 1 file, iterate |
| R-05 | iCloud sync conflict trong lúc move secrets | Low | 🔴 High | Disable iCloud sync tạm thời cho omniroute folder |
| R-06 | launchd KeepAlive + health agent conflict | Low | 🟡 Medium | Design: health agent không restart nếu launchd quản lý |
| R-07 | Quên không backup trước khi sửa | Low | 🟡 Medium | `git commit` trước mọi change |

---

## 4. Phân công trách nhiệm

### 4.1 Agent Assignment

| Phase | Agent Role | Trách nhiệm | Output |
|-------|-----------|-------------|--------|
| **Pha 0** | Security Agent | WBS-1: Hardening, WBS-2: Bug fixes | Security report, patches |
| **Pha 1** | Infrastructure Agent | WBS-3: IaC, WBS-2.3: Combo | IaC scripts, root cause analysis |
| **Pha 2** | Reliability Agent | WBS-4: Ollama, auto-start, 401 fix | Updated health agent, launchd plists |
| **Pha 3** | QA Agent | WBS-5: Monitoring, WBS-6: Testing | Test suite, monitoring scripts |
| **Pha 4** | Strategy Agent | WBS-7: Docs, WBS-8: Performance | Specs, playbook, ADR |

### 4.2 Handoff Criteria Between Phases

```
Phase 0 (Security) ──► Phase 1 (Infrastructure)
    ✓ Security hardened    ✓ Scripts committed
    ✓ Race condition fixed ✓ Combo identified
                          ✓ setup.sh works

Phase 1 (Infrastructure) ──► Phase 2 (Reliability)
    ✓ Health script in repo  ✓ Ollama monitored
    ✓ Combo resolved         ✓ Pre-warming active
    ✓ setup/teardown ready   ✓ 401 fixed

Phase 2 (Reliability) ──► Phase 3 (QA)
    ✓ Full health coverage   ✓ Tests pass
    ✓ Auto-start configured  ✓ Scanner verified

Phase 3 (QA) ──► Phase 4 (Strategy)
    ✓ Code quality gates      ✓ Docs written
    ✓ Monitoring operational  ✓ Decision made
```

### 4.3 Definition of Done cho mỗi Phase

| Phase | DoD |
|-------|-----|
| **Pha 0** | Không còn P0 vulnerability. Sync script an toàn. Secrets out of iCloud. |
| **Pha 1** | `infra/` folder có đầy đủ scripts, `setup.sh` install được từ clean state. |
| **Pha 2** | Health agent bao phủ cả OmniRoute + Ollama. OmniRoute auto-start. 401 fixed. |
| **Pha 3** | Test suite pass. Secret scanner verified. Rate limit tracking active. |
| **Pha 4** | Project identity xác định. Specs có nội dung tối thiểu. DR playbook ready. |

---

## 5. Success Metrics

### 5.1 KPIs

| KPI | Current Value | Target | Measurement Method |
|-----|--------------|--------|-------------------|
| **Secrets in iCloud** | ✅ YES | ❌ NO | `readlink ~/.omniroute/.env.secrets` |
| **Race condition** | `exit 0` (harmful) | `exit 1` (safe) | `grep "exit 0" anesthos-sync.sh` |
| **Health check coverage** | OmniRoute only | OmniRoute + Ollama | `grep "Ollama" health.log` |
| **401 errors/hour** | ~1 (hourly) | 0 | `grep -c "401" health.log` / hour |
| **Sync blocked when OpenCode running** | ❌ Advisory | ✅ Hard block | Test alias manually |
| **Health script in version control** | ❌ No | ✅ Yes | `ls infra/omniroute-health.sh` |
| **Pre-commit test coverage** | 0 tests | 50+ tests | `python3 -m pytest tests/ --tb=short` |
| **Specs folder** | Empty | ≥1 file | `ls .anesthos/specs/*.md` |
| **Disaster recovery playbook** | None | Exists | `ls docs/disaster-recovery.md` |
| **Infrastructure setup from clean state** | Manual | `setup.sh` | `sh infra/setup.sh && verify` |

### 5.2 Quality Gates

| Gate | Phase | Criteria | Action if Fail |
|------|-------|----------|----------------|
| **Security Gate** | Before Phase 1 | Secrets not in iCloud, file perms correct | Block phase transition |
| **Integration Gate** | Before Phase 3 | Health check + sync + alias work together | Fix before testing |
| **Test Gate** | Before Phase 4 | Pre-commit tests pass, scanner verified | Block phase transition |
| **Release Gate** | End of Phase 4 | All P0/P1 done, specs exist, playbook exists | Final review |

### 5.3 Monitoring Cadence

- **Daily**: Health check logs review (5s)
- **Weekly**: Rate limit report, cost projection (2min)
- **Monthly**: Full system audit — permissions, iCloud, backup integrity (15min)
- **Per Phase**: Gate review before transition

---

## Appendix A: Current State Baseline (Pre-Charter)

| Component | Status | Notes |
|-----------|--------|-------|
| OmniRoute | ✅ Running (58 models) | Combo name mismatch |
| Ollama | ✅ Running (cold) | No models loaded |
| Health Agent | ✅ launchd active | 401 error hourly |
| iCloud Secrets | ❌ CRITICAL | `.env.secrets` in iCloud |
| Sync Script | ❌ CRITICAL | `exit 0` race condition |
| Pre-commit hook | ⚠️ Partial | No tests |
| `.anesthos/specs/` | ❌ Empty | Only `.keep` |
| Medical code | ❌ None | SR-Agent only |

## Appendix B: Key Commands Reference

```bash
# Kiểm tra health log
tail -f ~/.omniroute/health.log

# Kiểm tra OmniRoute models
curl -s http://localhost:20128/v1/models | python3 -c "import sys,json; d=json.load(sys.stdin); [print(x['id']) for x in d['data']]"

# Kiểm tra Ollama
curl -s http://localhost:11434/api/ps | python3 -m json.tool

# Kiểm tra file permissions
stat -f "%p %N" ~/.omniroute/.env*

# Kiểm tra bypass audit
cat ~/.anesthos/bypass-audit.log 2>/dev/null || echo "No audit log yet"

# Verify infra setup
ls -la ~/projects/AnesthOS/infra/
```

---

*End of Project Charter — Version 1.0*
