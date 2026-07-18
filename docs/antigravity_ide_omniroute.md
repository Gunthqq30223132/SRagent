# Configure Antigravity IDE directly for Kiro and Ollama

This guide explains how to configure **Antigravity IDE** (located at `~/.antigravity-ide/` with application configuration under `~/Library/Application Support/Antigravity/` and `~/Library/Application Support/Antigravity IDE/`) to connect directly to the **Kiro API** and local **Ollama** instances.

By pointing the IDE to these endpoints directly, you bypass local proxies and leverage native performance.

---

## Method 1: Using Built-in AI Settings (Recommended)

To configure the built-in AI routing within the Antigravity IDE:

1. Open **Antigravity IDE**.
2. Open Settings using the keyboard shortcut `Cmd + ,` (or go to **Code / Antigravity IDE** -> **Settings** -> **Settings**).
3. Search for "Antigravity AI" in the settings search bar.
4. Set the following configuration values in your user settings:
   - **Antigravity AI: Override Base URL** (`antigravity.overrideBaseUrl`): `https://api.kiro.ai/v1`
   - **Antigravity AI: Model** (`antigravity.model`): `kr/claude-sonnet-4.5`
   - **Antigravity AI: API Key** (`antigravity.apiKey`): `kiro` (or your personal Kiro API Key)

Alternatively, you can edit your `settings.json` file directly:
- **Path**: `~/Library/Application Support/Antigravity IDE/User/settings.json` (or `~/Library/Application Support/Antigravity/User/settings.json`)
- Add the following keys:
  ```json
  {
    "antigravity.overrideBaseUrl": "https://api.kiro.ai/v1",
    "antigravity.model": "kr/claude-sonnet-4.5",
    "antigravity.apiKey": "kiro",
    "antigravity.ollama.overrideBaseUrl": "http://localhost:11434/v1",
    "antigravity.ollama.model": "qwen2.5:7b-instruct",
    "antigravity.ollama.apiKey": "ollama",
    "antigravity.ollama.baseUrl": "http://localhost:11434/v1"
  }
  ```

---

## Method 2: Configuring Popular Coding Extensions

If you use AI extensions inside Antigravity IDE, configure them directly:

### 1. Cline (formerly Prevvy)
Open `settings.json` and configure:
- **Kiro AI Configuration**:
  ```json
  {
    "cline.apiProvider": "openai",
    "cline.openAiBaseUrl": "https://api.kiro.ai/v1",
    "cline.openAiModelId": "kr/claude-sonnet-4.5",
    "cline.openAiApiKey": "kiro"
  }
  ```
- **Ollama Configuration**:
  ```json
  {
    "cline.apiProvider": "ollama",
    "cline.ollamaBaseUrl": "http://localhost:11434",
    "cline.ollamaModelId": "qwen2.5:7b-instruct"
  }
  ```

### 2. Continue
Open the Continue configuration file (usually at `~/.continue/config.json`) and define the model block:
```json
{
  "models": [
    {
      "title": "Kiro AI (Direct)",
      "provider": "openai",
      "model": "kr/claude-sonnet-4.5",
      "apiBase": "https://api.kiro.ai/v1",
      "apiKey": "kiro"
    },
    {
      "title": "Ollama Qwen2.5 (Direct)",
      "provider": "ollama",
      "model": "qwen2.5:7b-instruct"
    }
  ]
}
```

### 3. Roo Code
In Roo Code extension settings:
- **For Kiro AI**:
  - **API Provider**: `OpenAI Compatible`
  - **Base URL**: `https://api.kiro.ai/v1`
  - **Model ID**: `kr/claude-sonnet-4.5`
  - **API Key**: `kiro`
- **For Ollama**:
  - **API Provider**: `Ollama`
  - **Base URL**: `http://localhost:11434`
  - **Model ID**: `qwen2.5:7b-instruct`
