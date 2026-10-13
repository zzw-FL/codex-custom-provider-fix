# Codex++ Custom Provider Fix

A [Codex](https://github.com/openai/codex) skill that fixes `401 Unauthorized` errors when using custom model providers (local relays, OpenAI-compatible proxies, etc.).

## Problem

Codex++ caches model metadata in `~/.codex/models_cache.json`. When your custom models (e.g., via [one-api](https://github.com/songquanpeng/one-api), [LiteLLM](https://github.com/BerriAI/litellm), or any other relay) are missing from this cache, Codex falls back to the default `openai` provider and sends requests to `https://api.openai.com/v1/responses`. Your API key is for your own endpoint, not OpenAI's — hence the 401 error.

## What This Skill Does

1. **Discovers** your custom models from `~/.codex/model-catalogs/*.json`
2. **Injects** them into `~/.codex/models_cache.json` with the correct `model_provider` and `base_url`
3. **Repairs** any threads in `~/.codex/state_5.sqlite` that have the wrong provider assignment
4. **Backs up** files automatically before any mutation

## Installation

### Option 1: Install via Codex Skill Installer

```bash
codex skills install https://github.com/zzw-FL/codex-custom-provider-fix
```

### Option 2: Manual Install

```bash
git clone https://github.com/zzw-FL/codex-custom-provider-fix.git \
  ~/.codex/skills/codex-custom-provider-fix
```

On Windows:
```powershell
git clone https://github.com/zzw-FL/codex-custom-provider-fix.git `
  "$env:USERPROFILE\.codex\skills\codex-custom-provider-fix"
```

## Prerequisites

Before using this skill, ensure you have:

1. **A custom provider configured** in `~/.codex/config.toml`:
   ```toml
   model = "your-custom-model"
   model_provider = "custom"
   model_catalog_json = "model-catalogs/your-catalog.json"

   [model_providers.custom]
   name = "custom"
   wire_api = "responses"
   requires_openai_auth = true
   base_url = "http://127.0.0.1:57321/v1"
   ```

2. **A model catalog JSON** in `~/.codex/model-catalogs/` listing your custom models. Example:
   ```json
   {
     "models": [
       {
         "slug": "my-custom-model",
         "display_name": "My Custom Model",
         "model_provider": "custom"
       }
     ]
   }
   ```

## Usage

### In Codex Chat

Simply type in the Codex chat:
```
$codex-custom-provider-fix
```

Or describe the problem:
> "I'm getting 401 errors when switching to my custom model"

Codex will automatically run the repair script.

### Manual Execution

```bash
python ~/.codex/skills/codex-custom-provider-fix/scripts/repair_provider.py
```

On Windows:
```powershell
python "$env:USERPROFILE\.codex\skills\codex-custom-provider-fix\scripts\repair_provider.py"
```

Then **fully restart Codex++** (quit from system tray and reopen).

## Verification

After restart:
1. Start a new conversation with a custom model
2. Send a test message — it should respond without 401
3. Switch to another custom model in the same conversation — it should still work

## Why the Problem Keeps Coming Back

Codex++ occasionally refreshes `models_cache.json` from the server, which may overwrite custom entries. If 401 errors reappear after an app update or restart, simply re-run the script — it's idempotent and safe to use repeatedly.

## How It Works

The repair script:
1. Reads your `config.toml` to detect the custom provider name and `base_url`
2. Reads your model catalog JSON to discover all custom model slugs
3. Adds any missing models to `models_cache.json` with the correct provider metadata
4. Updates `state_5.sqlite` to fix threads that were incorrectly assigned to the `openai` provider

## Compatibility

- **Platforms**: macOS, Linux, Windows
- **Codex versions**: Desktop app (Codex++)
- **Providers**: Any OpenAI-compatible relay (one-api, LiteLLM, custom proxies, etc.)

## License

MIT
