import os
import time
import json
import pytest
import concurrent.futures
from rate_limit_guard import RateLimitGuard, format_remaining

def test_format_remaining():
    assert format_remaining(45) == "45s"
    assert format_remaining(150) == "2m 30s"
    assert format_remaining(120) == "2m"
    assert format_remaining(4500) == "1h 15m"
    assert format_remaining(3600) == "1h"

def test_rate_limit_guard_flow(tmp_path):
    state_file = tmp_path / "rate_limits.json"
    guard = RateLimitGuard(str(state_file))

    # Initial state
    assert guard.get_remaining_cooldown() is None

    # Record limit with fallback
    guard.record_limit(default_cooldown_seconds=10)
    cooldown = guard.get_remaining_cooldown()
    assert cooldown is not None
    assert 0 < cooldown <= 10

    # Clear state
    guard.clear()
    assert guard.get_remaining_cooldown() is None

def test_rate_limit_headers_parsing(tmp_path):
    state_file = tmp_path / "rate_limits.json"
    guard = RateLimitGuard(str(state_file))

    # Parse retry-after header
    headers = {"Retry-After": "15"}
    guard.record_limit(headers=headers)
    cooldown = guard.get_remaining_cooldown()
    assert cooldown is not None
    assert 10 < cooldown <= 15

def test_is_genuine_limit(tmp_path):
    state_file = tmp_path / "rate_limits.json"
    guard = RateLimitGuard(str(state_file))

    # Exhausted bucket reset time is large (>= 60s) -> Genuine
    headers_genuine = {
        "x-ratelimit-remaining-requests-1h": "0",
        "x-ratelimit-reset-requests-1h": "3600",
    }
    assert guard.is_genuine_limit(headers=headers_genuine) is True

    # Exhausted bucket reset time is small (< 60s) -> Not genuine
    headers_transient = {
        "x-ratelimit-remaining-requests": "0",
        "x-ratelimit-reset-requests": "5",
    }
    assert guard.is_genuine_limit(headers=headers_transient) is False

# --- NEW CORRUPTION AND CONCURRENCY TESTS ---
def test_corruption_resilience(tmp_path):
    state_file = tmp_path / "corrupt_limits.json"
    guard = RateLimitGuard(str(state_file))

    # 1. Empty file
    state_file.write_text("")
    assert guard.get_remaining_cooldown() is None

    # 2. Invalid JSON content
    state_file.write_text("{invalid_json: True}")
    assert guard.get_remaining_cooldown() is None

    # 3. Overwriting a corrupt file with record_limit works
    guard.record_limit(default_cooldown_seconds=30)
    cooldown = guard.get_remaining_cooldown()
    assert cooldown is not None
    assert 20 < cooldown <= 30

def test_concurrency_threads(tmp_path):
    state_file = tmp_path / "concurrent_limits.json"
    guards = [RateLimitGuard(str(state_file)) for _ in range(50)]

    def run_guard(g, idx):
        time.sleep(idx * 0.001)
        g.record_limit(default_cooldown_seconds=10 + idx)

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(run_guard, guards[i], i) for i in range(50)]
        concurrent.futures.wait(futures)

    # The file should be readable and hold a valid cooldown
    cooldown = guards[0].get_remaining_cooldown()
    assert cooldown is not None
    assert 5 < cooldown <= 60
