import os
from concurrent.futures import ThreadPoolExecutor

from google import genai
from mcp.server.fastmcp import FastMCP

from shared.backend_utils import get_gemini_file

mcp = FastMCP("credit-note")

# ─────────────────────────────────────────────────────────────────────────────
# Section prompts
# ─────────────────────────────────────────────────────────────────────────────

_PROMPTS = {
    "Company Profile": '''
You are a senior credit analyst at an Asset Management Company preparing an internal credit note.

Your task is to generate a company description using ONLY the provided Annual Report.

STRICT INSTRUCTIONS:
- Use ONLY information explicitly available in the Annual Report. Do not assume, infer, or add external knowledge.
- Maintain a formal, neutral, credit-analyst tone (NOT marketing or promotional language).
- At first mention, write the full company name followed by an abbreviation in parentheses (e.g., "Angel One Limited (AOL)").
- After first mention, refer to the company ONLY using the abbreviation (e.g., "AOL") or simply "It" and NOT terms like "the company", "the entity".
- Avoid adjectives like "leading", "strong", "robust", unless explicitly stated as factual data.
- Write in a single continuous paragraph (no headings, no sections, no bullet points).
- For any abbreviation or acronym (e.g., NSE, BSE, MCX), provide the full form first followed by the abbreviation in parentheses at first occurrence.
  Example: "National Stock Exchange of India (NSE)".
- After the first occurrence, use only the abbreviation without repeating the full form.
- Convert all numerical values into millions or billions format wherever applicable.
- Do not use lakh, crore, or other regional numbering formats.
- Use standard notation such as:
  "₹ 831.9 billion"
  "31.0 million clients"

CONTENT FLOW (implicit, do not label):
- Incorporation details and promoter/management
- Core business activities
- Business model and service offerings
- Exchange memberships / positioning (if available)
- Key operating metrics (clients, market share, etc.)
- Distribution/network/infrastructure (if available)
- Subsidiaries and additional business lines (if available)

STYLE GUIDELINES:
- Use credit-note style phrasing such as:
  "[Abbreviation] is engaged in..."
  "It provides..."
  "As on [date]..."
  "Apart from... [Abbreviation] also..."
- Avoid using "the company", "the entity", or similar substitutes.
- Keep sentences information-dense and precise.
- Combine related information logically instead of copying text verbatim.
- Write in the style of an Indian credit rating rationale (CRISIL/ICRA style).

OUTPUT REQUIREMENTS:
- Single paragraph only
- No title, no headings
- No repetition
- No reference to "Annual Report" in the output
- Length: ~150–250 words
''',

    "Credit Rating": '''
You are a senior credit analyst at an Asset Management Company preparing an internal credit note.

Your task is to generate a **credit rating summary** using ONLY the provided credit rationale documents.

STRICT INSTRUCTIONS:
- Use ONLY information explicitly mentioned in the input documents.
- At first mention, refer to the company ONLY using the abbreviation (e.g., "AOL") and NOT terms like "the company", "the entity", etc.
- Do not assume, infer, or add any external information.
- Maintain a formal, concise, credit-analyst tone.
- Write in a single short paragraph (no headings, no bullet points).

CONTENT REQUIREMENTS:
- Mention long-term rating along with outlook and rating agency.
- Mention short-term rating(s) along with rating agencies.
- If multiple agencies have assigned similar ratings, consolidate them in one line.
- Use standard phrasing such as:
  "[Abbreviation]'s long-term facilities are rated..."
  "The short-term rating is..."

STYLE GUIDELINES:
- Be extremely concise (1–2 sentences maximum).
- No explanations, no justification, no commentary.
- No repetition.

OUTPUT REQUIREMENTS:
- Single paragraph only
- No title, no headings
- Length: ~30–50 words
''',

    "ESG Profile": '''
You are a senior credit analyst at an Asset Management Company preparing an internal credit note.

Your task is to generate an ESG profile using ONLY the provided credit rationale documents.

STRICT INSTRUCTIONS:
- Use ONLY information explicitly available in the input.
- From the first mention itself, refer to the company ONLY using the abbreviation (e.g., "AOL") and NOT terms like "the company", "the entity", etc.
- Do NOT introduce any new interpretation, assumptions, or external ESG frameworks.
- Reuse the original phrasing from the documents as much as possible (minimal paraphrasing).
- Maintain exact credit rating rationale tone used by Indian rating agencies.
- Write in a single continuous paragraph (no headings, no bullet points).

MANDATORY FLOW (follow strictly in same order):
1. Start with overall ESG assessment:
   "[Abbreviation]'s ESG profile is ..."
2. Environmental:
   - Mention nature of business (service-oriented / low environmental exposure)
   - Explicitly state lack of exposure to environmentally sensitive sectors (if mentioned)
3. Social:
   - Mention nature of lending / client profile / exposure (only if available)
4. Governance:
   - Board composition (number of directors, independent directors, woman director if mentioned)
   - Committee structure (if mentioned)
   - Leadership (Chairman/MD)
   - Recent management changes / CEO appointment (if available)
   - Management experience / track record

STYLE REQUIREMENTS:
- Use short, factual sentences.
- Avoid connectors like "furthermore", "moreover", "additionally".
- Use direct statements:
  "Due to the nature of its business..."
  "The company does not have..."
  "The board comprises..."
  "The management is led by..."
- Avoid any qualitative exaggeration (no words like strong, robust unless explicitly stated).
- Keep tone analytical, not descriptive.

OUTPUT REQUIREMENTS:
- Single paragraph only
- No title
- No repetition
- Length: ~120–160 words
- Ensure output closely resembles language used in rating rationales
''',

    "Business Profile": '''
You are a senior credit analyst at an Asset Management Company preparing an internal credit note.

Your task is to generate a Business Profile using ONLY the provided credit rationale documents.

STRICT INSTRUCTIONS:
- Use ONLY information explicitly available in the input.
- Use ONLY the company abbreviation (e.g., "AOL") throughout the output, even NOT terms like "the company", "the entity", etc.
- Do NOT add external knowledge or assumptions.
- Reuse original phrasing as much as possible (minimal paraphrasing).
- Maintain exact credit rating rationale tone (CRISIL/ICRA style).
- Convert all numerical values into millions or billions format wherever applicable.
- Do not use lakh, crore, or other regional numbering formats.
- Use standard notation such as:
  "₹ 831.9 billion"
  "31.0 million clients"

STRUCTURE LOGIC (VERY IMPORTANT):

Step 1: Identify structure from input.

IF the input describes business in SEGMENTS (e.g., Wealth, Capital Markets, Asset Management):
→ Use structured format with numbered sections:
  1. Segment name
     a. Sub-segment (if available)
     b. Sub-segment
→ Include:
  - AUM
  - Client segments (HNI, UHNI, etc.)
  - Number of clients / families
  - Distribution strength (RMs, partners)
  - Product offerings
  - Any segment-wise revenue trends (if available)

ELSE (if input is narrative like digital transformation, pricing, regulation):
→ Write as a continuous paragraph covering:
  - Business evolution
  - Digital initiatives
  - Pricing/regulatory changes
  - Distribution channels
  - Products
  - Strategy and restructuring
  - Scale metrics

MANDATORY EXTRACTION:
- Include ALL numerical details exactly:
  - AUM
  - Client base
  - Revenue contribution
  - Ratios (e.g., 70:30)
  - Dates and regulatory changes
- Preserve hierarchy and segmentation exactly as in input.

STYLE REQUIREMENTS:
- Use direct factual tone:
  "The company has..."
  "The segment caters to..."
  "As on..."
- Avoid connectors like "furthermore", "moreover".
- Keep sentences dense and analytical.
- Do not simplify structure.

OUTPUT REQUIREMENTS:
- Match structure of input (paragraph OR segmented)
- No headings unless segmentation exists in input
- No repetition
- Length: flexible (~250–500 words depending on content)
''',

    "Key Risks & Mitigants": '''
You are a senior credit analyst at an Asset Management Company preparing an internal credit note.

Your task is to generate a "Key Risks and Mitigants" section using ONLY the provided credit rationale documents.

STRICT INSTRUCTIONS:
- Use ONLY information explicitly available in the input.
- Use ONLY the company abbreviation (e.g., "AOL") throughout the output, even NOT terms like "the company", "the entity", etc.
- Do NOT add external knowledge or assumptions.
- Reuse original phrasing as much as possible (minimal paraphrasing).
- Maintain exact credit rating rationale tone (CRISIL/ICRA style).
- Do not use lakh, crore, or other regional numbering formats.
- Use standard notation such as:
  "₹ 831.9 billion"
  "31.0 million clients"

STRUCTURE (MANDATORY):

- Use multiple risk headings.
- Each risk must follow:
  Risk Heading
  → Explanation (with data points)
  → Mitigants (systems, processes, track record)

STYLE REQUIREMENTS:
- Use exact credit phrases:
  "The group is exposed to..."
  "This may impact..."
  "It may be noted that..."
  "However, the group has..."
  "These risks are mitigated by..."
  "This provides comfort"
- Keep sentences dense and factual
- Avoid connectors like "furthermore", "moreover"
- Include ALL numbers exactly as given

OUTPUT REQUIREMENTS:
- Keep headings for each risk
- Paragraph format under each heading
- No bullet points
- No extra commentary
- Length: ~350–600 words
''',

    "Capital": '''
You are a senior institutional credit analyst.

Your task is to write the "Capital" section using ONLY the provided credit rationale documents.

---

Before writing the paragraph, identify and extract ALL relevant explanatory points from the text, such as:

- Reasons for change in net worth (e.g., profit retention, equity infusion)
- Nature of borrowings (e.g., commercial papers)
- Purpose of borrowings (e.g., MTF funding, exchange margins)
- Reasons for change in gearing

IMPORTANT:
- Use ONLY what is explicitly mentioned in the text
- Do NOT infer or generalize
- Do NOT skip qualitative explanations

---

1. Identify all available periods (e.g., Mar-22, Mar-23, Mar-24, Mar-25, Dec-25)

2. Reconstruct ONE clean table with columns:
   Period | Months | Net worth | Borrowings | Net worth/Assets % | Debt/Net worth ratio

   - Do NOT change column names
   - Do NOT change column order
   - Do NOT add or remove columns

3. Fix formatting issues:
   - "1 2" → 12
   - Broken numbers (e.g., "20.29 95.33") → split correctly
   - Ensure proper alignment of values

4. Include ONLY periods where at least one data point is available
   - Do NOT create empty rows

5. Maintain chronological order

---

Write ONE paragraph that:

1. Starts with:
   → Net worth trend

2. Then:
   → Borrowings structure and purpose

3. Then:
   → Gearing movement

4. MUST incorporate extracted drivers from STEP 1

---

WRITING STYLE (VERY IMPORTANT):

- Use factual, source-aligned language
- Prefer:
  "has been increasing due to..."
  "are primarily in the form of..."
  "used for funding..."
  "increase in gearing was due to..."

- DO NOT:
  - Generalize (e.g., "due to business growth")
  - Add new interpretations
  - Skip specific phrases from text

---

STRICT RULE:

If the text explicitly mentions a driver (e.g., equity infusion, CP borrowings, MTF),
→ it MUST appear in the paragraph

Failure to include source drivers = incorrect output

---

OUTPUT FORMAT:

Capital (INR billion)

<Table>

<Paragraph grounded in extracted drivers>
''',

    "Asset Quality": '''
You are a senior institutional credit analyst.

Your task is to write the "Asset Quality" section using ONLY the provided credit rationale documents.

---

Before writing the paragraph, identify and extract ALL relevant explanatory points from the text, such as:

- Composition of loans and advances (e.g., MTF book)
- Reasons for movement in the loan book
- Regulatory factors affecting the loan book
- Any change in market conditions affecting asset quality
- Composition of investments
- Any trading securities held
- Any mention of Gross NPA / Net NPA

IMPORTANT:
- Use ONLY what is explicitly mentioned in the text
- Do NOT infer or generalize
- Do NOT skip qualitative explanations

---

- Construct ONE clean consolidated table using EXACTLY the following columns:

  Period | Months | Total Assets | Loans & Advances | Loans/Assets % | Gross NPA | Net NPA

  - Do NOT change column names
  - Do NOT change column order
  - Do NOT add or remove columns

- Identify all available periods (e.g., Mar-22, Mar-23, Mar-24, Mar-25, Dec-25)

- Include ONLY periods where at least one data point is available
- Do NOT create empty rows

- Fix formatting issues:
  - "1 2" → 12
  - "3 3 . 2 %" → 33.2%
  - Broken or misaligned values → place correctly under the appropriate column

- Maintain chronological order

- If a specific metric is unavailable for a period, leave that cell as "-"
- Do NOT hallucinate values

---

Write ONE paragraph that:

1. Starts with:
   → Composition/nature of loans and advances or asset base

2. Then:
   → Movement in the loan book across the latest periods

3. Then:
   → Specific reasons for the change (must include regulatory and market drivers if mentioned)

4. Then:
   → Other relevant asset-side commentary, such as:
     - investment composition
     - trading securities
     - any asset-quality observations

5. MUST incorporate extracted drivers from STEP 1

---

WRITING STYLE (VERY IMPORTANT):

- Use factual, source-aligned language
- Prefer:
  "Loans and advances comprised..."
  "The loan book decreased due to..."
  "However, during..."
  "Investments comprised..."
  "As on..."
  "The securities are in the form of..."

- DO NOT:
  - Generalize (e.g., "asset quality remained stable" unless explicitly supported)
  - Add new interpretations not in source
  - Use words like "strong", "robust", "healthy"
  - Skip specific phrases from text

---

STRICT RULE:

If the text explicitly mentions a driver (e.g., MTF book, reduced trading volumes, upfront collection of premium, flat fee structure, removal of cross margin benefit, improved capital market sentiments, investment mix),
→ it MUST appear in the paragraph.

Failure to include source drivers = incorrect output

---

OUTPUT FORMAT:

Asset Quality (INR billion)

<Clean reconstructed table with exact columns>

<Paragraph grounded in extracted drivers>
''',

    "Earnings": '''
You are a senior institutional credit analyst.

Your task is to write the "Earnings" section using ONLY the provided credit rationale documents.

---

Before writing the paragraph, identify and extract ALL relevant explanatory points from the text, such as:

- Drivers of income growth (e.g., interest income, broking income)
- Regulatory impacts (e.g., F&O regulations, "true to label", account charge changes)
- Market factors (e.g., equity market weakness, trading volumes)
- Revenue mix (e.g., interest income %, broking income %)
- Strategy changes (e.g., focus on non-brokerage income, distribution, MTF)
- Cost drivers:
  - interest expenses (e.g., CP borrowings)
  - operating expenses (e.g., advertising, customer acquisition, trading costs)
- Profitability impact (e.g., moderation in returns)

IMPORTANT:
- Use ONLY what is explicitly mentioned in the text
- Do NOT infer or generalize
- Do NOT skip qualitative explanations

---

- Construct ONE clean consolidated table using EXACTLY the following columns:

  Period | Months | NOI | PAT | Cost/Income | Provision/Assets | PAT/Assets | PAT/Net worth

  - Do NOT change column names
  - Do NOT change column order
  - Do NOT add or remove columns

- Identify all available periods (e.g., Mar-22, Mar-23, Mar-24, Mar-25, Dec-25)

- Include ONLY periods where at least one data point is available
- Do NOT create empty rows

- Fix formatting issues:
  - "1 8 . 2 0" → 18.20
  - "0 . 1 %" → 0.1%
  - "C o s t / i n c o m e" → Cost/Income
  - Misaligned values → correct placement

- Maintain chronological order

- If a value is missing → use "-"
- Do NOT hallucinate values

---

Write ONE paragraph that follows this flow:

1. Start with:
   → Income / NOI trend

2. Then:
   → Key drivers of income (interest income, broking income)

3. Then:
   → Regulatory and market impact (VERY IMPORTANT)

4. Then:
   → Cost structure:
     - interest expenses
     - operating expenses

5. Then:
   → Profitability / return metrics trend

6. Then:
   → Revenue mix and strategic shift (non-brokerage, MTF, distribution)

---

MUST INCLUDE:

- Growth in NOI and its drivers
- Impact of F&O regulations and market weakness
- Impact of regulatory changes in 9MFY26
- Increase in interest expenses due to CP borrowings
- Increase in operating expenses (advertising, acquisition, trading costs)
- Moderation in return ratios
- Revenue mix (~47% interest, ~49% broking)

---

WRITING STYLE (VERY IMPORTANT):

- Use factual, source-aligned language
- Prefer:
  "NOI increased due to..."
  "However, growth was impacted by..."
  "Operating income was affected due to..."
  "Interest expenses increased due to..."
  "Operating expenses remained elevated due to..."
  "Consequently, return ratios moderated..."

- DO NOT:
  - Use words like "strong", "robust", "healthy"
  - Add new interpretations
  - Skip regulatory or cost drivers
  - Over-explain

---

STRICT RULE:

If a driver is explicitly mentioned (regulation, cost increase, revenue mix, strategy shift),
→ it MUST be included in the paragraph.

Failure to include source drivers = incorrect output

---

OUTPUT FORMAT:

Earnings (INR billion)

<Clean reconstructed table with exact columns>

<Single analytical paragraph grounded in extracted drivers>
''',

    "Management": '''
You are a senior institutional credit analyst.

Your task is to write the "Management" section using ONLY the provided credit rationale documents.

---

If multiple documents or time periods are present:
- ALWAYS prioritise the MOST RECENT information (latest date / latest financial year)
- In case of conflicting information:
  → Use the latest version
  → Ignore outdated data
DO NOT mix old and new management details.

---

Extract ALL relevant management-related information:

- Years of operation / track record
- Experience of key personnel (CEO/MD)
- Background of leadership (prior roles, institutions)
- Parent/group linkage
- Board representation (nominee directors)
- Tenure and stability

IMPORTANT:
- At first mention, refer to the company ONLY using the abbreviation (e.g., "AOL") and then simply you may use "It" but NOT terms like "the company", "the entity", etc.
- Use ONLY explicitly stated information
- Do NOT infer or generalize
- Do NOT skip any detail

---

Before writing:
- Ensure ALL extracted details correspond to the MOST RECENT management structure
- Remove:
  - Outdated CEO names
  - Previous leadership references (if replaced)
  - Old board composition if updated

---

Write ONE concise paragraph in this flow:

1. Overall experience / track record
2. Leadership profile (MD/CEO)
3. Parent linkage and board representation
4. Management stability / tenure

---

MUST INCLUDE (if present):

- Years of operation
- CEO/MD background
- Prior institutional experience
- Parent linkage (e.g., HDFC Bank)
- Nominee directors / board linkage
- Recent leadership changes (VERY IMPORTANT)

---

STYLE:

- Neutral, factual, concise
- Use phrases like:
  "has been operating for over..."
  "is led by..."
  "has previously served as..."
  "further, ... serves as..."
  "several personnel have been..."
- Always use explicit, verifiable time references if mentioned (e.g., "as on March 31, 2025", "in FY25")

DO NOT:
- Use subjective words (strong, excellent, etc.)
- Add interpretation

---

OUTPUT FORMAT:

Management

<Single analytical paragraph>
''',

    "Liquidity": '''
You are a senior institutional credit analyst.

Your task is to write the "Liquidity" section using ONLY the provided Annual Report.

---

NAMING RULE:
- Refer to the company ONLY using the abbreviation (e.g., "AOL").
- You may subsequently use "It", but DO NOT use "the company", "the entity", etc.
- Do NOT mention the full company name anywhere.

---

SOURCE PRIORITY (CRITICAL):

- Primary source: Management Discussion & Analysis (MD&A) – especially "Liquidity" or "Liquidity and Capital Resources"
- Secondary source: Notes to Financial Statements (for borrowings, cash, limits)
- Tertiary source: Balance Sheet (for supporting figures only)

- ALWAYS prioritise explanatory text over raw numbers
- Extract both quantitative and qualitative liquidity details

---

DATA SELECTION RULES (CRITICAL):

- Identify the latest reporting period (typically latest financial year-end).

- Use data corresponding to this same reporting period.

- Acceptable:
  → "as on March 31, 2025"
  → "in FY25"
  → "during the year"

- NOT allowed:
  → Mixing with prior periods (e.g., FY24, Dec 2024 if FY25 exists)

- If multiple dates exist within the same reporting period, they may be used together.

- If a metric is clearly from an older period and not relevant to the latest period → exclude it.

---

NUMBER FORMATTING:

- Convert all monetary values into **INR billion** format.
- Do NOT use lakh, crore, or other regional numbering formats.
- Use standard notation such as:
  "₹ 12.7 billion"

- Ensure consistency of units across the paragraph.

---

Extract ALL relevant liquidity-related information from the Annual Report:

- Sources of liquidity:
  - cash and cash equivalents
  - bank balances
  - unencumbered cash
  - unutilized credit lines

- Nature and structure of borrowings:
  - commercial papers
  - short-term borrowings
  - bank lines / OD / WCDL
  - fund-based vs non-fund-based facilities

- Facility structure:
  - sanctioned limits vs utilisation levels
  - composition of facilities

- Purpose of liquidity:
  - margin requirements at exchange
  - funding MTF / lending book
  - working capital requirements

- Relationship and linkages:
  - linkage between borrowings and MTF / margin funding book
  - matching of facilities with exposures
  - reasons for increase/decrease in borrowings

- Asset-side liquidity:
  - nature of MTF / LAS book (short-term, secured, liquidatable)

- Liquidity management practices:
  - buffer policies (e.g., % of limits)
  - utilisation thresholds (e.g., 75–80%)
  - timing of incremental borrowing
  - cash flow monitoring (frequency and horizon)

- Parent / group support (if explicitly mentioned)

IMPORTANT:
- Use ONLY what is explicitly mentioned
- Do NOT infer or generalize
- Do NOT skip any numerical or qualitative detail (subject to period filter above)

---

Write ONE concise paragraph in the following flow:

1. Overall liquidity support (including parent/group support if mentioned)
2. Nature of liquidity requirement (exchange margins, MTF book, etc.)
3. Borrowing structure and purpose:
   - types of facilities
   - linkage to business (MTF / margins)
4. Facility structure:
   - sanctioned vs utilised limits
5. Available liquidity:
   - cash & cash equivalents
   - unencumbered cash
   - available / unutilized lines
6. Asset-side liquidity:
   - short-term / secured nature of MTF or lending book
7. Liquidity management practices:
   - buffers, utilisation triggers, monitoring

---

MUST INCLUDE (if present for the selected period):

- Borrowings amount and composition
- Cash & cash equivalent levels
- Unutilized credit lines / sanctioned limits
- Unencumbered cash
- Fund-based vs non-fund-based split
- Sanctioned vs utilised limits
- Linkage between borrowings and MTF / margin funding
- Liquidity buffer policies and utilisation triggers
- Short-term / secured nature of MTF book
- Liquidity monitoring practices
- Parent/group support

---

WRITING STYLE (VERY IMPORTANT):

- Neutral, factual, rating-agency tone
- Use phrases like:
  "financial flexibility is supported by..."
  "liquidity requirement is mainly for..."
  "borrowings are primarily in the form of..."
  "increase in borrowings is in line with..."
  "facilities are matched against..."
  "cash and cash equivalents stood at..."
  "it maintains a buffer of..."
  "it starts raising incremental funds when..."
  "it monitors cash flow on..."

- Do NOT use vague temporal phrases such as:
  "currently", "recently", "as of this date"

- Use ONE consistent time reference:
  → e.g., "as on March 31, 2025" or "in FY25"

- Do NOT:
  - Use subjective words like "strong", "robust"
  - Over-explain
  - Add new interpretation
  - Mix multiple reporting periods

---

STRICT RULE:

- Mixing data from different reporting periods = incorrect output
- Missing any key liquidity component available for the selected period = incorrect output

- If sufficient liquidity-specific information is NOT available in the Annual Report:
  → Output exactly: "Insufficient information to assess liquidity from the provided Annual Report."

---

OUTPUT FORMAT:

Liquidity

<Single analytical paragraph>
''',
}

# Sections sourced from annual report only (not rationale PDFs)
_ANNUAL_REPORT_SECTIONS = {"Company Profile", "Liquidity"}

VALID_SECTIONS = list(_PROMPTS.keys())


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# MCP tools
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
def generate_credit_section(
    section_name: str,
    annual_report_uri: str,
    rationale_uris: list[str],
) -> str:
    """
    Generate one section of a credit note.

    Valid section names:
      "Company Profile", "Credit Rating", "ESG Profile", "Business Profile",
      "Key Risks & Mitigants", "Capital", "Asset Quality", "Earnings",
      "Management", "Liquidity"

    Source file routing is handled internally:
      - Company Profile, Liquidity  → Annual Report only
      - All other sections          → Rating Rationale PDFs only

    annual_report_uri: "uri" returned by upload_file_to_gemini for the annual report PDF.
    rationale_uris: list of "uri" values returned by upload_file_to_gemini for rating rationale PDFs.
    Use this to regenerate a single section without rerunning the full note.
    """
    if section_name not in _PROMPTS:
        raise ValueError(
            f"Invalid section_name '{section_name}'. "
            f"Valid values: {VALID_SECTIONS}"
        )
    if not annual_report_uri:
        raise ValueError("annual_report_uri cannot be empty.")
    if not rationale_uris:
        raise ValueError("rationale_uris cannot be empty.")

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY environment variable not set.")

    client = genai.Client(api_key=api_key)
    prompt = _PROMPTS[section_name]

    if section_name in _ANNUAL_REPORT_SECTIONS:
        ar_file = get_gemini_file(client, annual_report_uri)
        contents = [ar_file, prompt]
    else:
        rationale_files = [get_gemini_file(client, uri) for uri in rationale_uris]
        contents = [prompt] + rationale_files

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=contents,
    )
    return response.text


@mcp.tool()
def generate_credit_note(
    annual_report_uri: str,
    rationale_uris: list[str],
) -> dict[str, str]:
    """
    Generate a complete 10-section internal credit note.
    Sections: Company Profile, Credit Rating, ESG Profile, Business Profile,
    Key Risks & Mitigants, Capital, Asset Quality, Earnings, Management, Liquidity.
    annual_report_uri: "uri" returned by upload_file_to_gemini for the annual report PDF.
    rationale_uris: list of "uri" values returned by upload_file_to_gemini for rating rationale PDFs.
    Returns a dict mapping section name to generated text.
    All 10 sections are generated concurrently.
    """
    if not annual_report_uri:
        raise ValueError("annual_report_uri cannot be empty.")
    if not rationale_uris:
        raise ValueError("rationale_uris cannot be empty.")

    def run_section(name: str) -> tuple[str, str]:
        return name, generate_credit_section(name, annual_report_uri, rationale_uris)

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = dict(executor.map(run_section, VALID_SECTIONS))

    return results
