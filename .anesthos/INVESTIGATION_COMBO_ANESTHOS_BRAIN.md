# Investigation: Combo "anesthos-brain" Missing at Runtime

**Date**: 2026-07-12
**Status**: COMPLETED
**Author**: AI Engineer (Infrastructure Agent)

---

## Problem Statement

1. Model `claude-sonnet-4.5` appears in `/v1/models` with `owned_by: "combo"` but no combo named `anesthos-brain` is listed
2. Health check using `Authorization: Bearer sk-anesthos-brain-token` returns 401
3. Claude profile (`settings.json`) uses `anesthos-brain` as model and `sk-anesthos-brain-token` as auth token

---

## Findings

### Finding 1: Combo EXISTS in Database

```sql
sqlite3 ~/.omniroute/storage.sqlite "SELECT * FROM combos;"
```

Result:

| Column | Value |
|--------|-------|
| id | `anesthos-brain` |
| name | `anesthos-brain` |
| models | `["kr/claude-sonnet-4.5", "ag/claude-sonnet-4-6", "ag/gemini-2.5-pro"]` |
| strategy | `priority` |
| isHidden | `false` |
| createdAt | `2026-07-12T04:02:48` |
| sortOrder | `1` |

The combo IS properly configured in the database. It routes through:
1. `kr/claude-sonnet-4.5` (Kiro AI) — **primary**
2. `ag/claude-sonnet-4-6` (Antigravity) — **fallback 1**
3. `ag/gemini-2.5-pro` (Antigravity) — **fallback 2**

### Finding 2: OmniRoute API Does NOT List Combo Name as Model

OmniRoute's `/v1/models` API exposes combo MEMBER models under their original provider IDs, with `owned_by: "combo"` metadata. The combo NAME (`anesthos-brain`) is NOT registered as a model listing — it's a routing abstraction layer.

This is **normal OmniRoute behavior**. The combo name works at inference time (`/v1/chat/completions` with `model: "anesthos-brain"`) but is not enumerable via the models endpoint.

### Finding 3: Token `sk-anesthos-brain-token` is NOT Registered

Only one API key exists in OmniRoute:

```sql
sqlite3 ~/.omniroute/storage.sqlite "SELECT id, name, key FROM api_keys;"
```

| id | name | key |
|---|---|---|
| `92aad6e4-...` | Claude | `sk-6c05357ede94a37d-ccf177-56c35790` |

The token `sk-anesthos-brain-token` is **not registered** in the `api_keys` table. This causes 401 errors whenever:
- The health script (`omniroute-health.sh`) uses it for hourly completion probes
- Claude Desktop/CLI uses it (via `ANTHROPIC_AUTH_TOKEN` in `settings.json`)

### Finding 4: Where `sk-anesthos-brain-token` is Configured

The token is hardcoded in two places:

1. **Claude profile**: `~/.claude/profiles/anesthos/settings.json`
   ```json
   {
     "env": {
       "ANTHROPIC_BASE_URL": "http://localhost:20128/v1",
       "ANTHROPIC_AUTH_TOKEN": "sk-anesthos-brain-token",
       ...
     },
     "model": "anesthos-brain"
   }
   ```

2. **Health script**: `~/scripts/omniroute-health.sh` (line 43)
   ```bash
   -H "Authorization: Bearer sk-anesthos-brain-token"
   ```

---

## Root Cause

**The combo `anesthos-brain` was never missing.** The issue is a **token registration gap**:

1. Combo `anesthos-brain` exists in DB ✓
2. Combo is NOT hidden (`isHidden: false`) ✓
3. Combo routes through valid providers ✓
4. But `sk-anesthos-brain-token` was never registered as an API key ✗
5. Claude's profile uses this unregistered token, so every authenticated request fails with 401

Claude Code CLI currently works because OmniRoute may allow unauthenticated requests or the actual API key (`sk-6c05357ede94a37d-ccf177-56c35790`) is used elsewhere. The health script's hourly completion probe WILL fail because it uses the unregistered token.

---

## Recommended Fix (for WBS-4.4)

**Option A** (recommended): Register the token in OmniRoute
```bash
sqlite3 ~/.omniroute/storage.sqlite "
INSERT INTO api_keys (id, name, key, created_at, updated_at)
VALUES ('anesthos-brain-key', 'anesthos-brain', 'sk-anesthos-brain-token',
        datetime('now'), datetime('now'));
"
```

**Option B**: Update Claude profile + health script to use the existing valid key
```bash
# Replace sk-anesthos-brain-token with the actual registered key
# in both settings.json and omniroute-health.sh
```

---

## References

- Relevant files:
  - `~/.omniroute/storage.sqlite` — combo + api_keys table
  - `~/.claude/profiles/anesthos/settings.json` — Claude config with token
  - `~/scripts/omniroute-health.sh` — health script using token
  - `~/projects/AnesthOS/scripts/anesthos-sync.sh` — sync script
- WBS-4.4 will implement the fix
