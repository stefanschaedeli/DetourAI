import json
import re


def parse_agent_json(text: str) -> dict:
    """Strips markdown code fences and parses JSON."""
    text = text.strip()
    text = re.sub(r'^```[a-z]*\n?', '', text)
    text = re.sub(r'\n?```$', '', text)
    text = text.strip()
    return json.loads(text)
