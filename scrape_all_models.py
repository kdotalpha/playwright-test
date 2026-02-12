"""
Automated scraper for OpenAI model pricing pages.
Uses playwright-cli to visit each model's individual detail page.
"""
import subprocess
import json
import re
import os
import shutil
import time
from datetime import datetime, timezone

BASE_URL = "https://developers.openai.com"
OUTPUT_DIR = "output/run_20260212_214046"
PROGRESS_FILE = "openai_pricing_progress.json"
WORK_DIR = r"C:\Users\DavidTepper\OneDrive\Code\Pay-i\playwright-test"

# All unique model URLs found on the index page
MODEL_URLS = [
    "/api/docs/models/babbage-002",
    "/api/docs/models/chatgpt-4o-latest",
    "/api/docs/models/chatgpt-image-latest",
    "/api/docs/models/codex-mini-latest",
    "/api/docs/models/computer-use-preview",
    "/api/docs/models/dall-e-2",
    "/api/docs/models/dall-e-3",
    "/api/docs/models/davinci-002",
    "/api/docs/models/gpt-3",
    "/api/docs/models/gpt-4",
    "/api/docs/models/gpt-4-turbo",
    "/api/docs/models/gpt-4-turbo-preview",
    "/api/docs/models/gpt-4o",
    "/api/docs/models/gpt-4o-audio-preview",
    "/api/docs/models/gpt-4o-mini",
    "/api/docs/models/gpt-4o-mini-audio-preview",
    "/api/docs/models/gpt-4o-mini-realtime-preview",
    "/api/docs/models/gpt-4o-mini-search-preview",
    "/api/docs/models/gpt-4o-mini-transcribe",
    "/api/docs/models/gpt-4o-mini-tts",
    "/api/docs/models/gpt-4o-realtime-preview",
    "/api/docs/models/gpt-4o-search-preview",
    "/api/docs/models/gpt-4o-transcribe",
    "/api/docs/models/gpt-4o-transcribe-diarize",
    "/api/docs/models/gpt-5",
    "/api/docs/models/gpt-5-chat-latest",
    "/api/docs/models/gpt-5-codex",
    "/api/docs/models/gpt-5-mini",
    "/api/docs/models/gpt-5-nano",
    "/api/docs/models/gpt-5-pro",
    "/api/docs/models/gpt-audio",
    "/api/docs/models/gpt-audio-mini",
    "/api/docs/models/gpt-image-1",
    "/api/docs/models/gpt-image-1-mini",
    "/api/docs/models/gpt-oss-120b",
    "/api/docs/models/gpt-oss-20b",
    "/api/docs/models/gpt-realtime",
    "/api/docs/models/gpt-realtime-mini",
    "/api/docs/models/o1",
    "/api/docs/models/o1-mini",
    "/api/docs/models/o1-preview",
    "/api/docs/models/o1-pro",
    "/api/docs/models/o3",
    "/api/docs/models/o3-deep-research",
    "/api/docs/models/o3-mini",
    "/api/docs/models/o3-pro",
    "/api/docs/models/o4-mini",
    "/api/docs/models/o4-mini-deep-research",
    "/api/docs/models/omni-moderation-latest",
    "/api/docs/models/sora-2",
    "/api/docs/models/sora-2-pro",
    "/api/docs/models/text-embedding-3-large",
    "/api/docs/models/text-embedding-3-small",
    "/api/docs/models/text-embedding-ada-002",
    "/api/docs/models/text-moderation-latest",
    "/api/docs/models/text-moderation-stable",
    "/api/docs/models/tts-1",
    "/api/docs/models/tts-1-hd",
    "/api/docs/models/whisper-1",
]


def run_cli(cmd):
    """Run a playwright-cli command and return output."""
    full_cmd = f"npx @playwright/cli {cmd}"
    result = subprocess.run(
        full_cmd, shell=True, capture_output=True, text=True,
        cwd=WORK_DIR, timeout=60
    )
    return result.stdout + result.stderr


def get_snapshot_path(output):
    """Extract snapshot file path from CLI output."""
    # Find all snapshot paths, take the last one (most recent)
    matches = re.findall(r'\[Snapshot\]\(([^)]+)\)', output)
    if matches:
        return matches[-1]
    return None


def get_screenshot_path(output):
    """Extract screenshot file path from CLI output."""
    match = re.search(r'(\.playwright-cli[/\\]page-[^\s\]]+\.png)', output)
    if match:
        return match.group(1)
    match = re.search(r'Screenshot.*?:\s*(.+\.png)', output)
    if match:
        return match.group(1).strip()
    return None


def find_pricing_section(lines):
    """Find the start of the main Pricing section in the model detail page.

    The pricing section is identified by a generic element containing just 'Pricing'
    that is NOT inside the navigation sidebar (link elements).
    It's followed by a text block starting with 'Pricing is based on...'
    """
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Match: "- generic [ref=eXXX]: Pricing" (the section heading)
        if re.match(r'- generic \[ref=e\d+\]: Pricing$', stripped):
            # Verify: within next 5 lines there should be "Pricing is based on"
            for j in range(i+1, min(i+6, len(lines))):
                if 'Pricing is based on' in lines[j]:
                    return i
    return None


def extract_pricing_from_snapshot(snapshot_text, model_name):
    """Extract pricing information from a snapshot YAML.

    Observed pricing section patterns on OpenAI model detail pages:

    1. Text tokens (Per 1M tokens) with Input/Cached input/Output
    2. Audio tokens (Per 1M tokens) with Input/Cached input/Output
    3. Image generation (Per image) with Quality/Resolution/Price
    4. Simple pricing (Per 1M tokens) with Use case/Cost (whisper, tts, embeddings)
    5. Free / no pricing shown
    """
    pricing = []
    lines = snapshot_text.split('\n')

    pricing_start = find_pricing_section(lines)
    if pricing_start is None:
        return pricing

    # Work within pricing section (up to ~150 lines or until next major section)
    pricing_end = min(pricing_start + 150, len(lines))
    for i in range(pricing_start + 10, pricing_end):
        stripped = lines[i].strip()
        # Stop at next major section: Modalities, Endpoints, Features, etc.
        if re.match(r'- generic \[ref=e\d+\]: (Modalities|Endpoints|Features|Snapshots|Rate limits|Tools)$', stripped):
            pricing_end = i
            break

    section_lines = lines[pricing_start:pricing_end]
    section_text = '\n'.join(section_lines)

    # Determine what pricing subsections exist
    has_text_tokens = 'Text tokens' in section_text
    has_audio_tokens = 'Audio tokens' in section_text
    has_image_tokens = 'Image tokens' in section_text
    has_per_image = 'Per image' in section_text
    has_per_second = 'Per second' in section_text
    has_use_case_cost = 'Use case' in section_text and 'Cost' in section_text
    # Embeddings: has "Cost" label + "$X" but no "Use case"
    has_cost_only = (not has_use_case_cost and
                     re.search(r'generic \[ref=e\d+\]: Cost$', section_text, re.MULTILINE) is not None)

    if has_text_tokens or has_audio_tokens or has_image_tokens:
        # Parse structured token pricing sections
        # Split into subsections by looking for "Text tokens" / "Audio tokens" markers
        current_prefix = ""
        in_quick_comparison = False
        i = 0
        while i < len(section_lines):
            line = section_lines[i].strip()

            # Detect subsection headers
            if re.search(r'generic \[ref=e\d+\]: Text tokens$', line):
                current_prefix = ""
                in_quick_comparison = False
            elif re.search(r'generic \[ref=e\d+\]: Audio tokens$', line):
                current_prefix = "Audio "
                in_quick_comparison = False
            elif re.search(r'generic \[ref=e\d+\]: Image tokens$', line):
                current_prefix = "Image "
                in_quick_comparison = False

            # Skip "Quick comparison" subsections (they show OTHER models' prices)
            if 'Quick comparison' in line:
                in_quick_comparison = True
            # Reset quick comparison when we hit a new subsection
            if re.search(r'generic \[ref=e\d+\]: (Text tokens|Audio tokens|Image tokens|Image generation)$', line):
                in_quick_comparison = False

            if not in_quick_comparison:
                # Look for label: Input, Cached input, Output followed by price
                for label in ['Cached input', 'Input', 'Output']:
                    if re.search(rf'generic \[ref=e\d+\]: {re.escape(label)}$', line):
                        # Look at next line for price
                        if i + 1 < len(section_lines):
                            next_line = section_lines[i + 1].strip()
                            price_match = re.search(r'\$([0-9]+(?:\.[0-9]+)?)', next_line)
                            if price_match:
                                unit_type = f"{current_prefix}{label}"
                                price_val = float(price_match.group(1))
                                per_unit = price_val / 1_000_000
                                # Format with enough precision
                                price_str = f"{per_unit:.10f}".rstrip('0').rstrip('.')
                                # Avoid duplicates
                                if not any(p['unit_type'] == unit_type for p in pricing):
                                    pricing.append({
                                        "unit_type": unit_type,
                                        "price": price_str
                                    })
                        break
            i += 1

    elif has_per_image:
        # Parse image pricing: look for quality+resolution+price patterns
        # DALL-E style: Quality (Standard/HD), Resolution, Price
        current_quality = None
        i = 0
        in_quick_comparison = False
        while i < len(section_lines):
            line = section_lines[i].strip()

            if 'Quick comparison' in line:
                in_quick_comparison = True
            if re.search(r'generic \[ref=e\d+\]: (Image generation|Modalities)$', line) and i > 5:
                in_quick_comparison = False

            if not in_quick_comparison:
                # Detect quality level
                quality_match = re.search(r'generic \[ref=e\d+\]: (Standard|HD|Low|Medium|High)$', line)
                if quality_match:
                    current_quality = quality_match.group(1)

                # Detect resolution + price pairs
                resolution_match = re.search(r'generic \[ref=e\d+\]: (\d+x\d+)$', line)
                if resolution_match and current_quality:
                    resolution = resolution_match.group(1)
                    # Next line should have price
                    if i + 1 < len(section_lines):
                        next_line = section_lines[i + 1].strip()
                        price_match = re.search(r'\$([0-9]+(?:\.[0-9]+)?)', next_line)
                        if price_match:
                            unit_type = f"Per Image ({current_quality} {resolution})"
                            pricing.append({
                                "unit_type": unit_type,
                                "price": price_match.group(1)
                            })
            i += 1

    elif has_use_case_cost:
        # Simple pricing: "Use case" + "Cost" pattern (whisper, tts, embeddings)
        i = 0
        current_use_case = None
        in_quick_comparison = False
        while i < len(section_lines):
            line = section_lines[i].strip()

            if 'Quick comparison' in line:
                in_quick_comparison = True

            if not in_quick_comparison:
                # Look for use case
                uc_match = re.search(r'generic \[ref=e\d+\]: (Transcription|Speech generation|Embedding|Translation|Diarization|Search)$', line)
                if uc_match:
                    current_use_case = uc_match.group(1)

                # Look for cost value
                cost_match = re.search(r'generic \[ref=e\d+\]: \$([0-9]+(?:\.[0-9]+)?)$', line)
                if cost_match and current_use_case:
                    price_val = float(cost_match.group(1))
                    # Determine unit from nearby context
                    nearby = '\n'.join(section_lines[max(0,i-10):i])
                    if 'Per 1M tokens' in nearby:
                        per_unit = price_val / 1_000_000
                        price_str = f"{per_unit:.10f}".rstrip('0').rstrip('.')
                    elif 'Per 1M characters' in nearby:
                        per_unit = price_val / 1_000_000
                        price_str = f"{per_unit:.10f}".rstrip('0').rstrip('.')
                    elif 'Per minute' in nearby:
                        price_str = f"{price_val}"
                    elif 'Per image' in nearby:
                        price_str = f"{price_val}"
                    else:
                        # Default: assume per 1M tokens
                        per_unit = price_val / 1_000_000
                        price_str = f"{per_unit:.10f}".rstrip('0').rstrip('.')

                    pricing.append({
                        "unit_type": current_use_case,
                        "price": price_str
                    })
                    current_use_case = None  # Reset to avoid double-counting
            i += 1

    elif has_per_second:
        # Video pricing (Sora): "Video generation" / "Per second" / resolution + price
        in_quick_comparison = False
        for i, line in enumerate(section_lines):
            stripped = line.strip()
            if 'Quick comparison' in stripped:
                in_quick_comparison = True
            if not in_quick_comparison:
                # Look for price after a resolution/description line
                price_match = re.search(r'generic \[ref=e\d+\]: \$([0-9]+(?:\.[0-9]+)?)$', stripped)
                if price_match:
                    # Get the description from the previous line
                    desc = ""
                    if i > 0:
                        prev = section_lines[i-1].strip()
                        desc_match = re.search(r'generic \[ref=e\d+\]: "?(.+?)"?$', prev)
                        if desc_match:
                            desc = desc_match.group(1)
                    unit_type = f"Per Second"
                    if desc:
                        unit_type = f"Per Second ({desc})"
                    pricing.append({
                        "unit_type": unit_type,
                        "price": price_match.group(1)
                    })
                    break  # Usually just one price for sora

    elif has_cost_only:
        # Simple cost pricing (embeddings): section header + "Cost" + "$X"
        in_quick_comparison = False
        for i, line in enumerate(section_lines):
            stripped = line.strip()
            if 'Quick comparison' in stripped:
                in_quick_comparison = True
            if not in_quick_comparison:
                # Look for "Cost" label followed by price
                if re.search(r'generic \[ref=e\d+\]: Cost$', stripped):
                    if i + 1 < len(section_lines):
                        next_line = section_lines[i + 1].strip()
                        price_match = re.search(r'\$([0-9]+(?:\.[0-9]+)?)', next_line)
                        if price_match:
                            price_val = float(price_match.group(1))
                            # Determine unit
                            nearby = '\n'.join(section_lines[max(0,i-10):i])
                            if 'Per 1M tokens' in nearby:
                                per_unit = price_val / 1_000_000
                                price_str = f"{per_unit:.10f}".rstrip('0').rstrip('.')
                            elif 'Per 1M characters' in nearby:
                                per_unit = price_val / 1_000_000
                                price_str = f"{per_unit:.10f}".rstrip('0').rstrip('.')
                            else:
                                per_unit = price_val / 1_000_000
                                price_str = f"{per_unit:.10f}".rstrip('0').rstrip('.')
                            pricing.append({
                                "unit_type": "Input",
                                "price": price_str
                            })
                            break

    else:
        # Check for any dollar amounts at all in the pricing section
        # Some models may have pricing in unexpected formats
        for i, line in enumerate(section_lines):
            stripped = line.strip()
            # Look for Input/Output with prices
            for label in ['Cached input', 'Input', 'Output']:
                if re.search(rf'generic \[ref=e\d+\]: {re.escape(label)}$', stripped):
                    if i + 1 < len(section_lines):
                        next_line = section_lines[i + 1].strip()
                        price_match = re.search(r'\$([0-9]+(?:\.[0-9]+)?)', next_line)
                        if price_match:
                            price_val = float(price_match.group(1))
                            per_unit = price_val / 1_000_000
                            price_str = f"{per_unit:.10f}".rstrip('0').rstrip('.')
                            if not any(p['unit_type'] == label for p in pricing):
                                pricing.append({
                                    "unit_type": label,
                                    "price": price_str
                                })

        # Check for "Free" pricing
        if not pricing:
            for line in section_lines:
                if re.search(r'generic \[ref=e\d+\]: Free$', line.strip()):
                    pricing.append({"unit_type": "Input", "price": "0"})
                    break

    return pricing


def model_name_from_url(url):
    return url.split('/')[-1]


def safe_filename(name):
    return name.replace('/', '_').replace('\\', '_')


def save_progress(models_data, status="in_progress"):
    progress = {
        "models": models_data,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "status": status
    }
    with open(os.path.join(WORK_DIR, PROGRESS_FILE), 'w') as f:
        json.dump(progress, f, indent=2)


def main():
    os.makedirs(os.path.join(WORK_DIR, OUTPUT_DIR), exist_ok=True)

    all_models = []

    # Start fresh - delete old progress
    progress_path = os.path.join(WORK_DIR, PROGRESS_FILE)
    if os.path.exists(progress_path):
        os.remove(progress_path)

    for idx, model_url in enumerate(MODEL_URLS):
        model_name = model_name_from_url(model_url)

        print(f"\n[{idx+1}/{len(MODEL_URLS)}] Scraping {model_name}...")

        # Navigate to model page
        nav_output = run_cli(f'goto "{BASE_URL}{model_url}"')

        # Small delay for page to render
        time.sleep(1.5)

        # Take snapshot
        snap_output = run_cli('snapshot')
        snap_path = get_snapshot_path(snap_output)

        pricing = []
        if snap_path:
            snap_full_path = os.path.join(WORK_DIR, snap_path)
            try:
                with open(snap_full_path, 'r', encoding='utf-8') as f:
                    snapshot_text = f.read()
                pricing = extract_pricing_from_snapshot(snapshot_text, model_name)
                if pricing:
                    for p in pricing:
                        print(f"    {p['unit_type']}: {p['price']}")
                else:
                    print(f"    (no pricing found)")
            except Exception as e:
                print(f"    Error reading snapshot: {e}")
        else:
            print(f"    No snapshot path found")

        # Take screenshot
        ss_output = run_cli('screenshot')
        ss_path = get_screenshot_path(ss_output)
        if ss_path:
            src = os.path.join(WORK_DIR, ss_path)
            dst = os.path.join(WORK_DIR, OUTPUT_DIR, f"{safe_filename(model_name)}.png")
            try:
                shutil.copy2(src, dst)
                os.remove(src)
            except Exception as e:
                print(f"    Screenshot error: {e}")

        model_data = {
            "model_name": model_name,
            "region": "global",
            "pricing": pricing
        }
        all_models.append(model_data)
        save_progress(all_models)

    # Final save
    save_progress(all_models, status="completed")
    print(f"\n=== DONE: Scraped {len(all_models)} models ===")

    with_pricing = [m for m in all_models if m['pricing']]
    without_pricing = [m for m in all_models if not m['pricing']]
    print(f"Models with pricing: {len(with_pricing)}")
    print(f"Models without pricing: {len(without_pricing)}")
    for m in without_pricing:
        print(f"  - {m['model_name']}")


if __name__ == '__main__':
    main()
