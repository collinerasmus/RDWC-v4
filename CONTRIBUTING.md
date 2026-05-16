# Contributing to RDWC-v4

Thank you for your interest in contributing to RDWC-v4! This guide will help you get started safely and effectively.

## Table of Contents
- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Safety-Critical Guidelines](#safety-critical-guidelines)
- [Code Style](#code-style)
- [Testing Requirements](#testing-requirements)
- [Submitting Changes](#submitting-changes)

---

## Code of Conduct

**Safety First:** This project controls real hardware (pumps, relays, sensors). Bugs can damage equipment or affect plant health. Always:
- Test thoroughly before submitting
- Never bypass safety guards without discussion
- Document hardware-affecting changes clearly

**Be Respectful:** Constructive feedback, clear communication, and collaborative problem-solving.

---

## Getting Started

### Prerequisites
- Python 3.9 or higher
- Git
- For hardware testing: Raspberry Pi 4 with RDWC hardware setup

### Development Environment Setup

#### 1. Fork and Clone
```bash
# Fork the repository on GitHub, then:
git clone https://github.com/YOUR_USERNAME/RDWC-v4.git
cd RDWC-v4
```

#### 2. Create Virtual Environment

**Linux/macOS/Raspberry Pi:**
```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

#### 3. Install Dependencies
```bash
# Runtime dependencies
pip install -r requirements.txt

# Development tools (testing, coverage)
pip install -r requirements-dev.txt
```

#### 4. Configure Environment
```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your Pi's IP and sensor addresses
# (Not needed for most code changes - tests use mocks)
```

---

## Development Workflow

### 1. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

**Branch naming conventions:**
- `feature/` - New functionality
- `fix/` - Bug fixes
- `docs/` - Documentation only
- `refactor/` - Code restructuring without behavior change
- `test/` - Adding or modifying tests

### 2. Make Your Changes

**Read these first:**
- `.github/copilot-instructions.md` - Architecture and conventions
- `SYSTEM_ARCHITECTURE.md` - System design
- Relevant documentation in `docs/` directory

**Key principles:**
- Keep changes focused and minimal
- One logical change per commit
- Write clear commit messages

### 3. Run Tests Frequently
```bash
# Run all tests
pytest

# Run specific test file
pytest tests/test_ph_auto_core.py

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test function
pytest tests/test_dosing_math_basic.py::test_calculate_dose_ml -v
```

**Test early and often** - Don't wait until you're "done" to test.

### 4. Update Documentation
If your change affects:
- User-facing behavior → Update README.md
- Architecture → Update SYSTEM_ARCHITECTURE.md
- Deployment → Update relevant runbook
- API → Update docstrings and API documentation

### 5. Commit Your Changes
```bash
git add <files>
git commit -m "Brief description of change

- Detailed point 1
- Detailed point 2
- Related to issue #123"
```

**Commit message guidelines:**
- First line: Brief summary (50 chars or less)
- Blank line
- Detailed explanation of what and why
- Reference related issues/PRs

---

## Safety-Critical Guidelines

### 🚨 Hardware-Affecting Changes

If your code touches **any** of these areas, extra scrutiny is required:

#### Relay Control (`app/relays_core.py`)
- **NEVER** bypass `set_relay()` or write GPIO directly
- **ALWAYS** respect cooldown timers unless absolutely necessary
- **MUST** test on real hardware before merging
- **VERIFY** active-low logic (HIGH = OFF)

**Checklist for relay changes:**
- [ ] Changes go through `relays_core.set_relay()` or specific helpers
- [ ] Cooldown guards respected
- [ ] E-STOP behavior verified
- [ ] Tested with real relays (not just mocks)
- [ ] Min ON/OFF times honored for compressor-based equipment

#### Sensor Reading (`app/sensors_core.py`, `app/ezo_i2c_stabilized.py`)
- **RESPECT** I²C locks (`/tmp/rdwc_calib.lock`)
- **AVOID** reading sensors too frequently (contention)
- **TEST** with real I²C devices when possible

**Checklist for sensor changes:**
- [ ] Honors locking mechanisms
- [ ] Handles sensor offline gracefully
- [ ] Temperature compensation throttling considered
- [ ] Tested with actual EZO sensors if available

#### Dosing Logic (`app/ph_control.py`, `app/ec_control.py`, `app/dosing.py`)
- **VERIFY** safety caps (per-dose, daily totals)
- **CHECK** guard conditions (pH/EC limits, staleness)
- **ENSURE** dosing only happens in auto mode

**Checklist for dosing changes:**
- [ ] Safety caps enforced
- [ ] Guard conditions respected
- [ ] Mode checking present
- [ ] Dose logging implemented
- [ ] Tested with commissioning scripts

#### Scheduler (`app/scheduler.py`)
- **NO** periodic catch-up loops
- **EDGE-BASED** only (exactly 2 transitions per day)
- **VERIFY** midnight boundary handling

---

## Code Style

### Python Conventions

**Follow existing patterns in the codebase:**
- **Indentation:** 4 spaces (no tabs)
- **Line length:** ~100 characters (soft limit)
- **Naming:**
  - Functions/variables: `snake_case`
  - Classes: `PascalCase`
  - Constants: `UPPER_SNAKE_CASE`
- **Docstrings:** Use for public functions, especially complex logic
- **Type hints:** Encouraged for new code

**Example:**
```python
def calculate_dose_ml(
    current_value: float,
    target_value: float,
    volume_liters: float,
    correction_factor: float = 1.0
) -> float:
    """
    Calculate dosing amount in milliliters.
    
    Args:
        current_value: Current pH/EC reading
        target_value: Desired pH/EC value
        volume_liters: System volume in liters
        correction_factor: Optional adjustment factor
    
    Returns:
        Dose amount in milliliters
    """
    delta = target_value - current_value
    return delta * volume_liters * correction_factor
```

### Comments

**When to comment:**
- Non-obvious safety guards
- Hardware-specific behavior (e.g., active-low relays)
- Complex algorithms
- Workarounds for hardware limitations

**When NOT to comment:**
- Obvious code (e.g., `# increment counter`)
- Replacing good variable names
- Outdated comments that don't match code

**Good:**
```python
# Active-low relay: HIGH = OFF, LOW = ON
GPIO.output(relay_pin, GPIO.HIGH)  # Turn relay OFF
```

**Bad:**
```python
# Set pin to high
GPIO.output(relay_pin, GPIO.HIGH)
```

---

## Testing Requirements

### Test Coverage Expectations

**For new features:**
- Minimum 80% code coverage for new code
- Unit tests for business logic
- Integration tests for multi-component features
- Hardware mocks for GPIO/I²C

**For bug fixes:**
- Regression test that catches the bug
- Verify fix doesn't break existing behavior

### Test Types

#### 1. Unit Tests
Test individual functions in isolation:
```python
# tests/test_dosing_math.py
def test_calculate_dose_ml():
    result = calculate_dose_ml(
        current_value=5.8,
        target_value=6.0,
        volume_liters=25.0,
        correction_factor=1.0
    )
    assert result == 5.0  # (6.0 - 5.8) * 25 * 1.0
```

#### 2. Integration Tests
Test multiple components working together:
```python
# tests/test_ph_auto_core.py
def test_auto_dose_ph_up(test_client, mock_sensors):
    # Set up: pH too low, auto mode
    set_mode("ph", "auto")
    mock_sensors.ph = 5.5
    
    # Execute: Trigger auto-dose
    response = test_client.post("/api/ph/auto_dose")
    
    # Verify: Dose logged, relay activated
    assert response.status_code == 200
    assert dose_logged_in_db()
    assert relay_was_activated("ph_up_pump")
```

#### 3. End-to-End Tests
Test full user workflows:
```python
# tests/test_commissioning_sim.py
def test_full_commissioning_flow(test_client):
    # Simulate full commissioning sequence
    # 1. Check sensor status
    # 2. Calibrate pH (mid, low, high)
    # 3. Verify calibration
    # 4. Test relay control
    # 5. Verify settings
```

### Running Tests

```bash
# Fast tests only (unit tests)
pytest -m "not slow"

# All tests including slow integration tests
pytest

# With coverage report
pytest --cov=app --cov-report=html
open htmlcov/index.html  # View coverage

# Specific test
pytest tests/test_ph_auto_core.py::test_auto_dose_ph_up -v -s
```

### Mocking Hardware

**GPIO Mocking:**
Tests automatically mock GPIO when not on Raspberry Pi. No special setup needed.

**Sensor Mocking:**
```python
@pytest.fixture
def mock_sensors(monkeypatch):
    """Mock sensor readings"""
    def fake_read_sensors():
        return {
            "temperature_c": 20.5,
            "ph": 6.0,
            "ec_mscm": 1400,
            "online": True
        }
    monkeypatch.setattr("app.sensors_core.read_all_sensors", fake_read_sensors)
    return fake_read_sensors
```

---

## Submitting Changes

### Before You Submit

**Pre-submission checklist:**
- [ ] All tests pass (`pytest`)
- [ ] Code coverage is acceptable (`pytest --cov=app`)
- [ ] No new security warnings (CodeQL will check on PR)
- [ ] Documentation updated if needed
- [ ] Commit messages are clear
- [ ] Changes are focused on one logical unit

### Pull Request Process

#### 1. Push Your Branch
```bash
git push origin feature/your-feature-name
```

#### 2. Create Pull Request
- Go to GitHub repository
- Click "Pull requests" → "New pull request"
- Select your branch
- Fill out PR template (if available)

#### 3. PR Description Template
```markdown
## Summary
Brief description of what this PR does.

## Motivation
Why is this change needed? What problem does it solve?

## Changes
- Detailed change 1
- Detailed change 2
- Related change 3

## Testing
- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Tested on real hardware (if hardware-affecting)
- [ ] Manual testing performed (describe what you tested)

## Related Issues
Closes #123
Related to #456

## Screenshots (if UI change)
[Add screenshots here]

## Safety Review (if hardware-affecting)
- [ ] No direct GPIO access
- [ ] Cooldowns respected
- [ ] E-STOP behavior verified
- [ ] Tested on real Pi/hardware
```

#### 4. Respond to Review Feedback
- Address comments promptly
- Ask questions if feedback is unclear
- Push additional commits to same branch (will update PR)
- Mark conversations as resolved when addressed

#### 5. Merge
- Wait for CI checks to pass
- Wait for required approvals
- Squash and merge (for clean history) or regular merge

---

## Common Contribution Scenarios

### Scenario 1: Fixing a Bug

1. **Reproduce the bug** - Understand the issue
2. **Write a failing test** - Proves the bug exists
3. **Fix the bug** - Minimal code change
4. **Verify test passes** - Bug is fixed
5. **Check for side effects** - Run full test suite
6. **Submit PR** - Reference issue number

### Scenario 2: Adding a Feature

1. **Open an issue** - Discuss feature first (avoid wasted work)
2. **Get approval** - Ensure feature aligns with project goals
3. **Design** - Think through architecture impact
4. **Implement** - Write code + tests together
5. **Document** - Update README, docstrings, guides
6. **Submit PR** - With clear description and examples

### Scenario 3: Improving Documentation

1. **Identify gap** - What's missing or unclear?
2. **Make changes** - Fix typos, add examples, clarify
3. **Submit PR** - Documentation-only PRs are welcome!
4. **No tests needed** - Unless documenting new features

---

## Getting Help

### Resources
- **README.md** - Quick start and overview
- **SYSTEM_ARCHITECTURE.md** - System design and data flows
- **.github/copilot-instructions.md** - AI agent context (helpful for humans too!)
- **PROJECT_MANAGEMENT.md** - Organization and best practices
- **docs/** directory - Detailed guides

### Ask Questions
- **Issues tab** - Open a question issue (we'll add template)
- **Pull request** - Ask in PR comments during review
- **Discussions** - (If enabled) General questions and ideas

### Common Issues
- **"Import error"** → Activate virtual environment, reinstall dependencies
- **"GPIO not found"** → Normal on non-Pi; tests use mocks
- **"Port 8080 in use"** → Kill existing process or use different port
- **"Tests failing"** → Run `pytest -v` to see details, check conftest.py fixtures

---

## Recognition

Contributors will be:
- Listed in CHANGELOG.md for significant contributions
- Credited in commit history
- Acknowledged in project documentation

---

## License

By contributing, you agree that your contributions will be licensed under the same license as the project (see LICENSE file).

---

## Thank You!

Your contributions help make RDWC-v4 better for everyone. Whether it's fixing a typo, adding a feature, or improving documentation - all contributions are valuable. 🎉

**Questions about this guide?** Open an issue and we'll clarify!
