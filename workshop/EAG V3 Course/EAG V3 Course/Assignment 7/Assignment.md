Assignment
Deadline is always 7 days.

Build something that uses RAG well, and prove the architecture is intact.

Pass the eight base queries (A through H) from this session. Verbatim, within the iteration bounds named alongside each.

Build a real RAG application over a corpus of fifty or more items. Pick a path:

a Chrome plugin that indexes pages you visit;
a desktop or cloud app over documents you choose;
any application that needs retrieval to work.
Design five queries against your corpus. Each must answer correctly with the index and fail without it. At least two must require semantic recall, where the query's words do not appear in the chunks that answer it.

Architectural rules carry over from this session. The grep test on Perception's SYSTEM stays the gate: zero MCP tool names inside. Adding a new MCP tool for a file format your corpus needs is welcome; its docstring is where Decision learns about it.

Submit a GitHub repository (README with the corpus manifest, the eight base traces, and the five custom traces with their no-corpus comparison), and a short video.