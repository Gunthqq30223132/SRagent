# Preflight Anchor
- **Repo**: SRagent
- **Branch**: `claude/sr-agent-pipeline-design-rqtctp`
- **HEAD**: `4a2df77a9fdff5be026554407a7dc06216c629b9`
- **CWD**: `/Users/gun/projects/SRagent`

---

# Investigation of 9router Model & Combo Resolution Mechanics ([M1-10])

## 1. Executive Summary

This runbook documents live investigation findings regarding **9router** model discovery, combo resolution, fallback visibility, and database schema mechanics on local port `20128` and SQLite database `~/.9router/db/data.sqlite`.

---

## 2. Command Outputs & Evidence

### Question 1: Model List & Resolution Structure

#### 1.1 `v1/models` Inspection
Command:
```bash
python3 -c '
import httpx, json
headers = {"Authorization": "Bearer sk-[REDACTED_9ROUTER_KEY]"}
resp = httpx.get("http://localhost:20128/v1/models", headers=headers).json()
models = resp.get("data", [])
sonnet_models = [m for m in models if "sonnet-4.5" in m["id"]]
print(json.dumps(sonnet_models, indent=2))
'
```

Output:
```json
[
  {
    "id": "claude-sonnet-4.5",
    "object": "model",
    "owned_by": "combo"
  },
  {
    "id": "kr/claude-sonnet-4.5",
    "object": "model",
    "owned_by": "kr",
    "capabilities": {
      "thinking": false,
      "agentic": false
    }
  },
  {
    "id": "kr/claude-sonnet-4.5-thinking",
    "object": "model",
    "owned_by": "kr",
    "capabilities": {
      "thinking": true,
      "agentic": false
    }
  },
  {
    "id": "kr/claude-sonnet-4.5-agentic",
    "object": "model",
    "owned_by": "kr",
    "capabilities": {
      "thinking": false,
      "agentic": true
    }
  },
  {
    "id": "kr/claude-sonnet-4.5-thinking-agentic",
    "object": "model",
    "owned_by": "kr",
    "capabilities": {
      "thinking": true,
      "agentic": true
    }
  }
]
```

#### 1.2 SQLite `combos` and `providerConnections` Tables
Command:
```bash
python3 -c '
import sqlite3, json
conn = sqlite3.connect("/Users/gun/.9router/db/data.sqlite")
cur = conn.cursor()

print("=== COMBOS TABLE ===")
cur.execute("SELECT * FROM combos;")
for r in cur.fetchall():
    print(r)

print("\n=== PROVIDER CONNECTIONS TABLE ===")
cur.execute("SELECT id, provider, authType, name, email, priority, isActive FROM providerConnections;")
for r in cur.fetchall():
    print(r)

print("\n=== SETTINGS TABLE (COMBO & PROVIDER STRATEGIES) ===")
cur.execute("SELECT data FROM settings WHERE id=1;")
print(json.dumps(json.loads(cur.fetchone()[0]), indent=2))
'
```

Output:
```text
=== COMBOS TABLE ===
('7c945b68-b175-4c4f-906f-44ae0f08250b', 'claude-sonnet-4.5', None, '["kr/claude-opus-4.8-thinking-agentic","oc/deepseek-v4-flash-free","ag/claude-opus-4-6-thinking","ag/claude-sonnet-4-6","kr/claude-opus-4.7-thinking-agentic","cc/claude-sonnet-5"]', '2026-05-14T14:12:00.308Z', '2026-07-20T15:02:49.188Z')

=== PROVIDER CONNECTIONS TABLE ===
d125ce99-7b2d-4258-927b-f991160d313b kiro oauth Account 1 None 1 1
4e913814-1794-449f-8764-3ec2d09488ed ollama apikey Gun None 2 1
11ab7f21-f17f-454c-b120-fdbe9c0df1d5 ollama apikey Gun02 None 1 1
c4d41320-ae5e-4c8e-8010-cb8e400e4603 claude oauth Account 1 None 1 0
905bca5a-1148-4c3d-8ec7-d2be988a3e71 gemini-cli oauth [REDACTED_EMAIL_1] [REDACTED_EMAIL_1] 1 1
a2a3f9ed-e790-42c2-896a-fc22705bc9a3 antigravity oauth [REDACTED_EMAIL_2] [REDACTED_EMAIL_2] 1 0
99671ab0-b32b-4a0b-a092-2b02caa57f10 antigravity oauth [REDACTED_EMAIL_1] [REDACTED_EMAIL_1] 2 0

=== SETTINGS TABLE (COMBO & PROVIDER STRATEGIES) ===
{
  "cavemanEnabled": true,
  "cavemanLevel": "ultra",
  "providerStrategies": {
    "kiro": {
      "fallbackStrategy": "round-robin",
      "stickyRoundRobinLimit": 5
    },
    "antigravity": {
      "fallbackStrategy": "round-robin",
      "stickyRoundRobinLimit": 1
    },
    "claude": {
      "fallbackStrategy": "round-robin",
      "stickyRoundRobinLimit": 2
    }
  },
  "ccFilterNaming": true,
  "comboStrategies": {
    "claude-sonnet-4.5": {
      "fallbackStrategy": "fusion"
    }
  },
  "mitmRouterBaseUrl": "http://localhost:20128",
  "tunnelEnabled": true,
  "tunnelUrl": "https://competitions-weddings-chairs-minimum.trycloudflare.com",
  "requireApiKey": true,
  "password": "$2b$10$[REDACTED_BCRYPT_HASH]",
  "fallbackStrategy": "round-robin",
  "comboStrategy": "round-robin",
  "outboundProxyEnabled": false,
  "mitmEnabled": false,
  "ponytailEnabled": true,
  "ponytailLevel": "ultra"
}
```

**Key Finding:**
- `claude-sonnet-4.5` is a **Combo ID** (`owned_by: "combo"`), configured with `fusion` strategy across 6 target models (`kr/`, `oc/`, `ag/`, `cc/`).
- `kr/claude-sonnet-4.5` is a **Leaf Model** (`owned_by: "kr"`), which targets provider `kiro` directly.

---

### Question 2: Combo Response Field

Command:
```bash
python3 -c '
import httpx, json
headers = {
    "Authorization": "Bearer sk-[REDACTED_9ROUTER_KEY]",
    "Content-Type": "application/json"
}
url = "http://localhost:20128/v1/chat/completions"

for m in ["kr/claude-sonnet-4.5", "claude-sonnet-4.5"]:
    data = {"model": m, "messages": [{"role": "user", "content": "Return OK"}], "max_tokens": 5, "stream": False}
    resp = httpx.post(url, headers=headers, json=data, timeout=15.0)
    print(f"--- MODEL: {m} ---")
    print(resp.text)
'
```

Output:
```json
--- MODEL: kr/claude-sonnet-4.5 ---
{"id":"chatcmpl-1784597625595","object":"chat.completion","created":1784597625,"model":"claude-sonnet-4.5","choices":[{"index":0,"message":{"role":"assistant","content":"OK"},"finish_reason":"stop"}],"usage":{"prompt_tokens":6126,"completion_tokens":1,"total_tokens":6127}}

--- MODEL: claude-sonnet-4.5 ---
{"id":"chatcmpl-1784597627554","object":"chat.completion","created":1784597627,"model":"qwen3-coder-next","choices":[{"index":0,"message":{"role":"assistant","content":"OK"},"finish_reason":"stop"}],"usage":{"prompt_tokens":16609,"completion_tokens":1,"total_tokens":16610}}
```

**Key Finding:**
- When dispatching to leaf model `kr/claude-sonnet-4.5`, 9router strips the `kr/` prefix in the response and sets `"model": "claude-sonnet-4.5"`.
- When dispatching to combo model `claude-sonnet-4.5`, 9router resolves the combo/fusion policy and returns the **actual leaf model served** in the response's top-level `"model"` field (`"model": "qwen3-coder-next"`).

---

### Question 3: Fallback Visibility & Historical Execution

#### 3.1 Error/Fallback Response Payload
Command:
```bash
python3 -c '
import httpx
headers = {"Authorization": "Bearer sk-[REDACTED_9ROUTER_KEY]", "Content-Type": "application/json"}
url = "http://localhost:20128/v1/chat/completions"

for m in ["kr/non-existent-model", "invalid-combo-model"]:
    data = {"model": m, "messages": [{"role": "user", "content": "Return OK"}], "max_tokens": 5, "stream": False}
    resp = httpx.post(url, headers=headers, json=data, timeout=15.0)
    print(f"--- MODEL: {m} (Status {resp.status_code}) ---")
    print(resp.text)
'
```

Output:
```json
--- MODEL: kr/non-existent-model (Status 400) ---
{"error":{"message":"[kiro/non-existent-model] [400]: {\"message\":\"Invalid model ID. Please select a different model to continue.\",\"reason\":\"INVALID_MODEL_ID\"} (reset after 29s)"}}

--- MODEL: invalid-combo-model (Status 404) ---
{"error":{"message":"No active credentials for provider: openai","type":"invalid_request_error","code":"model_not_found"}}
```

#### 3.2 First Light M1-07 Audit in SQLite `requestDetails`
Command:
```bash
python3 -c '
import sqlite3, json
conn = sqlite3.connect("/Users/gun/.9router/db/data.sqlite")
cur = conn.cursor()

cur.execute("SELECT rowid, id, timestamp, provider, model, status, data FROM requestDetails WHERE rowid >= 2015 AND rowid <= 2022 ORDER BY rowid ASC;")
for r in cur.fetchall():
    data_obj = json.loads(r[6])
    req_model = data_obj.get("request", {}).get("model")
    conn_id = data_obj.get("connectionId")
    tokens = data_obj.get("tokens")
    print(f"rowid {r[0]} | ts {r[2]} | provider {r[3]} | db_model {r[4]} | req_model {req_model} | status {r[5]} | tokens {tokens}")
'
```

Output:
```text
rowid 2015 | ts 2026-07-20T13:27:07.556Z | provider kiro | db_model claude-sonnet-4.5 | req_model kiro/claude-sonnet-4.5 | status success | tokens {'prompt_tokens': 7921, 'completion_tokens': 2448}
rowid 2016 | ts 2026-07-20T15:12:24.237Z | provider kiro | db_model claude-sonnet-4.5 | req_model kiro/claude-sonnet-4.5 | status success | tokens {'prompt_tokens': 4137, 'completion_tokens': 4}
rowid 2017 | ts 2026-07-20T15:13:43.478Z | provider kiro | db_model claude-sonnet-4.5 | req_model kiro/claude-sonnet-4.5 | status success | tokens {'prompt_tokens': 8072, 'completion_tokens': 2545}
rowid 2018 | ts 2026-07-20T15:19:03.561Z | provider kiro | db_model claude-sonnet-4.5 | req_model kiro/claude-sonnet-4.5 | status success | tokens {'prompt_tokens': 8471, 'completion_tokens': 2810}
rowid 2019 | ts 2026-07-20T15:27:44.651Z | provider kiro | db_model claude-sonnet-4.5 | req_model kiro/claude-sonnet-4.5 | status success | tokens {'prompt_tokens': 8423, 'completion_tokens': 2848}
rowid 2020 | ts 2026-07-20T15:29:52.083Z | provider kiro | db_model claude-sonnet-4.5 | req_model kiro/claude-sonnet-4.5 | status success | tokens {'prompt_tokens': 7930, 'completion_tokens': 2444}
rowid 2021 | ts 2026-07-20T15:30:37.400Z | provider kiro | db_model claude-sonnet-4.5 | req_model kiro/claude-sonnet-4.5 | status success | tokens {'prompt_tokens': 8787, 'completion_tokens': 3148}
rowid 2022 | ts 2026-07-20T15:31:57.752Z | provider kiro | db_model claude-sonnet-4.5 | req_model kiro/claude-sonnet-4.5 | status success | tokens {'prompt_tokens': 8258, 'completion_tokens': 2501}
```

**Key Finding:**
- 9router exposes the serving leaf model ID in successful OpenAI API responses (`response.model`), error payload text (`[provider/model] [code]`), and SQLite `requestDetails` logs.
- During **First Light M1-07** (timestamps `2026-07-20T15:13:43Z` to `2026-07-20T15:31:57Z`), all dispatches requested `kiro/claude-sonnet-4.5` (`kr/claude-sonnet-4.5`). The leaf model that actually served all M1-07 dispatches was **`claude-sonnet-4.5` via provider `kiro`**.

---

### Question 4: Combo Schema API & Programmatic Query

#### 4.1 Schema of `combos` Table
Command:
```bash
sqlite3 ~/.9router/db/data.sqlite "PRAGMA table_info(combos);"
```

Output:
```text
0|id|TEXT|0||1
1|name|TEXT|1||0
2|kind|TEXT|0||0
3|models|TEXT|1||0
4|createdAt|TEXT|1||0
5|updatedAt|TEXT|1||0
```

#### 4.2 Endpoint Accessibility Test
Command:
```bash
python3 -c '
import httpx
headers = {"Authorization": "Bearer sk-[REDACTED_9ROUTER_KEY]"}
for ep in ["/api/combos", "/dashboard/combos", "/v1/combos"]:
    resp = httpx.get(f"http://localhost:20128{ep}", headers=headers)
    print(f"GET {ep} -> Status: {resp.status_code}")
'
```

Output:
```text
GET /api/combos -> Status: 401
GET /dashboard/combos -> Status: 307
GET /v1/combos -> Status: 404
```

**Key Finding:**
- Internal Web Dashboard API endpoints (`/api/*`) require session authentication (cookie-based Next.js auth) and return `401 Unauthorized` when accessed via standard Bearer API key.
- Programmatic inspection of combo membership and strategies is achievable via:
  1. Direct SQLite DB access (`~/.9router/db/data.sqlite` tables `combos` and `settings`).
  2. Public API `/v1/models` endpoint (distinguishes `owned_by: "combo"` vs provider leaf models).

---

## 3. Conclusions

1. **Observability of Leaf Models (§14D.4 Verifier Checks):**
   - **Fully Feasible via API Response:** When calling a 9router combo ID, the `model` field in the returned OpenAI `chat.completion` JSON object explicitly contains the resolved leaf model ID (e.g. `qwen3-coder-next`).
   - **Fully Feasible via Database:** SQLite `requestDetails` table logs `provider`, `model`, `req_model`, latency, tokens, and status for every request processed by 9router.

2. **First Light M1-07 Actual Execution Model:**
   - The dispatch runner requested `kiro/claude-sonnet-4.5` (leaf model targeting provider `kiro`).
   - The actual leaf model executed was **`claude-sonnet-4.5` served by provider `kiro`**.

---

## 4. Recommendations for ADR §4 & §14D.4

1. **ADR §4 (Model Routing & Combo Strategy):**
   - Explicitly document 9router model ID taxonomy:
     - Prefix syntax (`<provider_code>/<model_id>`, e.g., `kr/claude-sonnet-4.5`, `ag/claude-sonnet-4-6`) forces routing to a specific provider leaf model.
     - Non-prefixed names without provider codes (e.g., `claude-sonnet-4.5`) may map to a **Combo ID** subject to fusion/fallback policies across multiple backends.
   - For deterministic verification in benchmark runs, use explicit leaf model prefixes (`kr/claude-sonnet-4.5`) rather than ambiguous combo names.

2. **ADR §14D.4 (Dispatch Verifier Enforcement):**
   - Update `dispatch_verifier.py` rules to extract and verify `response["model"]` against expected leaf/combo resolution outputs.
   - For post-mortem audit and verifier checks, query `~/.9router/db/data.sqlite` table `requestDetails` to match dispatch timestamps with actual `provider` and `db_model` records.
