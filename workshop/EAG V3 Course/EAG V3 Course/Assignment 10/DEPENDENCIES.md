# Dependencies

Python is pinned to 3.11.15. Existing Python packages are resolved by the two committed uv.lock files; no Python dependency was added for desktop control.

cua-driver release 0.5.2 (binary reports 0.5.1): native controls, page access, recording and cursor overlay. Isolated in computer/backend.py; exit by replacing that adapter. Archive SHA256: 45bfd3244c4943fb677c83250d8c4323d1c8d0b8ea55045a65bf584bba24cb21.

mcp 1.27.2: Inherited catalogue tool transport; exit by replacing its tool adapter.

httpx 0.28.1: Gateway HTTP client; exit through the gateway clients.

ddgs 9.14.4: Inherited web-search fallback; exit by removing that MCP search backend.

tavily-python 0.7.25: Inherited web-search provider; exit by removing that provider adapter.

crawl4ai 0.8.6: Inherited page fetching; exit through the MCP fetch adapter.

python-dotenv 1.2.2: Local environment loading before client imports; exit through gateway configuration.

pydantic 2.13.4: Catalogue input/output contracts; exit by migrating those contracts together.

faiss-cpu 1.14.2: Inherited memory vector index; exit through vector_index.py.

numpy 2.4.6: Inherited vector arithmetic; exit through vector_index.py.

networkx 3.6.1: Inherited catalogue execution graph; exit through flow.Graph.

pyyaml 6.0.3: Plain task, key and catalogue configuration; exit by migrating those files.

playwright 1.60.0: Inherited browser skill; exit through browser/skill.py.

pillow 12.2.0: Window-image annotation; exit through computer/screen.py and inherited browser annotation.

trafilatura 2.0.0: Inherited HTML extraction; exit through browser/skill.py.

lxml 5.4.0: Inherited HTML processing; exit with the extraction backend.

lxml-html-clean 0.4.4: Inherited HTML cleaning; exit with the extraction backend.

pytest 9.0.3: Offline regression runner; exit by replacing the test harness.

pytest-asyncio 1.4.0: Async test execution; exit with the async test harness.

fastapi 0.136.3: Bundled V9 HTTP service; exit by replacing the gateway service.

uvicorn 0.48.0: Bundled V9 server process; exit through the gateway launch command.

jsonschema 4.26.0: Gateway response validation and offline driver-schema checks; exit through those boundaries.
