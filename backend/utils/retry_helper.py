import asyncio
import random
import time
from anthropic import InternalServerError, RateLimitError
from utils.debug_logger import LogLevel, debug_logger


async def call_with_retry(fn, *, job_id: str = None, agent_name: str = None,
                          max_attempts: int = 5):
    """Wraps a blocking Anthropic SDK call with exponential backoff on 429."""
    for attempt in range(1, max_attempts + 1):
        try:
            t0 = time.monotonic()
            response = await asyncio.to_thread(fn)
            duration = time.monotonic() - t0

            # Log timing + token usage
            usage = getattr(response, "usage", None)
            if usage:
                input_tok  = getattr(usage, "input_tokens", "?")
                output_tok = getattr(usage, "output_tokens", "?")
                total_tok  = (input_tok + output_tok
                              if isinstance(input_tok, int) and isinstance(output_tok, int)
                              else "?")
                token_str = (
                    f"  tokens: {input_tok} in / {output_tok} out / {total_tok} total"
                )
            else:
                token_str = ""

            model_str = getattr(response, "model", "")
            await debug_logger.log(
                LogLevel.API,
                f"← {agent_name or 'agent'} fertig  {duration:.1f}s  model={model_str}{token_str}",
                job_id=job_id, agent=agent_name,
            )

            # Log response text — terminal only (no job_id → not pushed to SSE queue)
            content = getattr(response, "content", None)
            if content:
                text = getattr(content[0], "text", "") if content else ""
                preview = text[:2000] + (" …[gekürzt]" if len(text) > 2000 else "")
                await debug_logger.log(
                    LogLevel.DEBUG,
                    f"← Antwort:\n{preview}",
                    agent=agent_name,
                )

            return response

        except (RateLimitError, InternalServerError) as exc:
            if attempt == max_attempts:
                raise
            delay = 2 ** (attempt - 1) + random.random()
            label = "Rate limit" if isinstance(exc, RateLimitError) else "Überlastet (529)"
            await debug_logger.log(
                LogLevel.WARNING,
                f"{label} (attempt {attempt}/{max_attempts}) — retry in {delay:.1f}s",
                job_id=job_id, agent=agent_name,
            )
            await asyncio.sleep(delay)
        except Exception as exc:
            await debug_logger.log(
                LogLevel.ERROR,
                f"Exception in {agent_name or 'agent'} (attempt {attempt}/{max_attempts}): {type(exc).__name__}: {exc}",
                job_id=job_id, agent=agent_name,
            )
            raise
