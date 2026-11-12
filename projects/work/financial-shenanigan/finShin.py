import os, asyncio
import pandas as pd
from pathlib import Path
from google import genai
from dotenv import load_dotenv

# BASE is the folder this script lives in — all paths are relative to it
# so the script works regardless of where you run it from
BASE = Path(__file__).parent

# Load API_KEY from the .env file sitting next to this script.
# Passing the explicit path means it works no matter what directory
# you run python from (avoids the "searches cwd" gotcha).
load_dotenv(BASE / ".env")
print("KEY:", os.getenv("API_KEY"))

# Initialise the Gemini client using the API key from the environment
client = genai.Client(api_key=os.getenv("API_KEY"))

# Upload the annual report PDF to Gemini's file store.
# Gemini needs the file hosted on its side before it can be passed into a prompt.
# The returned object (ar) is a reference we reuse across all 5 agent calls.
ar = client.files.upload(file=str(BASE / "Angel One.pdf"))

async def analyze(prompt_file, label):
    """
    Run a single specialist agent against the uploaded annual report.

    prompt_file  — filename inside the Prompts/ folder (e.g. "Earnings.md").
                   Each file contains the full system-level instruction that
                   tells Gemini which shenanigan category to look for and exactly
                   how to structure its findings.
    label        — human-readable name printed as a section header in the output.

    Gemini receives two things: the prompt text and the PDF file reference.
    It reads the full annual report and responds with its forensic findings
    for that specific shenanigan category.
    """
    r = await client.aio.models.generate_content(
        model="gemini-3.1-pro-preview",
        contents=[
            (BASE / "Prompts" / prompt_file).read_text(),  # specialist prompt
            ar                                              # the annual report PDF
        ]
    )
    print(f"\n{label}\n{r.text}")
    # Return the label and findings so main() can collect them into a dataframe
    return {"agent": label, "findings": r.text}

async def main():
    """
    Fire all 5 specialist agents at the same time using asyncio.gather.
    Each agent is independent — they all get the same PDF but look for
    different categories of accounting shenanigans simultaneously.
    Results print as each one finishes (order may vary).
    """
    results = await asyncio.gather(
        analyze("Foundation.md",   "Foundation & Framework"),   # governance + cross-statement divergences
        analyze("Earnings.md",     "Earnings Manipulation"),     # 7 income-statement shenanigans
        analyze("CashFLOW.md",     "Cash Flow Shenanigans"),     # 3 cash-flow shenanigans
        analyze("Acquisition.md",  "Acquisition Accounting"),    # 3 acquisition-related shenanigans
        analyze("keyMetrics.md",   "Key Metrics"),               # misleading non-GAAP / KPI manipulation
    )

    # Build a dataframe — one row per agent, two columns: agent name and its full findings text
    df = pd.DataFrame(results)

    # Save to Excel so findings are easy to read, share, and filter
    output_path = BASE / "findings.xlsx"
    df.to_excel(output_path, index=False)
    print(f"\nSaved to {output_path}")

# Entry point — asyncio.run() starts the event loop and runs main() to completion
asyncio.run(main())


