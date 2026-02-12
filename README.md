# OpenAI Pricing Scraper

Automated scraper that extracts pricing data for every model on OpenAI's developer docs. Uses **Claude Code** as an AI agent subprocess, which drives **playwright-cli** (headless by default) to browse, discover models, and extract pricing into structured JSON.

## How It Works

```
scrape_openai_pricing.py
  │
  ├─ Spawns claude.cmd as a subprocess
  │    └─ Claude Code uses playwright-cli (headless by default) to:
  │         1. Open the OpenAI models index page
  │         2. Discover all listed models
  │         3. Navigate to pricing page and individual model pages
  │         4. Extract pricing for each model
  │         5. Save progress incrementally to openai_pricing_progress.json
  │
  ├─ On success → extracts structured_output from Claude's JSON response
  ├─ On timeout → falls back to the progress file for partial results
  └─ Saves final output to output/openai_pricing_<timestamp>.json
```

## Prerequisites

### 1. Python 3.10+

Verify:
```bash
python --version
```

### 2. Node.js and npm

Required for Claude Code and playwright-cli. Verify:
```bash
node --version
npm --version
```

### 3. Claude Code CLI

Install Claude Code globally:
```bash
npm install -g @anthropic-ai/claude-code
```

Verify (on Windows the CLI is `claude.cmd`):
```bash
claude --version
```

You must be authenticated with an Anthropic API key or Claude account. See [Claude Code docs](https://docs.anthropic.com/en/docs/claude-code) for setup.

### 4. Playwright CLI

Install the `@playwright/cli` package globally:
```bash
npm install -g @playwright/cli@latest
```

Verify it's on your PATH:
```bash
playwright-cli --help
```

You should see a list of commands (`open`, `snapshot`, `screenshot`, `click`, `goto`, `close`, etc.).

### 5. Initialize workspace and install browser

Run `playwright-cli install` from the project directory. This initializes the workspace and detects an available browser (Chrome/Chromium):
```bash
playwright-cli install
```

Expected output:
```
✅ Workspace initialized at `<your-project-path>`.
✅ Found chrome, will use it as the default browser.
```

If Chrome is not found, install Chromium explicitly:
```bash
npx playwright install chromium
```

### 6. Verify end-to-end

Run these three commands in sequence to confirm playwright-cli can open a page, read its content, and close cleanly:
```bash
playwright-cli open https://example.com
playwright-cli snapshot
playwright-cli close
```

Expected behavior:
- `open` prints browser info with `headed: false` (headless by default) and a page snapshot
- `snapshot` prints the page URL, title, and a snapshot file path
- `close` prints `Browser 'default' closed`

**Note:** Do NOT pass `--headless` — it is not a valid flag. playwright-cli runs headless by default.

## Project Structure

```
playwright-test/
├── README.md                          # This file
├── .gitignore                         # Python gitignore
├── scrape_openai_pricing.py           # Main scraping script
├── claude_structured_client.py        # Reusable client for Claude Code structured output
├── test_claude_structured_output.py   # Basic test of Claude Code JSON schema compliance
├── notes/
│   └── notes.txt                      # Original project requirements
├── openai_pricing_progress.json       # Incremental progress (created at runtime)
└── output/
    └── openai_pricing_<timestamp>.json  # Final results (created at runtime)
```

## Usage

### Run the scraper

```bash
python scrape_openai_pricing.py
```

The script will:
1. Remove any old progress file
2. Launch Claude Code as a subprocess with a 30-minute timeout
3. Claude Code browses OpenAI's docs in headless mode, extracting pricing per model
4. Print a summary with model count and per-model pricing breakdown
5. Save the final JSON to `output/openai_pricing_<timestamp>.json`

### Monitor progress during a run

While the script is running, you can check incremental progress:
```bash
type openai_pricing_progress.json
```
(or `cat` on Linux/macOS)

### Run the structured output test

A simpler test to verify Claude Code CLI is working:
```bash
python test_claude_structured_output.py
```

### Use the structured client directly

```python
from claude_structured_client import ClaudeStructuredClient

client = ClaudeStructuredClient(model="sonnet", timeout=120)

schema = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"}
    },
    "required": ["answer"]
}

result = client.query("What is 2+2?", schema)
print(result)  # {"answer": "4"}
```

## Output Format

The scraper produces JSON with this structure:

```json
{
  "models": [
    {
      "model_name": "gpt-4o",
      "region": "global",
      "pricing": [
        { "unit_type": "Input", "price": "$2.50 / 1M tokens" },
        { "unit_type": "Cached Input", "price": "$1.25 / 1M tokens" },
        { "unit_type": "Output", "price": "$10.00 / 1M tokens" }
      ]
    },
    {
      "model_name": "dall-e-3",
      "region": "global",
      "pricing": [
        { "unit_type": "Standard 1024x1024", "price": "$0.040 / image" },
        { "unit_type": "HD 1024x1024", "price": "$0.080 / image" }
      ]
    }
  ]
}
```

Fields:
- **model_name**: Model identifier as listed on OpenAI's docs
- **region**: Always `"global"` for OpenAI (kept for future multi-provider use)
- **pricing**: Array of pricing dimensions, each with:
  - **unit_type**: Free-form string describing the pricing dimension (Input, Output, Cached Input, Per Image, Per Minute, Fine-tuning Training Input, etc.)
  - **price**: Price as displayed on the website, preserving original units (e.g. `"$2.50 / 1M tokens"`, `"$0.040 / image"`)

## Configuration

Key parameters in `scrape_openai_pricing.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--model` | `sonnet` | Claude model used for the scraping agent |
| `--dangerously-skip-permissions` | enabled | Required for unattended subprocess (no human to approve tool calls) |
| Timeout | 1800s (30 min) | Maximum time for the Claude Code subprocess |
| Progress file | `openai_pricing_progress.json` | Incremental save location |
| Output dir | `output/` | Where final timestamped JSON is saved |

## Troubleshooting

### `claude.cmd` not found
Claude Code CLI isn't installed or not on PATH. Run:
```bash
npm install -g @anthropic-ai/claude-code
```

### `playwright-cli` not found
The `@playwright/cli` package isn't installed globally. Run:
```bash
npm install -g @playwright/cli@latest
```
The scraping prompt also tells Claude Code to try `npx @playwright/cli` as a fallback.

### `--headless` error
Do not pass `--headless` to `playwright-cli open`. The CLI runs headless by default. This is already handled in the script's prompt.

### Timeout with partial results
If the 30-minute timeout is hit, the script falls back to `openai_pricing_progress.json` for whatever models were scraped before the timeout. Check the progress file and re-run if needed.

### No pricing data obtained
- Verify your Anthropic API key / Claude authentication is set up
- Verify playwright-cli works:
  ```bash
  playwright-cli open https://example.com
  playwright-cli snapshot
  playwright-cli close
  ```
- Check that the OpenAI docs URLs haven't changed
