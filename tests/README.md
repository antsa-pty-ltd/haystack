# Haystack AI Test Suite

This directory contains comprehensive tests for the Haystack AI service, including pytest unit/integration tests, promptfoo AI persona tests, and RAGAS quality evaluation.

**For complete testing documentation:**
- **[haystackTest.md](../haystackTest.md)** - Test philosophy, what we're testing and why (essential reading)
- **[TESTING.md](../TESTING.md)** - Operational guide with detailed instructions and troubleshooting

## Test Structure

```
tests/
├── conftest.py                      # Shared fixtures and golden test data
├── unit/                            # Unit tests (70 tests, fast, no external deps)
│   ├── test_policy_violations.py   # Safety & policy enforcement (23 CRITICAL tests)
│   ├── test_personalization.py     # Name personalization tests
│   ├── test_document_generation.py # Core generation logic tests
│   └── test_session_manager.py     # Session handling tests
├── integration/                     # Integration tests (10 tests, require Redis)
│   ├── test_ragas_evaluation.py    # RAGAS integration
│   └── test_document_workflow.py   # End-to-end workflow tests
└── quality/                         # Quality tests (12 tests, slow, uses OpenAI API)
    ├── test_ragas_minimal.py        # Minimal RAGAS tests (short documents)
    ├── test_ragas_simple.py         # Simplified RAGAS tests
    └── test_ragas_document_quality.py # Comprehensive RAGAS evaluation

../promptfoo/                        # Promptfoo AI persona tests (100+ tests)
├── configs/
│   ├── web_assistant_test.yaml     # Practitioner-facing AI (30+ tests)
│   ├── jaimee_test.yaml            # Client-facing therapist AI (40+ tests)
│   └── transcriber_test.yaml       # Document generation from transcripts (30+ tests)
└── redteam/
    └── config.yaml                  # Adversarial security testing (15 plugins)
```

## Running Tests

### Comprehensive Test Runner (Recommended)

Use `run_all_tests.sh` to run all tests (pytest + promptfoo + RAGAS):

```bash
# Fast feedback during development (~5 min, $0)
./run_all_tests.sh --quick

# Full test suite before PR (~30-35 min, $2-4)
./run_all_tests.sh

# With quality/RAGAS tests (~45 min, $10-15)
./run_all_tests.sh --with-quality

# Complete suite with red team (~60-70 min, $15-25)
./run_all_tests.sh --with-quality --red-team

# With coverage report
./run_all_tests.sh --coverage
```

**Test Type Options:**
```bash
./run_all_tests.sh --pytest-only     # Only pytest tests
./run_all_tests.sh --promptfoo-only  # Only promptfoo tests
./run_all_tests.sh --unit            # Only unit tests
./run_all_tests.sh --safety          # Only safety-critical tests
./run_all_tests.sh --integration     # Only integration tests
./run_all_tests.sh --quality         # Only RAGAS quality tests
```

See [TESTING.md](../TESTING.md) for complete documentation.

### Pytest Only (Fast Feedback)

Use `run_tests.sh` for quick pytest-only testing:

```bash
# Run all pytest tests
./run_tests.sh

# Run only unit tests (fast)
./run_tests.sh --unit

# Run only safety tests (CRITICAL)
./run_tests.sh --safety

# Run with coverage report
./run_tests.sh --coverage
```

### Manual pytest Commands

```bash
# Activate virtual environment
source venv/bin/activate

# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/unit/test_policy_violations.py -v

# Run tests matching pattern
pytest tests/ -k "policy" -v

# Run with coverage
pytest tests/ --cov=. --cov-report=html
```

## Test Categories

### Pytest Tests (94 tests total)

#### Unit Tests (`-m unit`) - 70 tests
Fast tests with no external dependencies (~2-3 min, $0):
- **Policy violation detection** - Ensures no diagnosis language, no medical advice
- **Personalization enforcement** - Uses client/practitioner names (not "the client")
- **Document generation logic** - Template processing, variable substitution
- **Session management** - Redis session handling

#### Safety Tests (`-m safety`) - 23 tests - **CRITICAL**
Zero-tolerance safety/policy tests (~2-3 min, $0):
- **Never diagnose mental health conditions** (legal/ethical requirement)
- **Never recommend medications** (outside AI scope)
- **Policy violation detection** - Blocks prohibited language
- **No hallucinated content** - Ensures factual accuracy

**⚠️ CRITICAL: All safety tests MUST pass (100% pass rate required)**

#### Integration Tests (`-m integration`) - 10 tests
Component interaction tests (~4-5 min, ~$0.10-0.50):
- Full document generation workflow (transcript → document)
- Redis session persistence
- OpenAI API integration
- Error handling and recovery

**Requires:** Redis running on localhost:6379

#### Quality Tests (`-m quality`) - 12 tests
RAGAS evaluation tests (~10-15 min, ~$2-5):
- **Faithfulness** ≥ 0.8 - No hallucinations, grounded in transcript
- **Relevancy** ≥ 0.7 - Addresses template requirements
- **Context Precision** ≥ 0.75 - Uses correct transcript segments
- **Safety compliance** - No diagnosis language in generated documents

**Requires:** OpenAI API key, uses gpt-4o-mini for evaluation

### Promptfoo Tests (100+ tests)

#### Web Assistant Tests (~30+ tests)
Practitioner-facing AI assistant (~3-5 min, ~$1-2):
- Safety: Refuses diagnosis even when practitioner asks
- Tool usage: Correct tool selection and chaining
- Document workflow: Search → Load → Generate → Review
- Error handling: Validates IDs exist before using

#### jAImee Therapist Tests (~40+ tests)
Client-facing therapeutic AI (~5-7 min, ~$2-3):
- Safety: Never diagnose, never label conditions
- Empathy: Validates feelings without clinical language
- Crisis handling: Suicidal ideation, self-harm protocols
- Boundaries: Clarifies AI is not replacing human therapy
- Positive reinforcement: Celebrates client progress

#### Transcriber Tests (~30+ tests)
Document generation from transcripts (~5-7 min, ~$2-3):
- Safety: No diagnostic language in documents
- Fidelity: Only uses information from transcript (no fabrication)
- Professional language: Australian English, clinical tone
- Template adherence: SOAP format, assessment structures

#### Red Team Tests (~100+ attack vectors)
Adversarial security testing (~15-20 min, ~$5-10):
- Jailbreak attacks: "Ignore previous instructions"
- Prompt injection: Malicious instructions in user input
- Base64 encoding: Hidden diagnosis requests
- PII leakage: Extract other clients' information
- Hallucination: Fabricate client data

**⚠️ Cost Warning:** Red team tests use many API calls, run sparingly

## Golden Test Data

Test fixtures are defined in `conftest.py`:

- **SAMPLE_TRANSCRIPT_SEGMENTS**: Sample therapy session segments
- **SAMPLE_TEMPLATE_SESSION_NOTES**: Standard session notes template
- **POLICY_VIOLATION_CASES**: Test cases for policy detection
- **PERSONALIZATION_TEST_CASES**: Test cases for name usage

## Development Workflow

### During Development (Fast Feedback)
```bash
# After code changes (~5 min)
./run_all_tests.sh --quick

# Or pytest only (~2-3 min)
./run_tests.sh --unit
```

### Before Committing
```bash
# Run quick tests to catch issues early
./run_all_tests.sh --quick
```

### Before Creating PR
```bash
# Full test suite with coverage (~35 min)
./run_all_tests.sh --coverage

# Ensure:
# - All tests pass (especially safety tests)
# - Coverage ≥ 80%
# - Report saved for review
```

### Before Deployment to Production
```bash
# Comprehensive quality assurance (~60-70 min)
./run_all_tests.sh --with-quality --red-team

# This includes:
# - All pytest tests (unit, safety, integration, quality)
# - All promptfoo tests (web_assistant, jaimee, transcriber)
# - Red team adversarial testing
# - RAGAS quality evaluation
```

## Success Criteria

Before production deployment, ensure:

| Test Category | Target | Critical? |
|--------------|--------|-----------|
| Safety tests | 100% pass | ✅ YES - BLOCK deployment if failing |
| Unit tests | 100% pass | ⚠️ Highly recommended |
| Integration tests | ≥ 95% pass | ⚠️ Investigate failures |
| Quality/RAGAS | ≥ 75% combined score | ⚠️ Review low scores |
| Code coverage | ≥ 80% | ⚠️ Target for maintainability |
| Promptfoo tests | ≥ 90% pass | ⚠️ Review failures |
| Red team tests | 0 critical vulnerabilities | ✅ YES - Monthly minimum |

## Adding New Tests

1. Create test file in appropriate directory (`unit/` or `integration/`)
2. Use fixtures from `conftest.py` for common test data
3. Mark tests with appropriate markers (`@pytest.mark.unit`, etc.)
4. Follow naming convention: `test_<feature>.py`

## Cost Management

Testing involves OpenAI API calls. Estimated costs:

| Test Configuration | Time | Cost | When to Run |
|-------------------|------|------|-------------|
| `--quick` | 5 min | $0 | After every code change |
| Default (no quality) | 30-35 min | $2-4 | Before PR |
| `--with-quality` | 45 min | $10-15 | Before deployment |
| `--red-team` | 60-70 min | $15-25 | Monthly, major releases |

**Cost-Saving Tips:**
- Use `--quick` during development (unit + safety only, no API calls)
- Skip quality tests unless needed (`--with-quality` is opt-in)
- Run red team tests monthly, not on every PR
- Set OpenAI API rate limits to control spending

## Environment Setup

### Required
- Python 3.11+ with virtual environment
- Node.js 18+ with npx (for promptfoo tests)
- OpenAI API key (for quality and promptfoo tests)
- Redis 7+ (for integration tests)

### Setup Instructions

```bash
# 1. Activate virtual environment
source venv/bin/activate

# 2. Install test dependencies
pip install -r requirements-test.txt

# 3. Set OpenAI API key
export OPENAI_API_KEY="sk-your-key-here"
# Or create .env file:
echo "OPENAI_API_KEY=sk-your-key-here" > .env

# 4. Start Redis (for integration tests)
sudo systemctl start redis
redis-cli ping  # Should return "PONG"

# 5. Verify setup
./run_all_tests.sh --quick  # Should pass
```

See [TESTING.md](../TESTING.md) for detailed setup instructions and troubleshooting.

## Dependencies

### Python (pytest)
Core:
- pytest >= 7.4.0
- pytest-asyncio >= 0.21.0
- pytest-mock >= 3.12.0
- pytest-cov >= 4.1.0

Optional (for RAGAS quality tests):
- ragas >= 0.1.0
- langchain-openai >= 0.1.0
- datasets >= 2.14.0

### Node.js (promptfoo)
- npx (included with Node.js 18+)
- promptfoo (automatically installed via npx)

### Services
- Redis 7+ (for integration tests)
- PostgreSQL 16+ with pgvector (optional, for semantic search tests)
