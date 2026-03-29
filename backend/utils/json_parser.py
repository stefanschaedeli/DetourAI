import json
import re
from typing import Optional


def parse_agent_json(text: str) -> dict:
    """Strips markdown code fences and parses JSON, with truncation repair."""
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
            repaired = _repair_truncated_json(text)
            if repaired is not None:
                return repaired
            raise ValueError(
                f"JSON-Antwort wurde abgeschnitten (unvollständig: {opens} öffnende vs {closes} schliessende Klammern). "
                f"Ursprünglicher Fehler: {e}"
            ) from e
        raise


def _repair_truncated_json(text: str) -> Optional[dict]:
    """Attempt to repair truncated JSON by closing open strings, objects, arrays.

    Strategy: walk through the text tracking nesting, find the last valid
    complete element, then close all open structures.
    """
    # Step 1: If we're inside an unterminated string, close it
    repaired = _close_open_string(text)

    # Step 2: Remove any trailing partial key-value pair after last complete value
    # e.g. '..."foo": "bar", "baz": "incomplete...' → remove from last incomplete pair
    repaired = _trim_trailing_incomplete(repaired)

    # Step 3: Close all open brackets/braces
    stack = []
    in_string = False
    escape = False
    for ch in repaired:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append('}' if ch == '{' else ']')
        elif ch in ('}', ']'):
            if stack:
                stack.pop()

    # Append closing chars in reverse order
    repaired += ''.join(reversed(stack))

    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def _close_open_string(text: str) -> str:
    """If text ends inside an unclosed string, close it with a quote."""
    in_string = False
    escape = False
    for ch in text:
        if escape:
            escape = False
            continue
        if ch == '\\' and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
    if in_string:
        # Remove any trailing incomplete escape sequence
        text = text.rstrip('\\')
        text += '"'
    return text


def _trim_trailing_incomplete(text: str) -> str:
    """Remove trailing incomplete elements after the last complete value.

    Looks for patterns like:  ,"key": "val...  or  , "key":  at end
    and trims back to the last complete value.
    """
    # Try parsing as-is first to avoid unnecessary trimming
    # Find the last complete array element or object entry
    # by looking for trailing comma + incomplete content
    stripped = text.rstrip()

    # If ends with a comma, remove it (incomplete next element)
    if stripped.endswith(','):
        return stripped[:-1]

    # If there's a trailing incomplete object value after a colon,
    # remove the whole key-value pair back to the previous comma or opening brace
    # Pattern: ... , "key": "incomplete_value"  (we already closed the string above)
    # We need to remove from the last comma before this incomplete pair
    # Look for the last complete structure
    for trim_pattern in [
        # Trailing key-value with closed string value, after our string repair
        r',\s*"[^"]*"\s*:\s*"[^"]*"\s*$',
        # Trailing key with no value
        r',\s*"[^"]*"\s*:\s*$',
        # Trailing key only
        r',\s*"[^"]*"\s*$',
    ]:
        m = re.search(trim_pattern, stripped)
        if m:
            candidate = stripped[:m.start()]
            # Only trim if the result looks like it ends at a valid point
            last_char = candidate.rstrip()[-1:] if candidate.rstrip() else ''
            if last_char in ('"', '}', ']', '0', '1', '2', '3', '4', '5',
                             '6', '7', '8', '9', 'e', 'l', 'n'):
                return candidate

    return stripped
