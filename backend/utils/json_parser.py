import json
import re


def parse_agent_json(text: str) -> dict:
    """Strips markdown code fences and parses JSON."""
    text = text.strip()
    text = re.sub(r'^```[a-z]*\n?', '', text)
    text = re.sub(r'\n?```$', '', text)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Check for truncation: unbalanced braces/brackets
        opens = text.count('{') + text.count('[')
        closes = text.count('}') + text.count(']')
        if opens > closes:
            raise ValueError(
                f"JSON-Antwort wurde abgeschnitten (unvollständig: {opens} öffnende vs {closes} schliessende Klammern). "
                f"Ursprünglicher Fehler: {e}"
            ) from e
        raise
