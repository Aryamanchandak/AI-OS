# podcast-pipeline (CLI / automation)

Direct-callable Python CLI for the podcast pipeline. No MCP, no agent layer.

Use this when:
- You want to run the pipeline from a shell script or cron job
- Something breaks on the agent/MCP side and you need a fallback
- You want to automate ingestion or delivery without going through Claude

## Setup

```bash
pip install feedparser yt-dlp requests python-dotenv
```

Set `READWISE_TOKEN` in your environment (or a `.env` file in this directory) for delivery.

## Commands

```bash
# List episodes from an RSS feed
python run.py rss https://feeds.example.com/podcast.xml --limit 5

# List episodes from a YouTube channel
python run.py youtube UCxxxxxxxxxxxxxx --limit 5

# Download audio for any URL
python run.py download https://www.youtube.com/watch?v=xxxxx

# Push an HTML brief to Readwise Reader
python run.py deliver brief.html "Episode Title" https://source-url.com
```

## How it works

This file imports directly from the `podcast-brief MCP` project at:
`/Users/aryamanchandak/Documents/AI Code/Personal/Podcast pipeline/podcast-brief MCP`

All real logic lives there. This is just a thin CLI caller — simplify it however you like for automation.
