---
name: codex-custom-provider-fix
description: >
  Fix Codex++ routing to custom model providers (e.g., local relays like
  one-api, litellm, or any OpenAI-compatible proxy). Use when switching
  models causes 401 Unauthorized errors from api.openai.com because custom
  models are missing from the internal models_cache.json or threads have
  the wrong model_provider in the state database.
metadata:
  short-description: Fix custom model 401 errors in Codex++
---

# Codex Custom Provider Fix

## When to Use

Activate this skill when the user reports:
- `unexpected status 401 Unauthorized: Incorrect API key provided` from `https://api.openai.com/v1/responses`
- Switching to a custom model in a conversation fails with 401
- Custom models work in a fresh conversation but not after switching

Root cause: Codex++ caches model metadata in `~/.codex/models_cache.json`. When custom
models (configured via a local relay or third-party provider) are absent from this cache,
the app falls back to the default `openai` provider and sends requests to the official
OpenAI endpoint. The user's API key is for their own endpoint, not OpenAI, so the key
is rejected.

## What It Does

1. Discovers custom models from the user's model-catalog JSON (`~/.codex/model-catalogs/`)
2. Injects them into `~/.codex/models_cache.json` with the correct `model_provider` and `base_url`
3. Repairs any threads in `~/.codex/state_5.sqlite` that have the wrong provider
4. Creates timestamped backups automatically before any mutation

## Prerequisites

The user must already have:
- A custom provider configured in `~/.codex/config.toml` (e.g., `[model_providers.custom]`)
- A model catalog JSON in `~/.codex/model-catalogs/` listing their custom models
- The custom provider's `base_url` set in the config

## How to Run

If the user asks to fix the 401 / custom model routing issue, execute the repair script:

```bash
python "$HOME/.codex/skills/codex-custom-provider-fix/scripts/repair_provider.py"
```

On Windows:
```powershell
python "$env:USERPROFILE\.codex\skills\codex-custom-provider-fix\scripts\repair_provider.py"
```

After the script runs, tell the user to **fully restart Codex++** (quit from the system tray
and reopen) for the changes to take effect.

## Post-Repair Verification

After restart, the user should:
1. Start a new conversation with any custom model
2. Send a test message and confirm it responds without 401
3. Switch to another custom model in the same conversation and confirm it still works

## If the Problem Returns

Codex++ occasionally refreshes `models_cache.json` from the server, which may overwrite
the custom entries. If 401 errors reappear after an app update or restart, re-run the
same script — it is idempotent and safe to run repeatedly.
