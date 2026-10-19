# Exact model profiles

The implementation lives in `__init__.py`. `ProfileRegistry` loads version-1 `profiles.yaml` and exposes named `chat` and `embedding` profiles. `ProfileError` reports malformed or unknown profiles.

Each profile must pin non-empty `provider` and `model` strings. Embedding profiles also require a positive integer `dim`. Both sections must be non-empty mappings. Profiles containing `tier` or `route` are rejected because these profiles represent exact pins rather than routing instructions.

`resolve(kind, name)` returns a copy of a profile, with a useful list of known names on failure. `all(kind)` returns copies of the section entries for diagnostics.

The [profile resolution stage](../orchestration/README.md) copies chat pins onto the request, and provider execution checks the returned model. [LLMService](../README.md) resolves embedding profiles and checks returned vector dimensions. Requests cannot combine a profile with explicit provider/model selection.

`image-transcription-v1` pins local `gemma4:12b` through the `gemma` provider. Send image content to `/api/llm/chat` with this profile; use an `image_url` block containing a base64 `data:` URL. The gateway does not download image links.
