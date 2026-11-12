"""T57 live verification: full-resolution image through cover-classification-v1.

Uses the exact production message shape from
merged-ingestion/src/ingestion/sources/book_metadata.py::_classify_page, but
calls the gateway client directly rather than through _classify_page, because
that function swallows every exception into is_cover=False -- which is exactly
the safe degradation T57 is trying to stop being necessary, and would hide a
max_ctx rejection instead of reporting it.
"""
import base64, json, pathlib, sys, time
from pydantic import BaseModel, ConfigDict
from llm_gateway.client import LLM

class CoverReadResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_cover: bool
    title: str | None = None
    author: str | None = None

photo = pathlib.Path(sys.argv[1])
data = base64.b64encode(photo.read_bytes()).decode("ascii")
print(f"photo:        {photo}")
print(f"file bytes:   {photo.stat().st_size:,}")
print(f"base64 chars: {len(data):,}  (pre-fix estimate would be ~{len(data)//4:,} tokens)")

PROMPT = (
    "Determine whether this photograph shows the front cover of a book. If it "
    "does, read the book title and author directly from the cover. Ignore blurbs, "
    "publisher names, awards, and series banners. Return the requested structured "
    "fields; use null for title and author when this is not a book cover."
)
media = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}[photo.suffix.casefold()]
messages = [{"role": "user", "content": [
    {"type": "text", "text": PROMPT},
    {"type": "image", "media_type": media, "data": data},
]}]

llm = LLM(base_url="http://127.0.0.1:8107")
start = time.time()
try:
    response = llm.chat(
        messages=messages,
        profile="cover-classification-v1",
        response_format={"type": "json_schema", "schema": CoverReadResult.model_json_schema()},
    )
except Exception as error:
    print(f"\nRESULT: REJECTED/ERROR after {time.time()-start:.1f}s")
    print(f"  {type(error).__name__}: {error}")
    sys.exit(1)
print(f"\nRESULT: ACCEPTED, completed in {time.time()-start:.1f}s")
print(f"  provider: {response.get('provider')}  model: {response.get('model')}  profile: {response.get('profile')}")
print(f"  parsed:   {json.dumps(response.get('parsed'))}")
