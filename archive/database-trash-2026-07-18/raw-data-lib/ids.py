import hashlib
import secrets
from .config import SOURCE_REGISTRY


def normalize(body: str) -> str:
    lines = [line.rstrip() for line in body.splitlines()]
    return "\n".join(lines)


def content_hash(body: str) -> str:
    return hashlib.sha256(normalize(body).encode()).hexdigest()


def code_for(source: str) -> str:
    reverse = {value: key for key, value in SOURCE_REGISTRY.items()}
    if source not in reverse:
        raise ValueError(f"Unknown source: {source!r}. Add to SOURCE_REGISTRY.")
    return reverse[source]


def mint_item_id(source: str) -> str:
    rand4 = "".join(secrets.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(4))
    return f"{code_for(source)}_{rand4}"
