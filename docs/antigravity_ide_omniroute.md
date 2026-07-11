# Configure Antigravity IDE to Route Through OmniRoute

This guide explains how to configure **Antigravity IDE** (located at `~/.antigravity-ide/` with application configuration under `~/Library/Application Support/Antigravity/` and `~/Library/Application Support/Antigravity IDE/`) to route its AI queries through **OmniRoute**.

By pointing the IDE to OmniRoute, it will automatically utilize the `anesthos-brain` combo model running locally on port `20128` with priority-fallback and token-saving compression.

---

## Method 1: Using Built-in AI Settings (Recommended)

To configure the built-in AI routing within the Antigravity IDE:

1. Open **Antigravity IDE**.
2. Open Settings using the keyboard shortcut `Cmd + ,` (or go to **Code / Antigravity IDE** -> **Settings** -> **Settings**).
3. Search for "Antigravity AI" or "Base URL" in the settings search bar.
4. Set the following configuration values in your user settings:
   - **Antigravity AI: Override Base URL** (or `antigravity.overrideBaseUrl` in `settings.json`):
     ```
     http://localhost:20128/v1
     ```
   - **Antigravity AI: Model** (or `antigravity.model` in `settings.json`):
     ```
     anesthos-brain
     ```
   - **Antigravity AI: API Key** (or `antigravity.apiKey` in `settings.json`):
     ```
     sk-anesthos-brain-token
     ```

Alternatively, you can edit your `settings.json` file directly:
- **Path**: `~/Library/Application Support/Antigravity IDE/User/settings.json` (or `~/Library/Application Support/Antigravity/User/settings.json`)
- Add the following keys:
  ```json
  {
    "antigravity.overrideBaseUrl": "http://localhost:20128/v1",
    "antigravity.model": "anesthos-brain",
    "antigravity.apiKey": "sk-anesthos-brain-token"
  }
  ```

---

## Method 2: Configuring Popular Coding Extensions

If you use AI extensions inside Antigravity IDE, configure them to route through OmniRoute's local endpoint:

### 1. Cline (formerly Prevvy)
Open `settings.json` and configure:
```json
{
  "cline.apiProvider": "openai",
  "cline.openAiBaseUrl": "http://localhost:20128/v1",
  "cline.openAiModelId": "anesthos-brain",
  "cline.openAiApiKey": "sk-anesthos-brain-token"
}
```

### 2. Continue
Open the Continue configuration file (usually at `~/.continue/config.json`) and define the model block:
```json
{
  "models": [
    {
      "title": "AnesthOS Brain",
      "provider": "openai",
      "model": "anesthos-brain",
      "apiBase": "http://localhost:20128/v1",
      "apiKey": "sk-anesthos-brain-token"
    }
  ],
  "tabAutocompleteModel": {
    "title": "AnesthOS Brain",
    "provider": "openai",
    "model": "anesthos-brain",
    "apiBase": "http://localhost:20128/v1",
    "apiKey": "sk-anesthos-brain-token"
  }
}
```

### 3. Roo Code
In Roo Code extension settings:
- **API Provider**: `OpenAI Compatible`
- **Base URL**: `http://localhost:20128/v1`
- **Model ID**: `anesthos-brain`
- **API Key**: `sk-anesthos-brain-token`
