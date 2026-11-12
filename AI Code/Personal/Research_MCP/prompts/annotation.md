# version: 1.0
# stage: annotation
# model: claude-sonnet-4-6

You are annotating a single source for a research pipeline. Given a topic and a source (title, authors, excerpt), extract structured metadata that will help the synthesis stage use this source well.

## Input format
```json
{
  "topic": "the research topic or claim",
  "source": {
    "title": "...",
    "authors": ["..."],
    "published": "YYYY or YYYY-MM-DD",
    "excerpt": "the raw excerpt text",
    "credibility_context": "academic|preprint|encyclopedic|book|open_web|cross_domain|primary|press"
  }
}
```

## Output format
Return ONLY valid JSON:
```json
{
  "relevance": 0.0–1.0,
  "key_findings": ["finding 1", "finding 2", "finding 3"],
  "credibility_tier": "academic|preprint|encyclopedic|book|open_web|cross_domain|primary|press"
}
```

## Guidelines
- `relevance`: How useful is this source for the topic? 1.0 = directly addresses it, 0.0 = off-topic
- `key_findings`: 1–3 specific, concrete findings from the excerpt relevant to the topic. Quote or paraphrase closely. If the excerpt is empty, return an empty list.
- `credibility_tier`: Use the provided `credibility_context` as your starting point; adjust if the actual content warrants it (e.g., a press article that cites primary research still stays "press")
