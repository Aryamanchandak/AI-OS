"""Typed KG storage errors (PLAN Phase 1 — fail-closed writes).

The store historically degraded gracefully — a failed connect or write logged
an error and returned normally, so a dispatcher could record ``done`` for a
projection Neo4j never received. Phase 1 makes the ingestion path fail loud:
preflight and (in strict mode) every ingestion read/write either succeed or
raise one of these.

    KGStoreError
    ├── KGUnavailableError   # dependency missing / cannot connect / db not open
    ├── KGConfigurationError # server stores graph data outside the approved root
    ├── KGSchemaError        # required constraints missing or uncreatable
    ├── KGReadError          # a read (incl. identity lookup) failed to answer
    └── KGWriteError         # a write failed

Key rule (ground rule 2): an unavailable identity lookup raises
``KGReadError`` / ``KGUnavailableError`` — it is *never* interpreted as
"no candidate exists", which would let the pipeline mint a duplicate concept.
"""

from __future__ import annotations


class KGStoreError(Exception):
    """Base class for all fail-closed KG storage errors."""


class KGUnavailableError(KGStoreError):
    """Neo4j is unreachable, its driver is missing, or the database is not open."""


class KGConfigurationError(KGStoreError):
    """Neo4j is reachable but its physical storage configuration is unsafe."""


class KGSchemaError(KGStoreError):
    """A required uniqueness constraint is missing and could not be created."""


class KGReadError(KGStoreError):
    """A KG read failed — the graph could not answer the query."""


class KGWriteError(KGStoreError):
    """A KG write failed."""
