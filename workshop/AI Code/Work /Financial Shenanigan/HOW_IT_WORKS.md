# How finShin.py Works — Plain English Explainer

---

## The Big Picture

You give the script one PDF (an annual report). It sends that PDF to Google's Gemini AI five times simultaneously, each time with a different set of instructions asking Gemini to look for a specific category of accounting manipulation. Each run is an independent "specialist agent." All five run at the same time (not one after another), and each prints its findings when it's done.

That's it. The whole script is: upload file → ask five questions at once → print five answers.

---

## What You Need Before Running

**1. A `.env` file in the same folder as `finShin.py`**

This file stores your secret API key so you don't hard-code it in the script. It should look like this:

```
API_KEY=AIzaSyXXXXXXXXXXXXXXXXXXXXXXXXX
```

The script reads this with `load_dotenv()` on line 7. Without it, `os.getenv("API_KEY")` returns `None` and the Gemini client fails to initialise.

**2. The annual report PDF**

Currently hard-coded as `84b8783b-111a-4ad3-8ebb-a508950025a2.pdf` in the same folder as the script. To analyse a different company, replace this filename.

**3. The five prompt files in the `Prompts/` subfolder**

```
Prompts/
  Foundation.md
  Earnings.md
  CashFLOW.md
  Acquisition.md
  keyMetrics.md
```

Each of these is a long, detailed instruction document that tells Gemini exactly what to look for. Think of them as job descriptions — one for each specialist.

---

## Step-by-Step: What Happens When You Run `python finShin.py`

### Step 1 — Load the API key

```python
load_dotenv()
client = genai.Client(api_key=os.getenv("API_KEY"))
```

`load_dotenv()` reads your `.env` file and puts `API_KEY` into the environment. Then `os.getenv("API_KEY")` fetches it and hands it to the Gemini client. The `client` object is now your authenticated connection to Google's Gemini API — every call to Gemini in this script goes through it.

---

### Step 2 — Work out where the files are

```python
BASE = Path(__file__).parent
```

`__file__` is Python's built-in variable that holds the path to the currently running script. `.parent` gets the folder it lives in. So if your script is at:

```
/Users/aryaman/Financial Shenanigan/finShin.py
```

Then `BASE` equals:

```
/Users/aryaman/Financial Shenanigan/
```

Every other path in the script is built on top of `BASE`, so the script works no matter where you run it from.

---

### Step 3 — Upload the PDF to Gemini

```python
ar = client.files.upload(path=str(BASE / "84b8783b-111a-4ad3-8ebb-a508950025a2.pdf"))
```

This is a critical step that's easy to misunderstand. You can't just pass a local file path to Gemini — Gemini is a cloud API and it can't read files off your laptop. So this line actually **uploads** the PDF to Google's servers and returns a reference object (`ar`).

Think of `ar` as a ticket stub. It doesn't contain the PDF — it's a pointer that says "the file lives at this URL on Google's servers." Every time you want Gemini to read the annual report, you pass `ar` rather than the actual file bytes.

This upload happens **once**. All five agents reuse the same `ar`, so the PDF is only transferred over the network a single time.

**Example of what `ar` looks like under the hood (simplified):**
```
File(name="files/abc123xyz", uri="https://generativelanguage.googleapis.com/v1beta/files/abc123xyz")
```

---

### Step 4 — Define the `analyze` function

```python
async def analyze(prompt_file, label):
    r = await client.aio.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            (BASE / "Prompts" / prompt_file).read_text(),
            ar
        ]
    )
    print(f"\n{label}\n{r.text}")
```

This function is the core unit of work. It represents **one specialist agent**. Here's exactly what it takes and what it does:

**Inputs:**
- `prompt_file` — the filename of the instruction document, e.g. `"Earnings.md"`
- `label` — a display name, e.g. `"Earnings Manipulation"`, printed as a header above the output

**What it does internally:**

1. `(BASE / "Prompts" / prompt_file).read_text()` — reads the full text of the instruction file from disk. For example, `Earnings.md` is ~3,000 words of detailed instructions telling Gemini what earnings manipulation looks like, what signals to find, where to look in the filing, and how to format its answer.

2. `client.aio.models.generate_content(...)` — sends a request to Gemini with two things in `contents`:
   - The instruction text (the prompt)
   - `ar` (the reference to the uploaded annual report PDF)

   Gemini reads both together. It uses the instructions to know what to look for, and the PDF as the source material to search through.

3. `r.text` — the full text of Gemini's response. This contains all the findings for that shenanigan category.

4. `print(f"\n{label}\n{r.text}")` — prints the label as a header followed by Gemini's analysis.

**Why `async`?**

The `async` keyword means this function can be paused mid-execution while waiting for Gemini to respond, allowing other functions to run in the meantime. Gemini typically takes 10–30 seconds to read a large annual report and generate findings. Without `async`, the script would sit idle waiting for the first agent to finish before even starting the second one. With `async`, all five start at the same time.

---

### Step 5 — Run all five agents simultaneously

```python
async def main():
    await asyncio.gather(
        analyze("Foundation.md",   "Foundation & Framework"),
        analyze("Earnings.md",     "Earnings Manipulation"),
        analyze("CashFLOW.md",     "Cash Flow Shenanigans"),
        analyze("Acquisition.md",  "Acquisition Accounting"),
        analyze("keyMetrics.md",   "Key Metrics"),
    )
```

`asyncio.gather()` takes multiple async tasks and runs them **concurrently**. It's the equivalent of hiring five analysts and handing them each a copy of the annual report at the same moment, rather than waiting for analyst 1 to finish before briefing analyst 2.

**Timeline comparison:**

Without concurrency (sequential):
```
[Agent 1: 25s] → [Agent 2: 25s] → [Agent 3: 25s] → [Agent 4: 25s] → [Agent 5: 25s]
Total: ~125 seconds
```

With `asyncio.gather` (concurrent):
```
[Agent 1: 25s]
[Agent 2: 25s]  ← all start at the same time
[Agent 3: 25s]
[Agent 4: 25s]
[Agent 5: 25s]
Total: ~25 seconds
```

Each `analyze(...)` call is one specialist being briefed. `await asyncio.gather(...)` waits for all five to complete before the script exits.

---

### Step 6 — Start the event loop

```python
asyncio.run(main())
```

`async` functions don't run on their own — they need an event loop to manage the concurrency. `asyncio.run()` creates that event loop, runs `main()` inside it, and shuts it down cleanly when `main()` is done. This is always the last line in a script that uses `async`.

---

## The Five Specialists — What Each One Looks For

Each specialist gets the same annual report but completely different instructions:

| Agent | Prompt File | What it looks for |
|---|---|---|
| **Foundation & Framework** | `Foundation.md` | Governance red flags, board independence, auditor relationship, and whether the income statement, balance sheet, and cash flow statement tell a consistent story. Looks for structural conditions that *enable* manipulation. |
| **Earnings Manipulation** | `Earnings.md` | Seven categories: revenue recognised too early, fake revenue, income inflated with one-time events, expenses deferred, expenses hidden, income deferred, and future expenses pulled into the current period. |
| **Cash Flow Shenanigans** | `CashFLOW.md` | Three categories: financing cash disguised as operating cash, operating outflows disguised as investing outflows, and operating cash inflated through unsustainable tactics like stretching payables or cutting inventory. |
| **Acquisition Accounting** | `Acquisition.md` | Three categories: using acquisitions to artificially boost revenue or earnings, inflating operating cash flow via inherited working capital, and using non-GAAP metrics to obscure the true cost of deals. |
| **Key Metrics** | `keyMetrics.md` | Two categories: misleading non-GAAP metrics that overstate performance (adjusted EBITDA, organic growth), and balance sheet metrics distorted to hide deterioration (DSO, inventory days, debt ratios). |

---

## How the Prompt Files Shape the Output

Each `.md` file in `Prompts/` is a structured instruction document. When Gemini receives it alongside the PDF, it behaves as if it were a specialist who has read and memorised that document before opening the annual report.

For example, `Earnings.md` tells Gemini things like:

- *"Look for revenue recognised before delivery is complete — specific signal: check whether revenue growth significantly outpaces cash collections"*
- *"Look for bill-and-hold arrangements — specific signal: unusual inventory on customer premises disclosed in footnotes"*
- *"For every signal you find, report: technique name | location in the filing | what you observed | signal strength (High/Medium/Low) | mitigating factors | confidence level"*

The prompt is the difference between asking a general question ("does this company manipulate its earnings?") and giving an expert a forensic checklist to work through systematically.

---

## Data Flow Diagram

```
.env file
   │
   └─ API_KEY
         │
         ▼
   Gemini Client (authenticated)
         │
         ├─ Upload PDF ──────────────────────────────► Google File Store
         │                                                     │
         │                                                     └─ ar (file reference)
         │
         └─ asyncio.gather fires 5 concurrent calls:
               │
               ├─ analyze("Foundation.md") ─── [Foundation.md text] + [ar] ──► Gemini ──► prints findings
               ├─ analyze("Earnings.md")   ─── [Earnings.md text]   + [ar] ──► Gemini ──► prints findings
               ├─ analyze("CashFLOW.md")   ─── [CashFLOW.md text]  + [ar] ──► Gemini ──► prints findings
               ├─ analyze("Acquisition.md")─── [Acquisition.md text]+ [ar] ──► Gemini ──► prints findings
               └─ analyze("keyMetrics.md") ─── [keyMetrics.md text] + [ar] ──► Gemini ──► prints findings
```

---

## To Analyse a Different Company

1. Drop the new annual report PDF into the same folder as `finShin.py`
2. Change line 19:
   ```python
   ar = client.files.upload(path=str(BASE / "YOUR_NEW_FILE.pdf"))
   ```
3. Run `python finShin.py`

The prompts don't change — they are written to work on any company's annual report.
