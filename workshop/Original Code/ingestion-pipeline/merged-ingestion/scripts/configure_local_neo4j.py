"""Configure the local Neo4j credential and persist it in ``AI Code/.env``.

The generated password is never printed. Existing process/environment values
remain the source of the current credential; a first-time local Neo4j install
falls back to the vendor default (neo4j/neo4j).
"""

from __future__ import annotations

import os
import secrets
import stat
import tempfile
from pathlib import Path

from dotenv import dotenv_values
from neo4j import GraphDatabase


def _ai_code_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if parent.name == "AI Code":
            return parent
    raise RuntimeError("Cannot locate the enclosing AI Code directory")


def _updated_env_text(original: str, values: dict[str, str]) -> str:
    pending = dict(values)
    output: list[str] = []
    for line in original.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in pending:
                output.append(f"{key}={pending.pop(key)}")
                continue
        output.append(line)
    if output and output[-1]:
        output.append("")
    output.extend(f"{key}={value}" for key, value in pending.items())
    return "\n".join(output) + "\n"


def main() -> None:
    env_path = _ai_code_root() / ".env"
    original = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
    file_values = {
        key: value
        for key, value in dotenv_values(env_path).items()
        if isinstance(value, str)
    }

    uri = os.getenv("NEO4J_URI") or file_values.get("NEO4J_URI") or "bolt://localhost:7687"
    username = (
        os.getenv("NEO4J_USERNAME")
        or file_values.get("NEO4J_USERNAME")
        or "neo4j"
    )
    current_password = (
        os.getenv("NEO4J_PASSWORD")
        or file_values.get("NEO4J_PASSWORD")
        or "neo4j"
    )
    database = (
        os.getenv("NEO4J_DATABASE")
        or file_values.get("NEO4J_DATABASE")
        or "neo4j"
    )
    new_password = secrets.token_urlsafe(32)

    updated = _updated_env_text(
        original,
        {
            "NEO4J_URI": uri,
            "NEO4J_USERNAME": username,
            "NEO4J_PASSWORD": new_password,
            "NEO4J_DATABASE": database,
        },
    )
    existing_mode = stat.S_IMODE(env_path.stat().st_mode) if env_path.exists() else 0o600
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=env_path.parent,
            prefix=".env.neo4j.",
            delete=False,
        ) as temporary:
            temporary.write(updated)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        temporary_path.chmod(existing_mode)

        with GraphDatabase.driver(uri, auth=(username, current_password)) as driver:
            driver.execute_query(
                "ALTER CURRENT USER SET PASSWORD "
                "FROM $current_password TO $new_password",
                current_password=current_password,
                new_password=new_password,
                database_="system",
            )

        os.replace(temporary_path, env_path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)

    print("Neo4j credential configured and saved to the shared root .env.")


if __name__ == "__main__":
    main()
