import os
import json
import time
import tempfile
from typing import Dict, Any, Optional, Tuple, Union

class RateLimitGuard:
    MIN_RESET_FOR_BREAKER_SECONDS = 60.0

    def __init__(self, state_file_path: Optional[str] = None) -> None:
        if state_file_path:
            self.state_file_path = state_file_path
        else:
            home = os.path.expanduser("~")
            self.state_file_path = os.path.join(home, ".rate_limits", "default.json")

    def get_remaining_cooldown(self) -> Optional[float]:
        """Check if the rate limit is active.

        Returns seconds remaining until reset, or None if not rate-limited.
        """
        try:
            if not os.path.exists(self.state_file_path):
                return None
            with open(self.state_file_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            now = time.time()
            remaining = state["reset_at"] - now
            if remaining > 0:
                return remaining

            # Expired — clean up
            try:
                os.remove(self.state_file_path)
            except Exception:
                pass
            return None
        except Exception:
            return None

    def record_limit(
        self,
        headers: Optional[Dict[str, str]] = None,
        error_context: Optional[Dict[str, Any]] = None,
        default_cooldown_seconds: float = 300.0,
    ) -> None:
        """Record that the rate limit has been triggered.

        Parses reset time from headers/error context and writes atomically.
        """
        now = time.time()
        reset_at = None

        header_seconds = self._parse_reset_seconds(headers)
        if header_seconds is not None:
            reset_at = now + header_seconds

        if reset_at is None and error_context:
            ctx_reset = error_context.get("reset_at")
            if isinstance(ctx_reset, (int, float)) and ctx_reset > now:
                reset_at = ctx_reset

        if reset_at is None:
            reset_at = now + default_cooldown_seconds

        try:
            state_dir = os.path.dirname(self.state_file_path)
            if state_dir and not os.path.exists(state_dir):
                os.makedirs(state_dir, exist_ok=True)

            state = {
                "reset_at": reset_at,
                "recorded_at": now,
                "reset_seconds": reset_at - now,
            }

            # Atomic write: write to temp file then rename
            fd, tmp_path = tempfile.mkstemp(dir=state_dir or ".", suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(state, f)
                os.replace(tmp_path, self.state_file_path)
            except Exception:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                raise
        except Exception:
            pass

    def clear(self) -> None:
        """Clear the rate limit state."""
        try:
            if os.path.exists(self.state_file_path):
                os.remove(self.state_file_path)
        except Exception:
            pass

    def is_genuine_limit(
        self,
        headers: Optional[Dict[str, str]] = None,
        last_known_state: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Decide whether a 429 is a genuine account-level rate limit or transient provider jitter.

        Returns True if it represents a genuine quota limit.
        """
        buckets = self._parse_buckets_from_headers(headers)
        if self._has_exhausted_bucket(buckets):
            return True

        if last_known_state and self._has_exhausted_bucket_in_state(last_known_state):
            return True

        return False

    def _parse_reset_seconds(self, headers: Optional[Dict[str, str]]) -> Optional[float]:
        if not headers:
            return None
        lowered = {k.lower(): v for k, v in headers.items()}
        keys = [
            "x-ratelimit-reset-requests-1h",
            "x-ratelimit-reset-requests",
            "retry-after",
        ]
        for key in keys:
            val = lowered.get(key)
            if val is not None:
                try:
                    parsed = float(val)
                    if parsed > 0:
                        return parsed
                except ValueError:
                    pass
        return None

    def _parse_buckets_from_headers(
        self, headers: Optional[Dict[str, str]]
    ) -> Dict[str, Tuple[Optional[int], Optional[float]]]:
        if not headers:
            return {}
        lowered = {k.lower(): v for k, v in headers.items()}
        result = {}
        tags = ["requests", "requests-1h", "tokens", "tokens-1h"]

        for tag in tags:
            rem_val = lowered.get(f"x-ratelimit-remaining-{tag}")
            res_val = lowered.get(f"x-ratelimit-reset-{tag}")

            remaining = None
            if rem_val is not None:
                try:
                    remaining = int(rem_val)
                except ValueError:
                    pass

            reset = None
            if res_val is not None:
                try:
                    reset = float(res_val)
                except ValueError:
                    pass

            if remaining is not None or reset is not None:
                result[tag] = (remaining, reset)

        return result

    def _has_exhausted_bucket(
        self, buckets: Dict[str, Tuple[Optional[int], Optional[float]]]
    ) -> bool:
        for remaining, reset in buckets.values():
            if remaining is not None and remaining > 0:
                continue
            if reset is None:
                continue
            if reset >= self.MIN_RESET_FOR_BREAKER_SECONDS:
                return True
        return False

    def _has_exhausted_bucket_in_state(self, state: Dict[str, Any]) -> bool:
        keys = ["requests_min", "requests_hour", "tokens_min", "tokens_hour"]
        for key in keys:
            bucket = state.get(key)
            if not bucket or not isinstance(bucket, dict):
                continue
            limit = bucket.get("limit", 0)
            remaining = bucket.get("remaining", 0)
            reset = bucket.get("remaining_seconds_now")
            if reset is None:
                reset = bucket.get("reset_seconds", 0)

            if limit <= 0:
                continue
            if remaining > 0:
                continue
            if reset >= self.MIN_RESET_FOR_BREAKER_SECONDS:
                return True
        return False


def format_remaining(seconds: float) -> str:
    """Format seconds remaining into a human-readable duration string."""
    s = max(0, int(seconds))
    if s < 60:
        return f"{s}s"
    if s < 3600:
        m = s // 60
        sec = s % 60
        return f"{m}m {sec}s" if sec > 0 else f"{m}m"
    h = s // 3600
    remainder = s % 3600
    m = remainder // 60
    return f"{h}h {m}m" if m > 0 else f"{h}h"
