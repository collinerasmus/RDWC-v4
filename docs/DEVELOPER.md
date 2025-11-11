# Developer guide - RDWC-v4

## Local setup

1. Create a virtualenv and install deps

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# optional dev deps
pip install -r requirements-dev.txt || true
```

## Run tests and linters

```bash
pytest -q
black --check .
flake8
```

## Run the dev server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

## Deployment (when you have access to the Pi)

- Add repository secrets: SSH_PRIVATE_KEY, PI_HOST, PI_USER
- Use the GitHub Actions Workflow "Deploy to Raspberry Pi" (manual dispatch or on push to main).

## Branching model

- main: protected, deployable
- develop: integration
- feature/* and fix/* for work

## Code style

- Use black and flake8. Add tests for new behavior.
