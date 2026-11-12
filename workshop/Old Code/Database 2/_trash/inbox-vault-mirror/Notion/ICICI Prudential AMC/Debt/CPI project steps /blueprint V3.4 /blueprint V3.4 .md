

# Main Document — Migration to Blueprint v3.4 (Multi-Feature Input)

Purpose: Replace the single-lag, single-feature architecture described in Blueprint v3.3 with the corrected multi-feature input architecture (v3.4). This document records the required changes at a high level and serves as the authoritative summary to apply to the codebase and blueprint file.

# Blueprint v3.4 — Multi-Feature Input (Text to replace / update v3.3)

Version: v3.4

Change log: Replaces single-lag input requirement (v3.3) with multi-feature input. All other behaviours and strict/fail-fast philosophy remain as described in v3.3.

Each target entry in TARGET_REGISTRY must now include feature_columns. Keep lag_column present for compatibility but treat feature_columns as the authoritative input list.

Example (textual, exact fields to include — do not invent values):

Replace every instance of:

With:

Validation required (fail fast):

All model implementations must conform to the following minimal interface (no extra fields):

Important notes (exact behavioural rules):

Add or update tests to assert:

# End — minimal scope

This blueprint update contains only the required textual and contract changes to move v3.3 → v3.4 (Multi-Feature Input). No other behavioural changes, code, or assumptions were added.

If you want, I will now (only) apply these exact textual replacements to the blueprint file you will upload.

