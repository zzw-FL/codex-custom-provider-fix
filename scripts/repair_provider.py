#!/usr/bin/env python3
"""
Repair Codex++ custom model provider routing.

Problem: Codex++ caches model metadata in models_cache.json. Custom models
configured via a local relay or third-party provider that are not in this cache
cause the app to fall back to the default 'openai' provider, sending requests
to api.openai.com and producing 401 errors because the user's key is for their
own endpoint, not OpenAI's.

This script:
1. Discovers custom models from the user's model-catalog JSON
2. Injects them into models_cache.json with the correct model_provider and base_url
3. Repairs any threads in state_5.sqlite that have the wrong provider assignment
4. Creates backups before any mutation

Usage:
    python repair_provider.py

The script is idempotent — safe to run multiple times.
"""

from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def error(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def info(msg: str) -> None:
    print(msg)


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def discover_catalog(codex_dir: Path) -> Path | None:
    """Find the user's model catalog JSON."""
    catalog_dir = codex_dir / "model-catalogs"
    if not catalog_dir.exists():
        return None

    # Prefer the catalog referenced by config.toml
    config_path = codex_dir / "config.toml"
    catalog_name: str | None = None
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("model_catalog_json"):
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        catalog_name = parts[1].strip().strip('"').strip("'")
                    break

    if catalog_name:
        candidate = catalog_dir / catalog_name
        if candidate.exists():
            return candidate

    # Fallback: first JSON file in the directory
    for child in sorted(catalog_dir.iterdir()):
        if child.suffix == ".json":
            return child

    return None


def read_custom_provider_config(codex_dir: Path) -> tuple[str, str]:
    """
    Read the custom provider name and base_url from config.toml.
    Returns (provider_name, base_url).
    """
    config_path = codex_dir / "config.toml"
    if not config_path.exists():
        return ("custom", "http://127.0.0.1:57321/v1")

    provider_name = "custom"
    base_url = ""
    current_section = ""

    with open(config_path, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped.startswith("[") and stripped.endswith("]"):
                current_section = stripped[1:-1]
                continue
            if stripped.startswith("model_provider"):
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    provider_name = parts[1].strip().strip('"').strip("'")
            if current_section.startswith("model_providers.") and stripped.startswith("base_url"):
                parts = stripped.split("=", 1)
                if len(parts) == 2:
                    base_url = parts[1].strip().strip('"').strip("'")

    if not base_url:
        base_url = "http://127.0.0.1:57321/v1"

    return (provider_name, base_url)


def build_cache_entry(catalog_model: dict, provider: str, base_url: str) -> dict:
    """Convert a model-catalog entry into a models_cache-compatible entry."""
    entry = {
        k: v
        for k, v in catalog_model.items()
        if k not in ("base_instructions", "instructions_template", "instructions_variables")
    }

    entry["model_provider"] = catalog_model.get("model_provider", provider)
    entry["base_url"] = base_url

    if "instructions_template" in catalog_model:
        entry.setdefault("model_messages", {})
        entry["model_messages"]["instructions_template"] = catalog_model["instructions_template"]
    if "base_instructions" in catalog_model:
        entry.setdefault("model_messages", {})
        entry["model_messages"]["persistent_instructions"] = catalog_model["base_instructions"]

    # Ensure required cache fields with sensible defaults
    entry.setdefault("description", catalog_model.get("display_name", catalog_model["slug"]))
    entry.setdefault("visibility", "list")
    entry.setdefault("supported_in_api", True)
    entry.setdefault("priority", 100)
    entry.setdefault("shell_type", "shell_command")
    entry.setdefault("apply_patch_tool_type", "freeform")
    entry.setdefault("web_search_tool_type", "text_and_image")
    entry.setdefault("supports_image_detail_original", True)
    entry.setdefault("supports_search_tool", True)
    entry.setdefault("supports_parallel_tool_calls", True)
    entry.setdefault("supports_reasoning_effort_updates", True)
    entry.setdefault("use_responses_lite", False)
    entry.setdefault("comp_hash", "custom")
    entry.setdefault("effective_context_window_percent", 100)
    entry.setdefault("node_repl_disabled", False)
    entry.setdefault("tool_mode", "code_mode_only")
    entry.setdefault("multi_agent_version", "v1")
    return entry


def repair_cache(codex_dir: Path, provider: str, base_url: str) -> tuple[int, list[str]]:
    cache_path = codex_dir / "models_cache.json"
    catalog_path = discover_catalog(codex_dir)

    if catalog_path is None:
        error("No model catalog JSON found in ~/.codex/model-catalogs/")

    if not cache_path.exists():
        error(f"models_cache.json not found: {cache_path}")

    cache = load_json(cache_path)
    catalog = load_json(catalog_path)

    existing_slugs = {m["slug"] for m in cache.get("models", [])}
    added = 0
    custom_slugs: list[str] = []

    for catalog_model in catalog.get("models", []):
        slug = catalog_model["slug"]
        custom_slugs.append(slug)
        if slug in existing_slugs:
            continue
        cache["models"].append(build_cache_entry(catalog_model, provider, base_url))
        existing_slugs.add(slug)
        added += 1

    if added:
        save_json(cache_path, cache)

    return added, custom_slugs


def repair_db(codex_dir: Path, custom_slugs: list[str], provider: str) -> int:
    db_path = codex_dir / "state_5.sqlite"
    if not db_path.exists() or not custom_slugs:
        return 0

    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()

    # Build a query that matches any of the custom model slugs
    placeholders = ",".join("?" for _ in custom_slugs)
    query = (
        f"UPDATE threads SET model_provider = ? "
        f"WHERE model IN ({placeholders}) AND model_provider != ?"
    )
    c.execute(query, (provider, *custom_slugs, provider))
    fixed = c.rowcount
    conn.commit()
    conn.close()
    return fixed


def main() -> int:
    codex_dir = Path.home() / ".codex"

    if not codex_dir.exists():
        error(f"Codex directory not found: {codex_dir}")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    # Backup cache
    cache_path = codex_dir / "models_cache.json"
    if cache_path.exists():
        shutil.copy2(cache_path, codex_dir / f"models_cache.json.backup-{stamp}")

    provider, base_url = read_custom_provider_config(codex_dir)
    info(f"Detected provider: '{provider}'  base_url: {base_url}")

    added, custom_slugs = repair_cache(codex_dir, provider, base_url)
    fixed = repair_db(codex_dir, custom_slugs, provider)

    info(f"models_cache.json: added {added} custom model(s)")
    info(f"state_5.sqlite:    fixed {fixed} thread(s)")

    if added or fixed:
        info("")
        info("Repair complete. Fully restart Codex++ for changes to take effect.")
    else:
        info("")
        info("Nothing to repair — custom models are already configured correctly.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
