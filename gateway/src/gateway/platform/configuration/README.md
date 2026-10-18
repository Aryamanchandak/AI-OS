# Configuration loading and paths

This folder resolves the gateway's configuration files and validates process settings. It loads configuration; it does not implement LLM provider selection or pricing policy.

| File | Responsibility |
| --- | --- |
| `settings.py` | Defines the immutable `GatewaySettings` model and loads gateway YAML. Requires a plain hostname/IP, a port between 1 and 65535, and a supported log level; rejects extra fields. |
| `glc.py` | Derives the AI OS root, gateway configuration root, and SQLite root; exposes `GLCPaths` and a required-YAML-mapping loader. |
| `__init__.py` | Re-exports the settings loader, path constants, and `GLCPaths`. |

`GLCPaths` reads `GLC_CONFIG_DIR`, `GLC_GATEWAY_DB`, `GLC_AUDIT_DB`, and `GLC_CACHE_DB`. Defaults point to the gateway's `config` folder and the sibling `Database/sqlite` folder. User-home markers in overridden paths are expanded.

The gateway YAML loader fails on missing files, malformed YAML, non-mapping documents, or invalid settings. LLM-specific configuration such as profiles, pricing, budgets, and cache settings is loaded by the owning LLM components using these resolved paths. See [application startup](../../app/README.md).
