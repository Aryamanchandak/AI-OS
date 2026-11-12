import os

from google import genai
from mcp.server.fastmcp import FastMCP

from shared.backend_utils import get_gemini_file

mcp = FastMCP("ara")

ARA_PROMPT = '''
You are a Senior Equity Research Analyst at a leading Asset Management Company. Your task is to produce a comprehensive, institutional-grade **Annual Report Analysis (ARA)** tailored for the Chief Investment Officer (CIO). This analysis will directly support high-stakes investment committee decisions, portfolio allocation, and risk oversight.

Your output must be a **standalone, authoritative document**, strictly grounded in the contents of the provided annual report. Do not include any assumptions, estimates, or external data. Every insight, data point, or judgment must be explicitly supported by disclosures in the report.

---

### 🔷 STRUCTURE & DELIVERABLE

#### I. Executive Summary — **Key Findings** (8–12 Bullet Points)
- Deliver high-impact, decision-useful insights upfront.
- Include material developments in:
  - Business performance and segment drivers
  - Strategic direction and capital allocation
  - Financial strength, cash generation, leverage
  - Governance, audit observations, and red flags
- Each bullet must convey **what changed**, **why it matters**, and **the investment implication**.
- Keep this section concise but powerful — tailored for a CIO skimming for actionable insight.

---

#### II. Deep-Dive Institutional Analysis

Structure the following sections organically based on actual disclosures in the annual report. Use clear section headers, crisp narrative, and **Markdown tables wherever financial or comparative data is disclosed** (these tables should be directly copy-pastable into Microsoft Word).

##### A. **Chairman's / CEO / CFO Messages – Strategic Tone & Priorities**
- Summarize key themes from leadership messages.
- Highlight tone, stated goals, shareholder alignment, capital allocation signals, and strategic pivots.
- Flag any shifts in management's risk posture or market outlook.

##### B. **MD&A Highlights – Operational & Strategic Insights**
- Extract core commentary on operating performance, segment dynamics, and macro environment.
- Cover cost structures, margin drivers, competitive positioning, and regulatory context.
- Emphasize stated forward-looking guidance, execution risks, and market opportunities.

##### C. **Financials – P&L, Balance Sheet, Cash Flow**
- Analyze revenue, margins, and PAT trends across 1Y/3Y/5Y periods.
- Highlight recurring vs. non-recurring items (e.g., exceptional gains/losses, impairments).
- Flag any significant YoY changes in major line items — especially under 'Other Expenses' (e.g., Warranty, Claims, CSR) — with a brief explanation if disclosed.
- Comment on:
  - Leverage (Debt/Equity, Interest Coverage)
  - Liquidity and working capital cycles
  - Free Cash Flow (FCF) generation and reinvestment capacity
  - Dividend payout, capex, debt repayments
- **Use Markdown tables** for multi-year comparisons of Revenue, EBITDA, PAT, margins, leverage, and FCF.

##### D. **Schedules in the Balance Sheet – Composition & Red Flags**
- Review supporting schedules to key Balance Sheet items, such as:
  - Fixed assets, other financial assets/liabilities, receivables, payables, provisions, and borrowings.
- Highlight any unusual movements or changes in composition YoY (e.g., steep rise in capital work-in-progress, provisions for doubtful debts, contingent liabilities).
- Note any asset/liability concentration risks or reclassifications.
- Summarize insights that help assess quality of earnings, working capital discipline, and hidden risks.

##### E. **Segment & Geographic Performance**
- Present segment-wise and/or region-wise financials: revenue, EBIT, margins.
- Highlight strong/weak segments and management commentary on each.
- **Use Markdown tables** for segmental/region-wise performance to show YoY comparison.

##### F. **Governance & Board Structure**
- Capture changes in Board or Key Managerial Personnel (KMP).
- Comment on independence, committee composition, and institutional engagement (if disclosed).
- Flag any potential governance risks.

##### G. **KMP Remuneration**
- Present and analyze top executive compensation:
  - Chairman, MD, CEO, CFO
- Provide YoY comparison and comment on performance alignment.
- **Use a Markdown table** to show executive compensation by year and role.
- Flag any pay structures that appear excessive or poorly aligned to shareholder outcomes.

##### H. **Related Party Transactions (RPTs)**
- Extract all material RPTs with counterparty names, transaction types, and magnitudes.
- Comment on frequency, trends, and any governance implications.
- Specifically highlight material increases in transaction values vs prior year and assess potential red flags or concentration risks.
- **Present RPTs in Markdown tables** (counterparty, nature of transaction, YoY value).

##### I. **Auditor's Report & Key Audit Matters (KAMs)**
- Identify audit firm, audit opinion, and any changes in auditor.
- Summarize all KAMs and emphasis of matter.
- Immediately flag qualified, adverse, or modified opinions.
- Highlight contingent liabilities, impairments, or litigations raised by the auditor.
- If a KAM has been consistently recurring with no change in scope or auditor concern, consider condensing it with reference to the relevant page number for optional review.

##### J. **Contingent Liabilities & Off-Balance Sheet Risks**
- Extract and comment on guarantees, legal proceedings, commitments, and other unrecognized risks.
- Comment on potential financial impact and how the company discloses or mitigates these.
- **Use Markdown tables** for contingent liabilities if multiple categories are disclosed.

##### K. **Financial Ratios & Emerging Risks**
- Present and interpret:
  - ROCE, ROE
  - Debt/Equity, Interest Coverage
  - Asset Turnover, Inventory/Receivables days
  - Operating Cash Flow vs PAT
- **Summarize ratios in a Markdown table** for clarity.
- Identify any **early warning signals**, such as:
  - Margin erosion
  - Working capital stress
  - OCF-PAT divergence
  - Excessive promoter compensation
  - Dependence on RPTs
  - Audit flags

---

### 🔷 PRESENTATION GUIDELINES

- **Tone:**
  - Maintain a formal, precise, and objective tone throughout.
  - Avoid emotional or promotional language.

- **Length:**
  - Be crisp yet comprehensive.
  - Prioritize clarity and decision-relevance over exhaustive detail.

- **Narrative Style:**
  - Use structured prose supported by **Markdown tables** wherever numbers or comparisons are disclosed.
  - Tables must be clean, minimal, and directly copy-pastable into Microsoft Word without formatting issues.
  - Use subheadings and logical flow to aid readability.

- **Strictly Avoid:**
  - Any assumptions, estimates, or external data not present in the annual report.
  - Benchmarking or peer comparisons unless explicitly disclosed.
  - Meta-commentary, drafting instructions, or placeholder notes.
  - Visual elements like charts, graphs, or formatting suggestions.
  - **Generic ESG commentary** unless materially flagged in the report or relevant to capital allocation/governance risk.


CRITICAL INSTRUCTION:

Avoid narrative, avoid storytelling, avoid verbosity.

Focus on:
- Maximum insight extraction
- High signal density
- Credit-relevant observations only

---

### 🔷 OUTPUT STYLE (MANDATORY):

- Bullet points ONLY (no paragraphs unless unavoidable)
- No verbosity, no narrative transitions, no storytelling
- Each bullet = one atomic idea
- Prefer short analytical fragments (not full sentences)

Each bullet must include at least one:
- Direction (rising / declining / stable / volatile)
- Cause (why)
- Implication (credit impact)

Examples:
❌ "The company has seen a decline in margins due to rising input costs."
✅ "Margins declining — input cost pressure, weak pass-through → earnings risk"

❌ "It is observed that receivables have increased."
✅ "Receivables rising faster than revenue → working capital stress"

Rules:
- No repetition
- No generic statements
- No filler language

---

EXPANSION RULE:

- Do NOT limit number of bullets
- Extract ALL possible credit signals
- Break complex ideas into multiple bullets

Example:
❌ "Margins declined due to costs"
✅
- Margins declining YoY
- Input costs rising faster than pricing
- Limited pass-through ability
- EBITDA volatility increasing → earnings predictability weak

---

DO NOT COMPRESS INSIGHTS:

- If multiple risks exist → list all
- If multiple drivers exist → split into bullets
- Prefer 50+ sharp bullets over summarized output

EXHAUSTIVENESS MANDATE (CRITICAL):

- Do NOT miss any credit-relevant insight
- Assume Investment Committee will rely ONLY on this output
- Missing a risk = analytical failure

---

### 🔷 OBJECTIVE

Deliver a distilled, audit-traceable, and investment-ready annual report analysis that empowers the CIO to:
- Understand the company's true financial and strategic posture
- Identify actionable trends or red flags
- Make capital allocation or risk-based decisions confidently — without needing to read the original 200-page report

This ARA is not a summary — it is a **precision-crafted institutional decision-support document**.
'''


@mcp.tool()
def analyze_annual_report(file_uri: str) -> str:
    """
    Run a full Annual Report Analysis (ARA) against a company's annual report PDF.
    Produces an institutional-grade markdown document covering financials, governance,
    related-party transactions, auditor remarks, management commentary, and more.
    file_uri: "uri" returned by upload_file_to_gemini.
    Returns full ARA markdown text.
    """
    if not file_uri:
        raise ValueError("file_uri cannot be empty.")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set.")

    client = genai.Client(api_key=api_key)
    pdf_file = get_gemini_file(client, file_uri)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[pdf_file, ARA_PROMPT]
    )
    return response.text
