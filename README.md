# rate-limit-guard

Cross-session and cross-process API rate limit guard for AI agents.

## Usage

```python
from rate_limit_guard import RateLimitGuard

guard = RateLimitGuard()
cooldown = guard.get_remaining_cooldown()
if cooldown:
    print(f"Rate limited! Wait {cooldown}s")
```
