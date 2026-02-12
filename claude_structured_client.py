"""
Claude Code Structured Output Client
A clean interface for invoking Claude Code programmatically with guaranteed JSON schema compliance.
"""

import subprocess
import json
from typing import Dict, Any, Optional


class ClaudeStructuredClient:
    """Client for invoking Claude Code CLI with guaranteed JSON schema compliance."""

    def __init__(self, model: str = "sonnet", timeout: int = 120):
        """
        Initialize the Claude client.

        Args:
            model: Claude model to use ('sonnet', 'opus', 'haiku')
            timeout: Timeout in seconds for Claude invocations
        """
        self.model = model
        self.timeout = timeout
        self.claude_cmd = "claude.cmd"  # Windows

    def query(
        self,
        prompt: str,
        schema: Dict[str, Any],
        allowed_tools: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Invoke Claude Code with a prompt and get schema-compliant output.

        Args:
            prompt: The task/query for Claude
            schema: JSON Schema dict defining the required output structure
            allowed_tools: Optional comma-separated tool list (e.g., "Read,Grep,Bash")

        Returns:
            The structured_output field containing schema-compliant data

        Raises:
            RuntimeError: If Claude invocation fails
            ValueError: If response doesn't contain structured_output
            TimeoutError: If Claude takes longer than timeout
        """
        # Build command
        cmd = [
            self.claude_cmd,
            '-p',  # Print mode (non-interactive)
            prompt,
            '--output-format', 'json',
            '--json-schema', json.dumps(schema),
            '--model', self.model,
        ]

        if allowed_tools:
            cmd.extend(['--allowed-tools', allowed_tools])

        try:
            # Invoke Claude
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Claude invocation failed with code {result.returncode}:\n"
                    f"STDERR: {result.stderr}\n"
                    f"STDOUT: {result.stdout}"
                )

            # Parse response
            response = json.loads(result.stdout)

            # Check for errors
            if response.get('is_error'):
                raise RuntimeError(
                    f"Claude returned error:\n{json.dumps(response, indent=2)}"
                )

            # Extract structured output
            if 'structured_output' not in response:
                raise ValueError(
                    f"Response missing structured_output field. "
                    f"Available fields: {list(response.keys())}"
                )

            return response['structured_output']

        except subprocess.TimeoutExpired:
            raise TimeoutError(
                f"Claude invocation timed out after {self.timeout} seconds"
            )
        except json.JSONDecodeError as e:
            raise RuntimeError(
                f"Failed to parse Claude JSON response: {e}\n"
                f"Raw output: {result.stdout}"
            )

    def query_with_metadata(
        self,
        prompt: str,
        schema: Dict[str, Any],
        allowed_tools: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Same as query() but returns the full response including metadata.

        Returns:
            Full response dict with fields:
            - structured_output: Schema-compliant data
            - result: Human-readable summary
            - session_id: Session identifier
            - total_cost_usd: API cost
            - usage: Token usage stats
            - duration_ms: Total duration
        """
        cmd = [
            self.claude_cmd,
            '-p',
            prompt,
            '--output-format', 'json',
            '--json-schema', json.dumps(schema),
            '--model', self.model,
        ]

        if allowed_tools:
            cmd.extend(['--allowed-tools', allowed_tools])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Claude failed: {result.stderr}\n{result.stdout}"
                )

            response = json.loads(result.stdout)

            if response.get('is_error'):
                raise RuntimeError(
                    f"Claude error:\n{json.dumps(response, indent=2)}"
                )

            return response

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Timed out after {self.timeout}s")
        except json.JSONDecodeError as e:
            raise RuntimeError(f"JSON parse error: {e}\n{result.stdout}")


# Example usage
if __name__ == "__main__":
    # Initialize client
    client = ClaudeStructuredClient(model="sonnet")

    # Define your schema
    schema = {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "count": {"type": "number"},
            "items": {
                "type": "array",
                "items": {"type": "string"}
            }
        },
        "required": ["summary", "count", "items"]
    }

    # Query Claude with guaranteed schema compliance
    try:
        result = client.query(
            prompt="List 3 popular programming languages and summarize them",
            schema=schema
        )

        print("Structured Output (guaranteed schema-compliant):")
        print(json.dumps(result, indent=2))
        print(f"\nSummary: {result['summary']}")
        print(f"Count: {result['count']}")
        print(f"Items: {', '.join(result['items'])}")

    except Exception as e:
        print(f"Error: {e}")
