# `evidence/test_evidence.py`

One test, `test_exact_passage_verification_rejects_paraphrase`, covering `verify_claims`.

A `SourceRecord` whose `extracted_text` is `"Revenue increased by 12 percent in the quarter."`. Two drafts against it: one quoting the same sentence but with extra internal whitespace (`"Revenue   increased by 12 percent..."`), and one that paraphrases (`"Revenue surged strongly"`, which never appears in the source). Asserts exactly one accepted and one rejected claim, and that the accepted claim has `passage_verified=True`.

This is the core guarantee of the module: whitespace differences don't break verification (the normalization step is doing its job), but a claim whose quoted passage isn't literally present — even a claim that's plausibly true — is rejected outright. It's a deliberate "fail closed" design: correctness of the underlying fact doesn't matter, only whether the cited text actually contains the quoted words. The test doesn't cover the `"unknown source"` rejection path, case-insensitivity, or the pydantic-validation-error rejection path (blank `claim`) — those are untested here.
