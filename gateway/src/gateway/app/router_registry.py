"""Generic registration of routers assembled by domain adapters."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import APIRouter, FastAPI


@dataclass(frozen=True, slots=True)
class RouterRegistration:
    router: APIRouter
    prefix: str
    tags: tuple[str, ...]


def register_routers(app: FastAPI, registrations: tuple[RouterRegistration, ...]) -> None:
    for registration in registrations:
        app.include_router(
            registration.router,
            prefix=registration.prefix,
            tags=list(registration.tags),
        )


def migrated_domain_registrations() -> tuple[RouterRegistration, ...]:
    """Return domain routers without exposing domain internals to app assembly."""

    from gateway.llm.api import registration as llm_registration

    return (llm_registration(),)
