# Haystack AI Testing Pipeline

## What This Is

A comprehensive CI/CD testing pipeline for the Haystack AI service (FastAPI-based mental health platform AI) that enables local testing before GitHub Actions deployment. The pipeline uses a 4-tier testing strategy with Docker-based test environments, ensuring reliable testing of AI function calling, tool workflows, and document generation while maintaining cost efficiency through conditional test execution.

## Core Value

Catch AI and integration bugs early before production deployment, with 80% pass rate thresholds for non-deterministic AI tests and 100% for integration tests, while keeping testing costs under $30 per full pipeline run.

## Requirements

### Validated

(None yet — this is a new testing infrastructure)

### Active

#### Infrastructure & Environment
- [ ] **ENV-01**: Docker Compose setup with PostgreSQL (test_antsa_db) and Redis (test instance)
- [ ] **ENV-02**: Test database seeding scripts with minimal test data (3 clients, 5 sessions, sample transcripts)
- [ ] **ENV-03**: Environment variable management for test configurations (.env.test)
- [ ] **ENV-04**: Test database reset/cleanup scripts between runs

#### Tier 1: Unit Tests (Fast Feedback, $0)
- [ ] **UNIT-01**: Mock fixtures for OpenAI API responses (function calling patterns)
- [ ] **UNIT-02**: Mock fixtures for NestJS API endpoints (client search, session retrieval)
- [ ] **UNIT-03**: FakeRedis or mock Redis for session/state management tests
- [ ] **UNIT-04**: Unit tests for 41 tool implementations (mocked external calls)
- [ ] **UNIT-05**: Unit tests for persona configurations and prompt validation
- [ ] **UNIT-06**: Unit tests for session manager logic
- [ ] **UNIT-07**: Unit tests for UI state manager logic
- [ ] **UNIT-08**: Unit tests for policy violation detection (mocked LLM)
- [ ] **UNIT-09**: Unit tests for message formatting and parsing utilities

#### Tier 2: Component Integration Tests (Real AI, ~$5)
- [ ] **INT-01**: FastAPI endpoint tests using TestClient (health, sessions, chat)
- [ ] **INT-02**: WebSocket streaming tests (connection, message flow, disconnection)
- [ ] **INT-03**: Haystack pipeline tests with REAL OpenAI (function calling intelligence)
- [ ] **INT-04**: Tool calling accuracy tests (AI chooses correct tools)
- [ ] **INT-05**: Tool chaining workflow tests (multi-step operations)
- [ ] **INT-06**: Persona switching tests (web_assistant, jaimee_therapist, transcriber_agent)
- [ ] **INT-07**: Multi-turn conversation history tests
- [ ] **INT-08**: Session persistence tests with real Redis
- [ ] **INT-09**: Mock NestJS API responses fixture library

#### Tier 3: End-to-End Integration Tests (Real Everything, ~$10)
- [ ] **E2E-01**: Document generation complete workflow (agentic exploration)
- [ ] **E2E-02**: Full tool workflow tests (search → load → generate)
- [ ] **E2E-03**: Policy violation detection with real LLM evaluation
- [ ] **E2E-04**: Session recovery and reconnection tests
- [ ] **E2E-05**: UI state synchronization across WebSocket
- [ ] **E2E-06**: Error handling and edge case scenarios
- [ ] **E2E-07**: Real NestJS API integration with test database
- [ ] **E2E-08**: Tool execution with real backend responses

#### Tier 4: Quality Evaluation Tests (AI Quality, ~$15)
- [ ] **QUAL-01**: RAGAS faithfulness metrics (>= 0.80 threshold)
- [ ] **QUAL-02**: RAGAS answer relevance metrics (>= 0.75 threshold)
- [ ] **QUAL-03**: RAGAS context precision metrics (>= 0.70 threshold)
- [ ] **QUAL-04**: promptfoo persona quality tests integration
- [ ] **QUAL-05**: Document completeness scoring (>= 0.80 threshold)
- [ ] **QUAL-06**: Tool selection accuracy measurement (>= 0.85 threshold)
- [ ] **QUAL-07**: Quality threshold validation script (80% overall pass rate)

#### Local Testing Scripts
- [ ] **LOCAL-01**: Docker environment startup script (start-test-env.sh)
- [ ] **LOCAL-02**: Docker environment cleanup script (stop-test-env.sh)
- [ ] **LOCAL-03**: Local CI simulation script (run-tests-local.sh)
- [ ] **LOCAL-04**: Test result verification script (verify-test-results.sh)
- [ ] **LOCAL-05**: Cost tracking utility (estimate test run costs)
- [ ] **LOCAL-06**: Quick feedback script (Tier 1 only, < 5 min)
- [ ] **LOCAL-07**: Pre-commit hook integration (optional Tier 1 auto-run)

#### CI/CD Integration
- [ ] **CI-01**: GitHub Actions workflow for Tier 1 (unit tests, every push)
- [ ] **CI-02**: GitHub Actions workflow for Tier 2 (component integration, PRs)
- [ ] **CI-03**: GitHub Actions workflow for Tier 3 (E2E, PRs)
- [ ] **CI-04**: GitHub Actions workflow for Tier 4 (quality, on-demand/labeled PRs)
- [ ] **CI-05**: GitHub Actions service containers (PostgreSQL, Redis)
- [ ] **CI-06**: Secret management for OpenAI API keys
- [ ] **CI-07**: Test result reporting and artifacts upload
- [ ] **CI-08**: Quality gate enforcement (fail build on threshold violations)

#### Documentation
- [ ] **DOC-01**: Setup guide (Docker installation, environment setup)
- [ ] **DOC-02**: Local testing workflow documentation
- [ ] **DOC-03**: CI/CD pipeline explanation
- [ ] **DOC-04**: Test organization and structure guide
- [ ] **DOC-05**: Cost optimization strategies documentation
- [ ] **DOC-06**: Troubleshooting guide for common test failures
- [ ] **DOC-07**: Mock fixture usage examples

### Out of Scope

- **Docker installation automation** — Users install Docker manually (well-documented process)
- **Testing web portal integration** — This pipeline focuses on Haystack service only
- **Mobile app testing** — Separate testing strategy required
- **Production monitoring/observability** — Different concern from CI/CD testing
- **Performance/load testing** — Focus is functional correctness, not performance benchmarks
- **Security penetration testing** — Covered by existing promptfoo red team tests
- **Manual testing procedures** — Pipeline is fully automated

## Context

### Technical Environment
- **Language:** Python 3.11+
- **Framework:** FastAPI with WebSocket support
- **AI Framework:** Haystack (declarative pipelines with agents)
- **LLM Provider:** OpenAI (gpt-5.2, gpt-4o-mini)
- **State Management:** Redis (sessions + UI state)
- **External Dependencies:** NestJS API (PostgreSQL + PGVector)
- **Existing Tests:** pytest (70 tests), RAGAS (12 tests), promptfoo (100+ tests)

### Current State
- Haystack service is in production
- Existing tests run manually via `run_all_tests.sh`
- No CI/CD pipeline currently
- Tests use real OpenAI API (not mocked)
- Test database not set up yet
- Docker not currently used for testing

### Key Challenges
1. **AI Non-Determinism:** OpenAI responses vary, requiring threshold-based pass rates
2. **Complex Function Calling:** 41 tools with intelligent chaining make mocking difficult
3. **Cost Management:** Real OpenAI API calls expensive; need strategic tier execution
4. **Multi-Service Architecture:** Haystack depends on NestJS API + PostgreSQL + Redis
5. **Test Isolation:** Need clean state between test runs to avoid flakiness

### Design Decisions from Research
- **Use Real OpenAI in Tier 2:** Function calling with 41 tools too complex to mock reliably
- **Docker for Test Environment:** Better isolation and CI/CD consistency than local DBs
- **4-Tier Strategy:** Balance between speed, cost, and confidence
- **Mock NestJS in Tier 2:** Controlled test data without full backend dependency
- **80% Threshold for AI Tests:** Industry standard for non-deterministic LLM tests

## Constraints

- **Cost:** Test pipeline should cost < $30 per full run (all 4 tiers)
- **Time:** Full pipeline should complete in < 60 minutes
- **Platform:** Must work on Linux (Ubuntu/Debian) - user's current environment
- **Compatibility:** Must support existing test structure (pytest, RAGAS, promptfoo)
- **Dependencies:** Minimize new dependencies; use established testing tools
- **Docker:** Required for test environment (installation guide provided)
- **OpenAI API:** Tests require valid API key; cost monitoring essential
- **Local-First:** Must be testable locally before CI/CD deployment

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Docker for test env | Better isolation, CI/CD consistency, team-ready setup | — Pending |
| Real OpenAI in Tier 2 | 41 tools + function calling too complex to mock; $5/run worth the confidence | — Pending |
| 4-tier test strategy | Balance speed (Tier 1: 5min), confidence (Tier 3: E2E), quality (Tier 4: RAGAS) | — Pending |
| Mock NestJS in Tier 2 | Avoid full backend dependency; controlled test data; faster execution | — Pending |
| 80% pass threshold for AI | Industry standard for LLM tests; accounts for non-determinism | — Pending |
| Local testing first | User wants to validate pipeline locally before GitHub Actions | — Pending |
| Keep existing tests | Reorganize into 4 tiers but preserve all existing test files | — Pending |

---
*Last updated: 2026-01-29 after initialization*
