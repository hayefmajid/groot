<div align="center">

<img src="groot_tokenslim_logo.png" alt="Groot Logo" width="220"/>

# 🌿 I'm Groot.

**Groot** is a Claude Code hook that intercepts every prompt before it reaches the LLM and compresses it — saving **up to 70% of tokens** on average, without losing meaning.

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://python.org)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Hook-orange.svg)](https://claude.ai/code)

</div>

---

## 🚀 What it does

Every time you type a prompt in Claude Code, Groot intercepts it, compresses it using a local or cloud LLM, and re-injects the compressed version — transparently, before Claude ever sees it.

**Result:** your context window lasts significantly longer, API costs drop, and long sessions stay sharp.

```
You type:   "can you tell me if the application will be sold on the Belgian market and how many users we expect"
Groot sends: "app Belgian market launch + expected users?"
Savings:    ~68% fewer tokens
```

---

## 📊 Compression Performance

| Metric | Value |
|--------|-------|
| **Average token savings** | **~70%** |
| Best case | up to 85% |
| Minimum threshold | configurable (default: 10 words) |
| Modes | `full` (~70% target) · `extra` (~85% target) |

> Groot skips compression automatically for short prompts, code blocks, and XML tool calls — only natural language is compressed.

---

## 📦 Files

```
groot.py              ← Main hook (UserPromptSubmit)
groot-toggle.ps1      ← Toggle ON/OFF script
.groot-config.json    ← Configuration template
install-commands.ps1  ← One-click installer
slash-commands/
  groot.md            ← /groot          toggle ON/OFF
  groot-show.md       ← /groot-show     current config
  groot-stats.md      ← /groot-stats    compression stats
  groot-config.md     ← /groot-config   set a config key
  groot-type.md       ← /groot-type     full | extra mode
  groot-llm.md        ← /groot-llm      change LLM provider
  groot-tokens.md     ← /groot-tokens   set word threshold
  groot-validate.md   ← /groot-validate toggle auto-Enter
  groot-files.md      ← /groot-files    toggle PDF/TXT/MD extraction
```

---

## ⚙️ Installation

### 1. Clone the repo

```bash
git clone https://github.com/hayefmajid/groot.git
cd groot
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the installer (PowerShell)

```powershell
.\install-commands.ps1
```

This will:
- Copy `groot.py` to `~/.claude/hooks/`
- Copy `groot-toggle.ps1` to `~/.claude/hooks/`
- Initialize `.groot-config.json` in `~/.claude/hooks/` (only if not already present)
- Install all `/groot-*` slash commands in `~/.claude/commands/`
- Patch `~/.claude/settings.json` to register the `UserPromptSubmit` hook

### 4. Restart Claude Code

Groot is now active. Every prompt you send will be compressed before reaching Claude.

---

## 🎮 Slash Commands

| Command | Description |
|---------|-------------|
| `/groot` | Toggle compression **ON / OFF** |
| `/groot-show` | Show current configuration |
| `/groot-stats` | View compression statistics |
| `/groot-type full` | Standard compression (~70% savings) |
| `/groot-type extra` | Aggressive compression (~85% savings) |
| `/groot-llm ollama` | Switch LLM provider |
| `/groot-llm openai sk-yourkey` | Set cloud provider + API key |
| `/groot-tokens 20` | Set minimum word threshold |
| `/groot-validate` | Toggle manual validation (no auto-Enter) |
| `/groot-files` | Toggle PDF / TXT / MD extraction |

---

## 🔌 LLM Providers

Groot supports **local** and **cloud** LLM providers for compression:

| Provider | Type | Default model |
|----------|------|---------------|
| `llama` | Local (llama.cpp) | configurable |
| `ollama` | Local | llama3.2 |
| `lmstudio` | Local | local-model |
| `openai` | Cloud | gpt-4o-mini |
| `anthropic` | Cloud | claude-haiku-4-5 |
| `groq` | Cloud | llama-3.1-8b-instant |
| `mistral` | Cloud | mistral-small-latest |

Switch provider at any time with `/groot-llm <provider>`.

---

## 🛠️ Configuration

Config file: `~/.claude/hooks/.groot-config.json`

```json
{
  "active": true,
  "min_words": 10,
  "compression_type": "full",
  "validate_mode": false,
  "file_extraction_enabled": true,
  "llm_provider": "llama",
  "providers": { ... }
}
```

| Key | Description |
|-----|-------------|
| `active` | Enable/disable compression |
| `min_words` | Skip compression for prompts shorter than N words |
| `compression_type` | `full` (70%) or `extra` (85%) |
| `validate_mode` | `true` = paste without auto-Enter (manual review) |
| `file_extraction_enabled` | Inline PDF/TXT/MD files into the compressed prompt |
| `llm_provider` | Active provider name |

---

## 🌳 How it works

```
[You type a prompt]
        ↓
[UserPromptSubmit hook triggered]
        ↓
[groot.py reads the prompt]
        ↓
[Too short or already compressed? → pass through]
        ↓
[Send to LLM (local or cloud) for compression]
        ↓
[Block original prompt → re-inject compressed version]
        ↓
[Claude receives the compressed prompt]
```

Groot runs **entirely locally** when using llama/ollama/lmstudio — nothing leaves your machine except what you send to Claude.

---

## 📜 License

MIT — use it, fork it, compress it.

---

<div align="center">
<i>I'm Groot.</i>
</div>
