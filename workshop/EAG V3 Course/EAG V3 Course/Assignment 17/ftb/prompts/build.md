Build the financial calculator specified below as one file, index.html, in the workspace.

How to work:
1. {start_step}
2. Run the check: `node checks/check_tool.js index.html`
3. If it exits non-zero, read what it reported, fix index.html, and run it again.
   Repeat until it exits 0. Do not give your final answer while it is failing.
4. Then answer with a short summary of what the tool does and the check result.

Contract for index.html:
- One self-contained file. No external scripts, styles, fonts or images. No network calls.
- All arithmetic lives in exactly one block: <script id="calc"> defining
  function calculate(input) that returns a plain object. That block must not
  touch document, window or storage. A second <script> reads the form, calls
  calculate, and shows the result.
- `input` has exactly the input keys in the specification; the returned object
  has exactly the output keys. Table inputs and outputs are arrays of row objects.
- A labelled form field for every input, pre-filled with sensible example
  values, and results visible as soon as the page opens and on every change.
- Money shown to 2 decimal places. Clear labels. Readable on a phone.
- Implement every rule in the specification. Never drop a rule to make the check pass.

You cannot edit checks/ or SPEC.md: they are the agreed judge. If the check
seems wrong, say so in your answer instead of working around it.
{change_note}
=== SPECIFICATION (also saved as SPEC.md) ===
{spec}
