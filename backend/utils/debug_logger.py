import asyncio
import json
import logging
import logging.handlers
import os
from enum import Enum
from datetime import datetime
from pathlib import Path


class LogLevel(str, Enum):
    DEBUG   = "DEBUG"
    INFO    = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR   = "ERROR"
    AGENT   = "AGENT"
    API     = "API"
    PROMPT  = "PROMPT"


class VerbosityLevel(str, Enum):
    MINIMAL   = "minimal"
    NORMAL    = "normal"
    VERBOSE   = "verbose"
    DEBUG_ALL = "debug"


# Which LogLevels are written to file at each verbosity
VERBOSITY_FILTER: dict[VerbosityLevel, set[LogLevel]] = {
    VerbosityLevel.MINIMAL: {LogLevel.ERROR, LogLevel.WARNING},
    VerbosityLevel.NORMAL: {LogLevel.ERROR, LogLevel.WARNING, LogLevel.SUCCESS,
                            LogLevel.INFO, LogLevel.AGENT},
    VerbosityLevel.VERBOSE: {LogLevel.ERROR, LogLevel.WARNING, LogLevel.SUCCESS,
                             LogLevel.INFO, LogLevel.AGENT, LogLevel.API},
    VerbosityLevel.DEBUG_ALL: {LogLevel.ERROR, LogLevel.WARNING, LogLevel.SUCCESS,
                               LogLevel.INFO, LogLevel.AGENT, LogLevel.API,
                               LogLevel.DEBUG, LogLevel.PROMPT},
}

# Agent class name → log file path (relative to logs dir)
_COMPONENT_MAP: dict[str, str] = {
    "RouteArchitect": "agents/route_architect",
    "RouteArchitectAgent": "agents/route_architect",
    "StopOptionsFinder": "agents/stop_options_finder",
    "StopOptionsFinderAgent": "agents/stop_options_finder",
    "RegionPlanner": "agents/region_planner",
    "RegionPlannerAgent": "agents/region_planner",
    "AccommodationResearcher": "agents/accommodation_researcher",
    "AccommodationResearcherAgent": "agents/accommodation_researcher",
    "ActivitiesAgent": "agents/activities_agent",
    "RestaurantsAgent": "agents/restaurants_agent",
    "DayPlanner": "agents/day_planner",
    "DayPlannerAgent": "agents/day_planner",
    "TravelGuideAgent": "agents/travel_guide_agent",
    "TripAnalysisAgent": "agents/trip_analysis_agent",
    "OutputGenerator": "agents/output_generator",
    "Orchestrator": "orchestrator/orchestrator",
}


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
        # File logging
        self._file_loggers: dict[str, logging.Logger] = {}
        self._verbosity: dict[str, VerbosityLevel] = {}  # per job_id
        self._default_verbosity = VerbosityLevel.NORMAL
        self._logs_dir = Path(os.getenv("LOGS_DIR", Path(__file__).parent.parent / "logs"))

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

    def _local_push(self, job_id: str, event: dict) -> bool:
        """Push to all in-process queues registered for this job.
        Returns True if at least one local subscriber received the event."""
        queues = list(self._subscribers.get(job_id, []))
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass
        return len(queues) > 0

    # ── File logging ──────────────────────────────────────────────

    def set_verbosity(self, job_id: str, level_str: str) -> None:
        """Set the file-logging verbosity for a specific job."""
        try:
            self._verbosity[job_id] = VerbosityLevel(level_str)
        except ValueError:
            self._verbosity[job_id] = self._default_verbosity

    def clear_verbosity(self, job_id: str) -> None:
        """Clean up verbosity setting after job ends."""
        self._verbosity.pop(job_id, None)

    def _get_file_logger(self, component: str) -> logging.Logger:
        """Lazy-create a logger with TimedRotatingFileHandler for a component."""
        if component in self._file_loggers:
            return self._file_loggers[component]

        log_path = self._logs_dir / f"{component}.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger(f"travelman.{component.replace('/', '.')}")
        logger.setLevel(logging.DEBUG)
        logger.propagate = False

        # Avoid duplicate handlers on reload
        if not logger.handlers:
            handler = logging.handlers.TimedRotatingFileHandler(
                str(log_path), when="midnight", backupCount=30, encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter(
                "[%(asctime)s] [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            ))
            logger.addHandler(handler)

        self._file_loggers[component] = logger
        return logger

    def _should_log_to_file(self, level: LogLevel, job_id: str = None) -> bool:
        """Check whether this level should be written to file given the job's verbosity."""
        verbosity = self._verbosity.get(job_id, self._default_verbosity) if job_id else self._default_verbosity
        return level in VERBOSITY_FILTER.get(verbosity, VERBOSITY_FILTER[VerbosityLevel.NORMAL])

    def _write_to_file(self, level: LogLevel, message: str, *,
                       job_id: str = None, agent: str = None) -> None:
        """Write a log line to the appropriate component file."""
        if not self._should_log_to_file(level, job_id):
            return

        component = _COMPONENT_MAP.get(agent, "api/api") if agent else "api/api"
        logger = self._get_file_logger(component)

        job_tag = f"[job:{job_id[:8]}] " if job_id else ""
        agent_tag = f"[{agent}] " if agent else ""
        line = f"{job_tag}{agent_tag}{message}"

        # Map our LogLevel to Python logging levels
        py_level = {
            LogLevel.DEBUG: logging.DEBUG,
            LogLevel.INFO: logging.INFO,
            LogLevel.SUCCESS: logging.INFO,
            LogLevel.WARNING: logging.WARNING,
            LogLevel.ERROR: logging.ERROR,
            LogLevel.AGENT: logging.INFO,
            LogLevel.API: logging.DEBUG,
            LogLevel.PROMPT: logging.DEBUG,
        }.get(level, logging.INFO)

        logger.log(py_level, line)

    def log_frontend(self, level: str, message: str, source: str = "",
                     stack: str = "") -> None:
        """Write a frontend error/warning/info to the frontend log file."""
        logger = self._get_file_logger("frontend/frontend")
        source_tag = f" [{source}]" if source else ""
        line = f"{source_tag} {message}"
        if stack:
            line += f"\n{stack}"

        py_level = {"error": logging.ERROR, "warning": logging.WARNING,
                     "info": logging.INFO}.get(level, logging.INFO)
        logger.log(py_level, line)

    # ── Public logging API ────────────────────────────────────────

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
            LogLevel.PROMPT:  "\033[90m",
        }.get(level, "")
        reset = "\033[0m"
        prefix = f"[{agent}] " if agent else ""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"{color}[{ts}][{level.value}] {prefix}{message}{reset}")

        # File logging
        self._write_to_file(level, message, job_id=job_id, agent=agent)

        if job_id:
            event = {
                "type": "debug_log",
                "level": level.value,
                "message": message,
                "agent": agent,
                "data": data,
                "ts": datetime.now().isoformat(),
            }
            delivered = self._local_push(job_id, event)
            if not delivered:
                self._redis_push(job_id, event)

    async def log_prompt(self, agent: str, model: str, prompt: str, *,
                         job_id: str = None):
        sep = "─" * 60
        print(f"\033[90m[{datetime.now().strftime('%H:%M:%S')}][PROMPT] [{agent}] → {model}\n{sep}\n{prompt}\n{sep}\033[0m")

        # File logging — only at DEBUG_ALL verbosity
        if self._should_log_to_file(LogLevel.PROMPT, job_id):
            component = _COMPONENT_MAP.get(agent, "api/api")
            logger = self._get_file_logger(component)
            job_tag = f"[job:{job_id[:8]}] " if job_id else ""
            logger.debug(f"{job_tag}[{agent}] PROMPT → {model}\n{sep}\n{prompt}\n{sep}")

    async def push_event(self, job_id: str, event_type: str,
                         agent_id, data, percent: int = 0):
        event = {
            "type": event_type,
            "agent_id": agent_id,
            "data": data,
            "percent": percent,
        }
        delivered = self._local_push(job_id, event)
        if not delivered:
            self._redis_push(job_id, event)


debug_logger = DebugLogger()   # module-level singleton
