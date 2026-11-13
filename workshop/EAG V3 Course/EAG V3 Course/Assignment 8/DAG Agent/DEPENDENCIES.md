# Dependencies

Python is pinned to 3.11.15. uv.lock pins all resolved packages.

The original Anthropic dependency is restored and pinned for direct provider calls. Only agent/llm.py imports its SDK; no AI OS service, gateway, configuration, or database is used. The SDK owns retries and HTTP transport. Standard-library adapters handle local files and public web text.

- annotated-types 0.8.0: SDK model metadata. Exit: remove or replace its owning direct dependency.
- anthropic 0.125.0: direct Claude API access. Exit: remove or replace its owning direct dependency.
- anyio 4.16.0: SDK transport concurrency. Exit: remove or replace its owning direct dependency.
- certifi 2026.10.23: SDK TLS certificates. Exit: remove or replace its owning direct dependency.
- colorama 0.4.6: Windows test output. Exit: remove or replace its owning direct dependency.
- contourpy 1.3.3: chart contour backend. Exit: remove or replace its owning direct dependency.
- cycler 0.12.1: chart style cycle. Exit: remove or replace its owning direct dependency.
- distro 1.9.0: SDK platform metadata. Exit: remove or replace its owning direct dependency.
- docstring-parser 0.18.0: SDK tool metadata. Exit: remove or replace its owning direct dependency.
- fonttools 4.68.0: chart fonts. Exit: remove or replace its owning direct dependency.
- h11 0.16.0: SDK HTTP protocol. Exit: remove or replace its owning direct dependency.
- httpcore 1.0.9: HTTP transport core. Exit: remove or replace its owning direct dependency.
- httpx 0.28.1: Anthropic SDK HTTP transport. Exit: remove or replace its owning direct dependency.
- idna 3.20: SDK HTTP host encoding. Exit: remove or replace its owning direct dependency.
- iniconfig 2.3.1: pytest configuration. Exit: remove or replace its owning direct dependency.
- jiter 0.19.0: SDK JSON parsing. Exit: remove or replace its owning direct dependency.
- kiwisolver 1.5.1: chart layout. Exit: remove or replace its owning direct dependency.
- matplotlib 3.9.4: PNG charts. Exit: remove or replace its owning direct dependency.
- numpy 2.4.6: chart numerical arrays. Exit: remove or replace its owning direct dependency.
- packaging 26.3: package versions. Exit: remove or replace its owning direct dependency.
- pillow 13.0.0: chart image encoding. Exit: remove or replace its owning direct dependency.
- pluggy 1.7.0: pytest plugins. Exit: remove or replace its owning direct dependency.
- pydantic 2.14.3: SDK response models. Exit: remove or replace its owning direct dependency.
- pydantic-core 2.50.4: SDK model validation. Exit: remove or replace its owning direct dependency.
- pygments 2.21.0: pytest highlighting. Exit: remove or replace its owning direct dependency.
- pyparsing 3.3.3: chart parsing. Exit: remove or replace its owning direct dependency.
- pytest 8.4.2: test runner. Exit: remove or replace its owning direct dependency.
- python-dateutil 4.0.0: chart date handling. Exit: remove or replace its owning direct dependency.
- pyyaml 6.0.3: YAML contracts/configuration. Exit: remove or replace its owning direct dependency.
- sniffio 1.3.1: SDK async transport detection. Exit: remove or replace its owning direct dependency.
- typing-extensions 4.16.0: SDK typing compatibility. Exit: remove or replace its owning direct dependency.
- typing-inspection 0.4.5: SDK type inspection. Exit: remove or replace its owning direct dependency.
- tzdata 2026.6: locked supporting library. Exit: remove or replace its owning direct dependency.
