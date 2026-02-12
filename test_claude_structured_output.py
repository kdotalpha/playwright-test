#!/usr/bin/env python3
"""
Test script to verify Claude Code CLI can be invoked programmatically
with guaranteed JSON schema compliance.
"""

import subprocess
import json
import sys


def test_claude_structured_output():
    """Test invoking Claude Code with --json-schema flag."""

    # Define a simple JSON schema
    schema = {
        "type": "object",
        "properties": {
            "result": {
                "type": "string",
                "description": "The result of the calculation"
            },
            "value": {
                "type": "number",
                "description": "The numeric value"
            }
        },
        "required": ["result", "value"]
    }

    # Simple prompt that should produce structured output
    prompt = "Calculate 5 + 3 and return the result as a number and a string description"

    print("=" * 60)
    print("Testing Claude Code CLI with structured output")
    print("=" * 60)
    print(f"\nPrompt: {prompt}")
    print(f"\nRequired Schema:\n{json.dumps(schema, indent=2)}")
    print("\nInvoking Claude Code CLI...")
    print("-" * 60)

    try:
        # Invoke Claude Code with json-schema
        result = subprocess.run([
            'claude.cmd',  # Use .cmd on Windows
            '-p',  # Print mode (non-interactive)
            prompt,
            '--output-format', 'json',
            '--json-schema', json.dumps(schema),
            '--model', 'sonnet',  # Use Sonnet for faster response
        ],
        capture_output=True,
        text=True,
        timeout=60
        )

        print(f"\nReturn code: {result.returncode}")

        if result.returncode != 0:
            print(f"\nSTDERR:\n{result.stderr}")
            print(f"\nSTDOUT:\n{result.stdout}")
            return False

        # Parse the JSON response
        response = json.loads(result.stdout)

        print("\nFull Response Structure:")
        print(json.dumps(response, indent=2))

        # Check if structured_output field exists
        if 'structured_output' in response:
            print("\n[OK] SUCCESS: structured_output field found!")
            print(f"\nStructured Output:\n{json.dumps(response['structured_output'], indent=2)}")

            # Validate it matches schema
            output = response['structured_output']
            if 'result' in output and 'value' in output:
                print("\n[OK] Schema validation passed!")
                print(f"  - result (string): {output['result']}")
                print(f"  - value (number): {output['value']}")
                return True
            else:
                print("\n[FAIL] FAIL: Output missing required fields")
                return False
        else:
            print("\n[FAIL] FAIL: No structured_output field in response")
            print("Available fields:", list(response.keys()))
            return False

    except subprocess.TimeoutExpired:
        print("\n[FAIL] FAIL: Command timed out after 60 seconds")
        return False
    except json.JSONDecodeError as e:
        print(f"\n[FAIL] FAIL: Could not parse JSON response: {e}")
        print(f"\nRaw output:\n{result.stdout}")
        return False
    except Exception as e:
        print(f"\n[FAIL] FAIL: Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\nClaude Code Structured Output Test")
    print("=" * 60)

    success = test_claude_structured_output()

    print("\n" + "=" * 60)
    if success:
        print("[OK] TEST PASSED: Claude Code structured output works!")
        sys.exit(0)
    else:
        print("[FAIL] TEST FAILED: Could not get structured output")
        sys.exit(1)
