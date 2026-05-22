# Contributing to A/MCL

Thanks for your interest in contributing! A/MCL is a small project and any kind
of contribution — bug reports, docs, tests, or code — is welcome.

By participating, you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

```bash
git clone https://github.com/ratnam1510/A-MCL.git
cd A-MCL
python -m venv .venv
source .venv/bin/activate
pip install -e ".[accurate-tokens]"
```

## Running the tests

```bash
pip install -e ".[dev]"
pytest
```

The full suite lives in [`tests/test_amcl.py`](tests/test_amcl.py).

## Code style

- Python 3.10+.
- Standard library first; only add a runtime dependency if there is no clean
  stdlib alternative.
- Follow the patterns already in `src/amcl/`. Keep modules small and focused.
- Run `ruff check src tests` before sending a patch if you have it installed.

## Reporting bugs

Open an issue at <https://github.com/ratnam1510/A-MCL/issues> with:

1. What you did (commands, agent, OS).
2. What you expected.
3. What actually happened, including the `amcl-server status` output and any
   relevant lines from `~/.amcl/amcl.log`.

## Pull requests

1. Fork the repo and create a topic branch.
2. Add or update tests for any behavior change.
3. Update `README.md` / docs if you change user-visible behavior.
4. Open the PR against `main` with a short description of the change and why.

## Security

Please do **not** open public issues for security problems. See
[SECURITY.md](SECURITY.md) for how to report them privately.
