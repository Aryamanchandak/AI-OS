# Configuration loading and paths

This folder resolves the gateway's configuration files and database paths. It loads configuration; it does not implement LLM provider selection or pricing policy.

| File | Responsibility |
| --- | --- |
| `glc.py` | Derives the AI OS root, gateway configuration root, and SQLite root; exposes `GLCPaths`. YAML is read only by [`gateway/config.py`](../../config.py). |
| `__init__.py` | Re-exports path constants and `GLCPaths`. |

`GLCPaths` reads `GLC_CONFIG_DIR` and `GLC_GATEWAY_DB`. Defaults point to the gateway's `config` folder and the sibling `Database/sqlite` folder. User-home markers in overridden paths are expanded.

LLM-specific configuration such as profiles, pricing, and budgets is loaded by the owning LLM components using these resolved paths. See [application startup](../../app/README.md).
