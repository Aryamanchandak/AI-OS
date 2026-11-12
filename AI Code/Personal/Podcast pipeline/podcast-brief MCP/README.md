# podcast-brief

Generate research briefs from podcasts and push them to Readwise Reader.

For each episode, the pipeline:
1. Downloads audio (YouTube or RSS)
2. Transcribes with speaker diarization (Deepgram Nova-3)
3. Extracts typed claims via Claude
4. Researches each claim — papers (Semantic Scholar/arXiv), news (Brave, trusted sources only), or books/Wikipedia, depending on profile
5. Synthesises a structured brief with verbatim quotes, verdicts, caveats, and source links (Claude Opus)
6. Pushes the brief to your Readwise Reader inbox

Three profiles: `academic` (Lex), `current_events` (Ezra), `hybrid` (Senra).

---

## Setup

### 1. Install

```bash
git clone <your-repo>
cd podcast-brief
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

You also need `yt-dlp` available on your PATH. The `pip install` above brings in the Python wrapper, but on some systems you may want the standalone binary too:

```bash
# macOS
brew install yt-dlp ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
pipx install yt-dlp
```

`ffmpeg` is required for audio conversion.

### 2. API keys

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

Required:
- **`DEEPGRAM_API_KEY`** — [deepgram.com](https://deepgram.com) ($200 free credit, ~$0.30/hour after)
- **`ANTHROPIC_API_KEY`** — [console.anthropic.com](https://console.anthropic.com)
- **`READWISE_TOKEN`** — [readwise.io/access_token](https://readwise.io/access_token)

Optional (depending on profile):
- **`BRAVE_API_KEY`** — [brave.com/search/api](https://brave.com/search/api) — free tier: 2000 queries/month. Needed for `current_events` and `hybrid`.
- **`GOOGLE_BOOKS_API_KEY`** — [console.cloud.google.com](https://console.cloud.google.com) — optional for `hybrid`. Without it, Google Books still works but with stricter rate limits.

Verify everything's wired up:

```bash
podcast-brief check
```

### 3. Configure shows

Edit `config/shows.yaml`. Three example shows are included. For each new show:

```yaml
- name: "Show Name"
  sources:
    rss: "https://..."          # Find via "show name RSS"
    youtube_channel: "UC..."    # The UC... part of the channel URL
  profile: academic              # academic | current_events | hybrid
  speakers_hint: "Host is X. Guests vary."
  active: true
```

Either `rss` or `youtube_channel` is sufficient; both is best (RSS is preferred, YouTube is the fallback).

Edit `config/trusted_sources.yaml` to customise the news whitelist.

Edit `config/prompts/*.md` to tune how each profile writes briefs — these prompts are where most of the quality lives.

---

## Usage

### Manual: brief a single URL

```bash
podcast-brief brief "https://www.youtube.com/watch?v=..."
```

For an unconfigured URL, the pipeline auto-detects the show if the channel matches `shows.yaml`, otherwise uses the `hybrid` profile by default. Override:

```bash
podcast-brief brief "<url>" --profile academic
podcast-brief brief "<url>" --show "Lex Fridman Podcast"
podcast-brief brief "<url>" --transcript-only
podcast-brief brief "<url>" --skip-research      # cheaper, faster, less useful
```

### Automated: daily polling

```bash
podcast-brief poll                # check all active shows, process new episodes
podcast-brief poll --dry-run      # show what would be processed
```

To run automatically every morning at 4am, add to crontab (`crontab -e`):

```cron
0 4 * * * cd /path/to/podcast-brief && /path/to/podcast-brief/.venv/bin/podcast-brief poll >> /tmp/podcast-brief.log 2>&1
```

On macOS, `launchd` is more reliable than cron — see `cron-vs-launchd.md` notes if needed.

### Browse history

```bash
podcast-brief recent              # last 20 processed episodes
podcast-brief recent --limit 50
```

---

## iOS Shortcut (share-sheet → brief)

Run the local server:

```bash
uvicorn src.server:app --host 0.0.0.0 --port 8765
```

For phone access, the easiest path is [Tailscale](https://tailscale.com) — install on both devices, then your phone can reach the laptop on its tailnet IP.

Then create an iOS Shortcut:
1. Action: "Get Contents of URL"
2. URL: `http://<laptop-tailscale-ip>:8765/brief`
3. Method: POST
4. Headers: `Content-Type: application/json`
5. Request body (JSON): `{"url": "<Shortcut Input>"}`
6. Save to share sheet

Now share-sheet from Spotify, YouTube, Overcast, anywhere → "Send to Brief Pipeline" → it lands in Reader within ~10 mins.

For an extra security layer, set `PODCAST_BRIEF_API_TOKEN` in `.env` and append `?token=...` to the URL in the Shortcut.

---

## Cost expectation

Per 90-minute episode, roughly:

| Stage | Cost |
|---|---|
| Deepgram transcription | ~$0.45 |
| Claim extraction (Sonnet) | ~$0.10 |
| Research comparisons (Sonnet, ~10 calls) | ~$0.30 |
| Synthesis (Opus) | ~$0.50 |
| Brave search (free tier covers this) | $0 |
| **Per episode** | **~$1.30** |

5 episodes/week ≈ $25–30/month. You can drop this significantly by switching synthesis from Opus to Sonnet (`MODEL_SYNTHESIS` in `src/config.py`) at some quality cost — recommended after you've validated the Opus output is genuinely better for your shows.

---

## Project layout

```
podcast-brief/
├── config/
│   ├── shows.yaml                # your podcast subscriptions
│   ├── trusted_sources.yaml      # news whitelist
│   └── prompts/                  # synthesis prompts per profile
├── src/
│   ├── config.py                 # paths, models, config loaders
│   ├── state.py                  # SQLite for dedup and history
│   ├── ingest.py                 # YouTube + RSS audio fetching
│   ├── transcribe.py             # Deepgram + speaker name resolution
│   ├── extract.py                # Pass 1: typed claim extraction
│   ├── research/
│   │   ├── academic.py           # Semantic Scholar + arXiv
│   │   ├── news.py               # Brave + trusted sources
│   │   └── books.py              # Google Books + Wikipedia
│   ├── synthesize.py             # Pass 2: Opus produces final brief
│   ├── format.py                 # Markdown → HTML for Reader
│   ├── deliver.py                # Readwise Reader API
│   ├── pipeline.py               # End-to-end orchestrator
│   ├── poll.py                   # RSS + YouTube polling
│   ├── server.py                 # FastAPI for iOS Shortcut
│   └── cli.py                    # CLI entry point
└── /Users/aryamanchandak/Documents/AI Code/Core truth storage/Podcast_Data/
    ├── audio/                    # downloaded MP3s (delete periodically)
    ├── transcripts/              # cached JSON transcripts
    ├── briefs/                   # generated markdown + HTML
    └── state.db                  # SQLite — dedup + history
```

---

## Tuning notes

- **The synthesis prompts** (`config/prompts/*.md`) are where quality is determined. Iterate on these. Read your first few briefs and then refine the prompt — "more skeptical of overstatement," "shorter must-listen list," etc.
- **Speaker name resolution** is best-effort. For shows where it fails, edit `speakers_hint` in `shows.yaml` to be more specific.
- **The trusted source whitelist** is opinionated. The list in `trusted_sources.yaml` is a starting point — add or remove based on your standards.
- **Long episodes** (3+ hours): the transcript may exceed the prompt budget and get truncated (60% start + 20% end). For those, consider running `--profile hybrid` over `--profile academic` since hybrid is more forgiving.
- **Cleanup**: audio MP3s pile up. Add to your monthly maintenance: `find '/Users/aryamanchandak/Documents/AI Code/Core truth storage/Podcast_Data/audio' -mtime +14 -delete`.

---

## Troubleshooting

**"yt-dlp failed"** — Update yt-dlp; YouTube changes break older versions weekly: `pip install -U yt-dlp` or `brew upgrade yt-dlp`.

**Transcription is wrong about who is speaking** — Deepgram's diarization is good but not perfect. Edit `speakers_hint` to be very specific about voice characteristics if it matters.

**Research returns nothing** — Search queries from the extraction pass may be too specific. The synthesis pass will note "no papers found" rather than inventing citations.

**Reader API 401** — Token expired or wrong. Re-fetch from `readwise.io/access_token` and update `.env`.

**Pipeline runs but Reader is empty** — Check `podcast-brief recent` for status. If status is `error`, the brief generation succeeded but delivery failed; the markdown is saved to `/Users/aryamanchandak/Documents/AI Code/Core truth storage/Podcast_Data/briefs/` for recovery.
