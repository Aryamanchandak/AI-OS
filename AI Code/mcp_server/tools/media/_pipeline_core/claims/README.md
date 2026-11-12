# Claims

This package contains reusable claim extraction and claim verification contracts/services
that can be used by MCP tools.

It still accepts arbitrary content and arbitrary claim lists. MCP-facing code can import
these models directly instead of redefining claim shapes per tool.

The podcast MCP scaffolds intentionally stop at generic boundaries here. Integration with
research-project-specific claim extraction and verification services is tracked separately
and should not be wired into this server until that project is moved over on purpose.
