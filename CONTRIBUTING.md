# Contributing

Thanks for considering a contribution.

## Quick start

```sh
git clone https://github.com/p-vbordei/rate-limit-guard-py.git
cd rate-limit-guard-py
uv sync
uv run --with pytest --with pytest-asyncio pytest
```

## Workflow

1. Open an issue first for non-trivial changes.
2. Fork, branch from `main`, make changes.
3. Run tests locally before pushing.
4. Open a PR with a clear description.

## Code style

- Tests live in `tests/` next to source in `src/`.
- Prefer small focused PRs over big ones.
- Tests should be deterministic.

## License

By contributing you agree your contribution will be licensed under the project's existing license (Apache-2.0).
