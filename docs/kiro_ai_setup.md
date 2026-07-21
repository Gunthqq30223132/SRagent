# Direct Kiro AI Setup in Antigravity

Kiro AI provides the `kr/claude-sonnet-4.5` model as a direct integration for Antigravity IDE and Antigravity 2.0.

Because OmniRoute has been decommissioned, follow these instructions to establish the direct connection to Kiro AI.

---

## Configuration Settings

Open your `settings.json` file located at:
- `~/Library/Application Support/Antigravity IDE/User/settings.json`
- (or `~/Library/Application Support/Antigravity/User/settings.json`)

And configure the Kiro API settings:

```json
{
  "antigravity.overrideBaseUrl": "https://api.kiro.ai/v1",
  "antigravity.model": "kr/claude-sonnet-4.5",
  "antigravity.apiKey": "kiro"
}
```

### Authentication Details

Kiro AI authentication natively routes through AWS Builder ID / OIDC. If you are using Antigravity, the IDE can establish direct OIDC authentication. For manual/headless configuration, you can use your credential token as the `antigravity.apiKey`.
