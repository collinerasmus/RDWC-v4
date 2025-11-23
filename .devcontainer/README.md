# RDWC-v4 Codespaces Development Environment

This devcontainer configuration enables cloud-based development using GitHub Codespaces or VS Code Remote Containers.

## What This Provides

✅ **Full Python Development Environment**
- Python 3.11 (matches CI/CD)
- All dependencies from `requirements.txt` and `requirements-dev.txt`
- VS Code extensions: Python, Pylance, Copilot, Playwright
- Port forwarding for FastAPI server (8080)

✅ **Development Tasks You Can Do**
- Write and edit Python code
- Run pytest tests (mocked hardware)
- Review pull requests with live code context
- Use GitHub Copilot for code assistance
- Debug API endpoints (with mock hardware)
- Update documentation
- Run linters and formatters

## Limitations

❌ **Hardware Operations NOT Available**
- Cannot access Raspberry Pi GPIO pins
- Cannot communicate with I²C sensors (pH, EC, temperature)
- Cannot control relays (lights, chiller, pumps)
- Cannot perform hardware commissioning

⚠️ **For Hardware Testing:**
- Deploy to physical Raspberry Pi using `./deploy_pi.sh`
- Use commissioning scripts from `tools/` directory
- Follow [COMMISSIONING_RUNBOOK.md](../COMMISSIONING_RUNBOOK.md)

## Quick Start

### Using GitHub Codespaces

1. Go to the repository on GitHub
2. Click **Code** → **Codespaces** → **Create codespace on [branch]**
3. Wait for environment to build (~2-3 minutes first time)
4. A validation script will run automatically to verify the setup
5. Start developing!

### Using VS Code Remote Containers (Local)

1. Install [VS Code](https://code.visualstudio.com/) and [Docker Desktop](https://www.docker.com/products/docker-desktop)
2. Install the [Remote - Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) extension
3. Open this repository in VS Code
4. Click the green button in the bottom-left corner
5. Select **Reopen in Container**

## Running the API Server (Development Mode)

```bash
# In the Codespace terminal
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

The API will be available at the forwarded port URL (Codespaces will show a notification).

**Note:** The server will run with mocked hardware since GPIO and I²C are not available in a container.

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific test file
pytest tests/test_relay_system.py
```

All tests use mocked GPIO and I²C interfaces, so they work perfectly in Codespaces.

## Environment Variables

The devcontainer attempts to mount `.env` file if it exists locally. For Codespaces, you'll need to:

1. Copy `.env.example` to `.env`
2. Use mock/test values for hardware pins and I²C addresses
3. Or work without `.env` (code has sensible defaults)

## Cost and Limits

**GitHub Codespaces (Free Tier):**
- 120 core-hours per month
- 15 GB storage
- Auto-stops after 30 minutes of inactivity

**Typical Usage:**
- 2-core machine = ~60 hours of development time
- More than enough for occasional code reviews and feature work

## When to Use Codespaces vs. Local Pi

| Task | Use Codespaces | Use Raspberry Pi |
|------|----------------|------------------|
| Code review | ✅ Yes | ⚠️ Optional |
| Write new features | ✅ Yes | ⚠️ Optional |
| Run unit tests | ✅ Yes | ⚠️ Optional |
| Update docs | ✅ Yes | ⚠️ Optional |
| Debug API logic | ✅ Yes (mocked) | ✅ Yes (real) |
| Calibrate sensors | ❌ No | ✅ Required |
| Commission hardware | ❌ No | ✅ Required |
| Test GPIO/relays | ❌ No | ✅ Required |
| End-to-end validation | ❌ No | ✅ Required |

## Troubleshooting

### Dependencies fail to install
If `pip install` fails during container creation:
1. Check `requirements.txt` and `requirements-dev.txt` for version conflicts
2. Rebuild the container: Command Palette → **Rebuild Container**

### Port 8080 not forwarding
1. Check the **Ports** panel in VS Code (next to Terminal)
2. Ensure port 8080 is listed and forwarded
3. Click the globe icon to open in browser

### Tests fail with "No GPIO hardware"
This is expected in Codespaces. The tests should automatically use mocked GPIO via pytest fixtures. If they don't:
1. Check that `conftest.py` is present in the repository root
2. Ensure pytest is discovering the fixtures correctly

## Validating Your Environment

After the devcontainer is created, you can manually run the validation script:

```bash
python .devcontainer/validate.py
```

This checks:
- ✅ Configuration file is valid
- ✅ Python version is correct (3.9+)
- ✅ All dependencies are installed
- ✅ Project structure is intact

The validation script runs automatically during setup, but you can re-run it anytime.

## More Information

- **Project Documentation:** See [README.md](../README.md)
- **Architecture:** See [SYSTEM_ARCHITECTURE.md](../SYSTEM_ARCHITECTURE.md)
- **Contributing:** See [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Codespaces Docs:** https://docs.github.com/en/codespaces
