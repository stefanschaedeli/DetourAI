import asyncio
from enum import Enum
from datetime import datetime


class LogLevel(str, Enum):
    DEBUG   = "DEBUG"
    INFO    = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR   = "ERROR"
    AGENT   = "AGENT"
    API     = "API"


class DebugLogger:
    def __init__(self):
        self._subscribers: dict[str, asyncio.Queue] = {}

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=1000)
        self._subscribers[job_id] = q
        return q

    def unsubscribe(self, job_id: str):
        self._subscribers.pop(job_id, None)

    async def log(self, level: LogLevel, message: str, *,
                  job_id: str = None, agent: str = None, data: dict = None):
        # Terminal output (ANSI colors)
        color = {
            LogLevel.DEBUG:   "\033[94m",
            LogLevel.INFO:    "\033[96m",
            LogLevel.SUCCESS: "\033[92m",
            LogLevel.WARNING: "\033[93m",
            LogLevel.ERROR:   "\033[91m",
            LogLevel.AGENT:   "\033[95m",
            LogLevel.API:     "\033[33m",   # yellow for API calls
        }.get(level, "")
        reset = "\033[0m"
        prefix = f"[{agent}] " if agent else ""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"{color}[{ts}][{level.value}] {prefix}{message}{reset}")

        # SSE push
        if job_id and job_id in self._subscribers:
            try:
                self._subscribers[job_id].put_nowait({
                    "type": "debug_log",
                    "level": level.value,
                    "message": message,
                    "agent": agent,
                    "data": data,
                    "ts": datetime.now().isoformat(),
                })
            except asyncio.QueueFull:
                pass

    async def log_prompt(self, agent: str, model: str, prompt: str, *,
                         job_id: str = None):
        """Print the full prompt sent to Claude in a clearly delimited block."""
        sep = "─" * 60
        print(f"\033[90m[{datetime.now().strftime('%H:%M:%S')}][PROMPT] [{agent}] → {model}\n{sep}\n{prompt}\n{sep}\033[0m")

    async def push_event(self, job_id: str, event_type: str,
                         agent_id, data, percent: int = 0):
        if job_id in self._subscribers:
            try:
                self._subscribers[job_id].put_nowait({
                    "type": event_type,
                    "agent_id": agent_id,
                    "data": data,
                    "percent": percent,
                })
            except asyncio.QueueFull:
                pass


debug_logger = DebugLogger()   # module-level singleton
