"""
OpenAI Pricing Scraper via Claude Code + playwright-cli

Launches Claude Code as a subprocess, which uses playwright-cli in headless mode
to browse OpenAI's developer docs, scrape all model pricing data from individual
model pages, save progress incrementally, and return structured JSON output.
"""

import subprocess
import json
import os
import sys
import time
import threading
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

OPENAI_PRICING_SCHEMA = {
    "type": "object",
    "properties": {
        "models": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "model_name": {
                        "type": "string",
                        "description": "Model identifier, e.g. gpt-4o, dall-e-3, whisper-1"
                    },
                    "region": {
                        "type": "string",
                        "description": "Pricing region. 'global' unless region-specific pricing found."
                    },
                    "pricing": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "unit_type": {
                                    "type": "string",
                                    "description": "Pricing dimension: Input, Output, Cached Input, Per Image, Per Minute, etc."
                                },
                                "price": {
                                    "type": "string",
                                    "description": "Raw per-unit price as a decimal string, e.g. '0.0000025' for $2.50/1M tokens. For per-image or per-minute prices, the raw single-unit cost, e.g. '0.040' for $0.040/image. Use string type to preserve decimal precision."
                                }
                            },
                            "required": ["unit_type", "price"]
                        }
                    }
                },
                "required": ["model_name", "region", "pricing"]
            }
        }
    },
    "required": ["models"]
}

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

PROGRESS_FILE = "openai_pricing_progress.json"

SCRAPE_PROMPT_TEMPLATE = r"""
You are a web scraper. Use playwright-cli via the Bash tool to scrape OpenAI model pricing
by visiting EACH model's individual detail page. Always use --headed mode so the browser is
visible (this avoids Cloudflare bot detection that blocks headless browsers).

## Important Rules
- `playwright-cli open --headed <url>` opens a headed browser. Always use --headed.
- `playwright-cli goto <url>` navigates the already-open browser to a new URL.
- `playwright-cli snapshot` returns the page accessibility tree — use this to read page text.
- `playwright-cli screenshot` captures a screenshot (prints the output path).
- `playwright-cli click <ref>` clicks an element by its snapshot ref.
- `playwright-cli close` closes the browser session.
- Save incremental progress after each model to: """ + PROGRESS_FILE + r"""
- CRITICAL: Do NOT navigate to /api/docs/pricing or any pricing overview page.
  ALL pricing data must come from individual model detail pages.

## Steps

### Step 1: Open the models index page
```
playwright-cli open --headed "https://developers.openai.com/api/docs/models"
```
```
playwright-cli snapshot
```

### Step 2: Handle cookie/consent banners
If you see any cookie consent or dismissable banners, click to accept/dismiss them.

### Step 3: Collect all model links
From the snapshot, collect ALL links matching the pattern `/api/docs/models/<model-name>`.
The page lists models in multiple sections (Featured, Frontier, Specialized, etc.) — the
same model may appear more than once. Deduplicate by URL to build a list of unique model
page URLs to visit.

### Step 4: Visit each model page one by one
For EACH unique model URL from Step 3, perform ALL of the following sub-steps in order.
Do not skip any sub-step. Do not batch multiple models together.

  a. **Navigate** to the model's detail page:
     `playwright-cli goto "https://developers.openai.com<model-url>"`

  b. **Snapshot** the page:
     `playwright-cli snapshot`

  c. **Extract pricing** from the model's page. Look for:
     - Input token pricing
     - Output token pricing
     - Cached input pricing (if available)
     - Per-image pricing (for image models)
     - Per-minute pricing (for audio models)
     - Per-character pricing (for TTS)
     - Any other pricing dimensions shown
     If the page shows no pricing, record the model with an empty pricing array.

  d. **Screenshot** the model page — you MUST do this for every model:
     `playwright-cli screenshot`

  e. **Copy the screenshot** to the run output folder. The screenshot command prints the
     file path (e.g. `.playwright-cli\page-<timestamp>.png`). Copy it:
     `copy "<source_path>" "{RUN_FOLDER}\<model_name>.png"`
     Use a filesystem-safe model name (replace / with _). Delete the source file after copying.

  f. **Save progress** — write the accumulated results so far to the progress file as JSON:
     ```json
     {
       "models": [...all models scraped so far...],
       "last_updated": "<timestamp>",
       "status": "in_progress"
     }
     ```

### Step 5: Close browser when done
```
playwright-cli close
```
Set the progress file status to "completed".

## Output Requirements
- Set region to "global" for all OpenAI models (OpenAI uses uniform global pricing)
- Convert displayed prices to raw per-unit decimal strings:
  - "$X / 1M tokens" -> divide X by 1,000,000 (e.g. "$2.50 / 1M tokens" -> "0.0000025")
  - "$X / 1M characters" -> divide X by 1,000,000
  - "$X / image" -> use X as-is (e.g. "$0.040 / image" -> "0.040")
  - "$X / minute" -> use X as-is (e.g. "$0.006 / minute" -> "0.006")
  - "Free" or "$0" -> "0"
- Only scrape models that have individual detail pages on the models index
- If a model has fine-tuning pricing, include those as separate pricing entries with
  unit_type like "Fine-tuning Training Input", "Fine-tuning Training Output", etc.

## Error Handling
- If a page fails to load, retry once after a short wait
- If playwright-cli is not found, try using `npx @playwright/cli` instead
- If a specific model page doesn't have pricing, still include it with an empty pricing array
- Always save progress before moving to the next model
""".strip()

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    progress_path = os.path.join(project_root, PROGRESS_FILE)
    output_dir = os.path.join(project_root, "output")
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_folder = os.path.join(output_dir, f"run_{timestamp}")

    # Ensure run output directory exists
    os.makedirs(run_folder, exist_ok=True)

    # Build prompt with run folder path injected (relative for use in prompt)
    run_folder_rel = os.path.relpath(run_folder, project_root)
    scrape_prompt = SCRAPE_PROMPT_TEMPLATE.replace("{RUN_FOLDER}", run_folder_rel)

    # Clean up old progress file
    if os.path.exists(progress_path):
        os.remove(progress_path)
        print(f"Removed old progress file: {progress_path}")

    # Build subprocess command — prompt is piped via stdin to avoid
    # Windows command-line length limits (~8191 chars).
    cmd = [
        "claude.cmd",
        "-p",
        "--output-format", "json",
        "--json-schema", json.dumps(OPENAI_PRICING_SCHEMA),
        "--model", "opus",
        "--dangerously-skip-permissions",
    ]

    print("=" * 70)
    print("OpenAI Pricing Scraper via Claude Code + playwright-cli")
    print("=" * 70)
    print(f"Start time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Run folder: {run_folder}")
    print(f"Progress file: {progress_path}")
    print(f"Timeout: 1800s (30 minutes)")
    print("=" * 70)
    print()

    # --------------- Progress monitor thread ---------------
    prev_model_count = [0]
    prev_png_count = [0]
    stop_monitor = threading.Event()

    def monitor_progress():
        """Poll the progress file and screenshot count, print updates."""
        reported_complete = False
        while not stop_monitor.is_set():
            try:
                # Check for new screenshots
                png_count = len([f for f in os.listdir(run_folder) if f.endswith('.png')])
                if png_count > prev_png_count[0]:
                    prev_png_count[0] = png_count
                    print(f"  [PROGRESS] Screenshots: {png_count}")

                # Check progress file for new models
                if os.path.exists(progress_path):
                    with open(progress_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    count = len(data.get("models", []))
                    if count > prev_model_count[0]:
                        new_models = data["models"][prev_model_count[0]:]
                        for m in new_models:
                            name = m.get("model_name", "?")
                            n_prices = len(m.get("pricing", []))
                            print(f"  [PROGRESS] +{name} ({n_prices} price entries)")
                        prev_model_count[0] = count
                        print(f"  [PROGRESS] Total models so far: {count}")
                    status = data.get("status", "")
                    if status and status != "in_progress" and not reported_complete:
                        print(f"  [PROGRESS] Status: {status}")
                        reported_complete = True
            except (json.JSONDecodeError, IOError, KeyError):
                pass
            stop_monitor.wait(5)

    monitor_thread = threading.Thread(target=monitor_progress, daemon=True)
    monitor_thread.start()

    # --------------- Run Claude Code subprocess ---------------
    start_time = time.time()
    timed_out = False
    stdout_data = ""
    returncode = None

    print("[DEBUG] Launching Claude Code subprocess...")
    print(f"[DEBUG] Command: {' '.join(cmd)}")
    print(f"[DEBUG] Prompt length: {len(scrape_prompt)} chars")
    print()

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=project_root,
        )

        # Send prompt and close stdin
        proc.stdin.write(scrape_prompt)
        proc.stdin.close()

        # Read stdout in a background thread (avoids deadlock with stderr thread)
        stdout_chunks = []

        def read_stdout():
            stdout_chunks.append(proc.stdout.read())

        stdout_thread = threading.Thread(target=read_stdout, daemon=True)
        stdout_thread.start()

        # Stream stderr in real-time (Claude Code progress messages)
        def stream_stderr():
            for line in proc.stderr:
                line = line.rstrip("\n")
                if line:
                    print(f"  [CLAUDE] {line}")

        stderr_thread = threading.Thread(target=stream_stderr, daemon=True)
        stderr_thread.start()

        # Wait for process with timeout
        proc.wait(timeout=1800)
        returncode = proc.returncode
        stdout_thread.join(timeout=10)
        stderr_thread.join(timeout=5)
        stdout_data = "".join(stdout_chunks)

    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        proc.wait()
        print("\n[TIMEOUT] Claude Code timed out after 30 minutes.")
        print("Falling back to progress file for partial results...")

    stop_monitor.set()
    monitor_thread.join(timeout=5)

    elapsed = time.time() - start_time
    print(f"\nElapsed: {elapsed:.1f}s")

    # --------------- Extract results ---------------
    pricing_data = None
    source = None

    if not timed_out and returncode is not None:
        if returncode != 0:
            print(f"\n[ERROR] Claude Code exited with code {returncode}")
            print(f"STDOUT (first 2000 chars): {stdout_data[:2000]}")
        else:
            try:
                response = json.loads(stdout_data)

                if response.get("is_error"):
                    print(f"\n[ERROR] Claude returned an error:")
                    print(json.dumps(response, indent=2)[:2000])
                elif "structured_output" in response:
                    pricing_data = response["structured_output"]
                    source = "structured_output"
                    print("\n[OK] Got structured output from Claude Code.")

                    # Also capture metadata
                    cost = response.get("total_cost_usd", "unknown")
                    duration_ms = response.get("duration_ms", "unknown")
                    print(f"  API cost: ${cost}")
                    print(f"  Duration: {duration_ms}ms")
                else:
                    print("\n[WARN] Response missing structured_output.")
                    print(f"  Available keys: {list(response.keys())}")
                    print(f"  STDOUT (first 2000 chars): {stdout_data[:2000]}")
            except json.JSONDecodeError as e:
                print(f"\n[ERROR] Failed to parse Claude JSON response: {e}")
                print(f"  Raw stdout (first 2000 chars): {stdout_data[:2000]}")

    # Fallback to progress file
    if pricing_data is None and os.path.exists(progress_path):
        print(f"\nFalling back to progress file: {progress_path}")
        try:
            with open(progress_path, "r", encoding="utf-8") as f:
                pricing_data = json.load(f)
            source = "progress_file"
            print("[OK] Loaded partial results from progress file.")
        except (json.JSONDecodeError, IOError) as e:
            print(f"[ERROR] Could not read progress file: {e}")

    if pricing_data is None:
        print("\n[FAIL] No pricing data obtained.")
        sys.exit(1)

    # --------------- Save output ---------------
    output_path = os.path.join(run_folder, "openai_pricing.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(pricing_data, f, indent=2)

    print(f"\nResults saved to: {output_path}")
    print(f"Source: {source}")

    # --------------- Screenshot verification ---------------
    models = pricing_data.get("models", [])
    png_files = [f for f in os.listdir(run_folder) if f.endswith('.png')]
    print(f"\nScreenshots: {len(png_files)} files in {run_folder}")
    print(f"Models: {len(models)}")
    if len(png_files) < len(models):
        print(f"[WARN] Missing screenshots for {len(models) - len(png_files)} models")
    elif len(png_files) == 0:
        print("[FAIL] No screenshots were taken!")

    # --------------- Summary ---------------
    print(f"\n{'=' * 70}")
    print(f"SUMMARY: {len(models)} models scraped, {len(png_files)} screenshots")
    print(f"{'=' * 70}")

    for m in models:
        name = m.get("model_name", "?")
        region = m.get("region", "?")
        prices = m.get("pricing", [])
        price_summary = ", ".join(
            f"{p.get('unit_type', '?')}: {p.get('price', '?')}" for p in prices
        )
        print(f"  {name} (region={region})")
        if price_summary:
            print(f"    {price_summary}")

    print(f"\nDone. Elapsed: {elapsed:.1f}s")


if __name__ == "__main__":
    main()
