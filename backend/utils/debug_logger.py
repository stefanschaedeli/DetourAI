import asyncio
import json
import os
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


def _get_redis():
    """Return a Redis client if available, else None."""
    redis_url = os.getenv("REDIS_URL", "")
    if not redis_url:
        return None
    try:
        import redis as redis_lib
        client = redis_lib.from_url(redis_url, decode_responses=True)
        client.ping()
        return client
    except Exception:
        return None


class DebugLogger:
    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._redis = None      # lazily initialised
        self._redis_tried = False

    def _r(self):
        """Lazily get Redis client (cached after first attempt)."""
        if not self._redis_tried:
            self._redis_tried = True
            self._redis = _get_redis()
        return self._redis

    def _redis_push(self, job_id: str, event: dict):
        """Push a serialised event onto the Redis list sse:{job_id}."""
        r = self._r()
        if r:
            try:
                key = f"sse:{job_id}"
                r.rpush(key, json.dumps(event))
                r.expire(key, 3600)   # 1h TTL — stream is short-lived
            except Exception:
                pass

    def subscribe(self, job_id: str) -> asyncio.Queue:
        q = asyncio.Queue(maxsize=1000)
        self._subscribers.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, queue: asyncio.Queue = None):
        if job_id not in self._subscribers:
            return
        if queue is not None:
            try:
                self._subscribers[job_id].remove(queue)
            except ValueError:
                pass
            if not self._subscribers[job_id]:
                del self._subscribers[job_id]
        else:
            del self._subscribers[job_id]

    def _local_push(self, job_id: str, event: dict):
        """Push to all in-process queues registered for this job."""
        for q in list(self._subscribers.get(job_id, [])):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

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
            LogLevel.API:     "\033[33m",
        }.get(level, "")
        reset = "\033[0m"
        prefix = f"[{agent}] " if agent else ""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"{color}[{ts}][{level.value}] {prefix}{message}{reset}")

        if job_id:
            event = {
                "type": "debug_log",
                "level": level.value,
                "message": message,
                "agent": agent,
                "data": data,
                "ts": datetime.now().isoformat(),
            }
            self._local_push(job_id, event)
            self._redis_push(job_id, event)

    async def log_prompt(self, agent: str, model: str, prompt: str, *,
                         job_id: str = None):
        sep = "─" * 60
        print(f"\033[90m[{datetime.now().strftime('%H:%M:%S')}][PROMPT] [{agent}] → {model}\n{sep}\n{prompt}\n{sep}\033[0m")

    async def push_event(self, job_id: str, event_type: str,
                         agent_id, data, percent: int = 0):
        event = {
            "type": event_type,
            "agent_id": agent_id,
            "data": data,
            "percent": percent,
        }
        self._local_push(job_id, event)
        self._redis_push(job_id, event)


debug_logger = DebugLogger()   # module-level singleton
