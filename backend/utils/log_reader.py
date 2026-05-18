"""Log file reading utilities — line parser, reverse-tail reader, async file tailer."""
import asyncio
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple

_LOG_RE = re.compile(
    r'^\[(?P<ts>[^\]]+)\] \[(?P<level>[^\]]+)\]'
    r'(?: \[job:(?P<job>[^\]]+)\])?'
    r'(?: \[(?P<agent>[^\]]+)\])?'
    r' (?P<message>.*)$'
)

_BLOCK = 16 * 1024  # 16 KB read-back blocks for reverse seek


def parse_log_line(line: str) -> Optional[Dict]:
    """Parse one structured log line into a dict; returns None for blank lines."""
    if not line or not line.strip():
        return None
    m = _LOG_RE.match(line)
    if m:
        return {
            "ts": m.group("ts"),
            "level": m.group("level"),
            "job": m.group("job"),
            "agent": m.group("agent"),
            "message": m.group("message"),
            "raw": line,
        }
    return {"ts": None, "level": "RAW", "job": None, "agent": None, "message": line, "raw": line}


def read_last_n_lines(path: Path, n: int) -> List[str]:
    """Return the last n non-empty lines from path; returns [] if file is missing."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            remaining = f.tell()
            chunks: List[bytes] = []
            while remaining > 0 and len(b"".join(chunks).split(b"\n")) <= n + 2:
                read_size = min(_BLOCK, remaining)
                remaining -= read_size
                f.seek(remaining)
                chunks.insert(0, f.read(read_size))
            content = b"".join(chunks).decode("utf-8", errors="replace")
            all_lines = [l for l in content.splitlines() if l.strip()]
            return all_lines[-n:] if len(all_lines) > n else all_lines
    except FileNotFoundError:
        return []


def matches_filters(
    entry: Dict,
    levels: Set[str],
    job_id: str,
    search: str,
) -> bool:
    """Return True if the parsed entry passes all active filters.

    Empty levels set means all levels pass. RAW entries are excluded when a
    level filter is active (they lack a proper level).
    """
    if levels:
        if entry["level"] == "RAW":
            return False
        if entry["level"] not in levels:
            return False
    if job_id and entry.get("job") and job_id.lower() not in entry["job"].lower():
        return False
    if job_id and not entry.get("job"):
        return False
    if search and search.lower() not in entry["message"].lower():
        return False
    return True


async def tail_files(
    paths: List[Path],
    filter_fn: Callable,
    poll_interval: float = 0.5,
):
    """Async generator: yield new parsed+filtered log entries as files grow.

    Handles log rotation by detecting inode change or size shrink and
    reopening from offset 0.
    """
    # Track (inode, offset) per path
    state: Dict[Path, Tuple[int, int]] = {}
    for p in paths:
        try:
            st = p.stat()
            state[p] = (st.st_ino, st.st_size)
        except FileNotFoundError:
            state[p] = (0, 0)

    while True:
        await asyncio.sleep(poll_interval)
        for p in paths:
            try:
                st = p.stat()
            except FileNotFoundError:
                state[p] = (0, 0)
                continue

            prev_ino, prev_offset = state[p]
            rotated = st.st_ino != prev_ino or st.st_size < prev_offset
            if rotated:
                prev_offset = 0

            if st.st_size <= prev_offset:
                state[p] = (st.st_ino, prev_offset)
                continue

            try:
                with open(p, "rb") as f:
                    f.seek(prev_offset)
                    new_bytes = f.read(st.st_size - prev_offset)
            except OSError:
                continue

            state[p] = (st.st_ino, prev_offset + len(new_bytes))
            text = new_bytes.decode("utf-8", errors="replace")
            for line in text.splitlines():
                if not line.strip():
                    continue
                entry = parse_log_line(line)
                if entry and filter_fn(entry):
                    yield entry
