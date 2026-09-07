# Repository wiki brief

Make OpenWiki the canonical documentation for Agent Data Workbench. Write for developers trying the product, integrating an agent, and changing the code. Use English and plain, specific language. Keep the root README short and put detailed documentation here.

Document the runnable quickstart with real user-provided traces, architecture, trace import and exploration, bounded investigations and reviewed knowledge, task design and grader audits, grouped suites and target execution, exports and batch analysis, local FastAPI/TypeScript operation, and development/testing. Include SDK and CLI examples grounded in current source, source-linked diagrams where useful, and links between related workflows.

Explain meaningful boundaries: JSON type preservation; exact evidence checks versus interpretation; sampled versus corpus-wide results; lexical clustering limits; trusted command execution; source-group and final-split exposure bookkeeping; failed versus invalid outcomes; synthetic test results versus measured production performance. Document existing extension seams without claiming unimplemented connectors, Harbor integration, training execution, sandbox isolation, or automatic redaction.

Use repository source and tests as evidence. Do not treat removed legacy docs, local runs, credentials, provider login files, or installed dependencies as documentation inputs. Preserve the user’s Python 3.14, FastAPI, SQLAlchemy, React/TypeScript, Given / When / Then, and full-object comparison conventions.

Generate through Codex’s OpenWiki integration using its existing host session. Keep documentation maintenance on demand. Do not configure a paid API provider, scheduled CI generation, external connectors, or a public documentation deployment. OpenWiki’s generated setup text may mention a scheduled workflow; this repository has no such workflow configured.

Internal artifact IDs use canonical UUID strings, with suite names separate from IDs; external trace IDs are preserved. Document the version 0.3 project format and the explicit refusal to open older formats without rewriting them. The shipped product contains no demo commands, fake agent, or canned data. Test fixtures live only under tests/. Document domain API routers and FastAPI bearer dependencies, domain CLI modules, and shared persistence/report helpers.
