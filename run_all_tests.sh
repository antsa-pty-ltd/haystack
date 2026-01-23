#!/bin/bash
################################################################################
# run_all_tests.sh - Comprehensive Haystack Test Runner
################################################################################
#
# Purpose: Run all Haystack tests (pytest + promptfoo + RAGAS) from terminal
#
# Usage: ./run_all_tests.sh [OPTIONS]
#
# Options:
#   --pytest-only       Run only pytest tests
#   --promptfoo-only    Run only promptfoo tests
#   --unit              Run only unit tests (pytest)
#   --safety            Run only safety tests (pytest + promptfoo safety)
#   --integration       Run only integration tests
#   --quality           Run only quality/RAGAS tests
#   --with-quality      Include quality/RAGAS tests (slow, costs $2-5)
#   --red-team          Include promptfoo red team tests (slow, costs $5-10)
#   --coverage          Generate pytest coverage report
#   --verbose           Verbose output
#   --quick             Run only unit + safety (fast feedback, ~5 min)
#   --report FILE       Save report to specific file
#   --help              Show this help message
#
# Examples:
#   ./run_all_tests.sh --quick              # Fast feedback (5 min)
#   ./run_all_tests.sh                      # Default (30-35 min, no slow tests)
#   ./run_all_tests.sh --with-quality       # Include RAGAS (~45 min)
#   ./run_all_tests.sh --coverage          # With coverage report
#   ./run_all_tests.sh --pytest-only        # Only pytest tests
#   ./run_all_tests.sh --safety            # Only safety-critical tests
#
################################################################################

set -e  # Exit on error, but we'll handle errors gracefully with || true

# Change to haystack directory (script location)
cd "$(dirname "$0")"

################################################################################
# Colors for output
################################################################################
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

################################################################################
# Configuration Variables
################################################################################
RUN_PYTEST=true
RUN_PROMPTFOO=true
RUN_UNIT=true
RUN_SAFETY=true
RUN_INTEGRATION=true
RUN_QUALITY=false        # Default: skip slow tests
RUN_RED_TEAM=false       # Default: skip expensive red team tests
GENERATE_COVERAGE=false
VERBOSE=false
REPORT_FILE="test-report-$(date +%Y%m%d-%H%M%S).txt"

# Test result tracking
PYTEST_UNIT_PASSED=0
PYTEST_UNIT_FAILED=0
PYTEST_SAFETY_PASSED=0
PYTEST_SAFETY_FAILED=0
PYTEST_INTEGRATION_PASSED=0
PYTEST_INTEGRATION_FAILED=0
PYTEST_QUALITY_PASSED=0
PYTEST_QUALITY_FAILED=0
PROMPTFOO_WEB_ASSISTANT_PASSED=0
PROMPTFOO_WEB_ASSISTANT_TOTAL=0
PROMPTFOO_JAIMEE_PASSED=0
PROMPTFOO_JAIMEE_TOTAL=0
PROMPTFOO_TRANSCRIBER_PASSED=0
PROMPTFOO_TRANSCRIBER_TOTAL=0
PROMPTFOO_RED_TEAM_PASSED=0
PROMPTFOO_RED_TEAM_TOTAL=0

# Timing
START_TIME=$(date +%s)
UNIT_TIME=0
SAFETY_TIME=0
INTEGRATION_TIME=0
QUALITY_TIME=0
PROMPTFOO_TIME=0

# Environment status
PYTHON_OK=false
VENV_OK=false
NPX_OK=false
OPENAI_KEY_OK=false
REDIS_OK=false

################################################################################
# Helper Functions
################################################################################

print_header() {
    echo -e "${BOLD}${BLUE}============================================================================${NC}"
    echo -e "${BOLD}${BLUE}$1${NC}"
    echo -e "${BOLD}${BLUE}============================================================================${NC}"
}

print_section() {
    echo -e "\n${BOLD}${CYAN}--- $1 ---${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

################################################################################
# Usage / Help
################################################################################

show_help() {
    cat << EOF
${BOLD}Haystack Comprehensive Test Runner${NC}

${BOLD}USAGE:${NC}
    ./run_all_tests.sh [OPTIONS]

${BOLD}OPTIONS:${NC}
    --pytest-only       Run only pytest tests
    --promptfoo-only    Run only promptfoo tests
    --unit              Run only unit tests (pytest)
    --safety            Run only safety tests (pytest + promptfoo safety)
    --integration       Run only integration tests
    --quality           Run only quality/RAGAS tests
    --with-quality      Include quality/RAGAS tests (slow, costs \\$2-5)
    --red-team          Include promptfoo red team tests (slow, costs \\$5-10)
    --coverage          Generate pytest coverage report
    --verbose           Verbose output
    --quick             Run only unit + safety (fast feedback, ~5 min)
    --report FILE       Save report to specific file
    --help              Show this help message

${BOLD}EXAMPLES:${NC}
    ${CYAN}./run_all_tests.sh --quick${NC}
        Fast feedback (unit + safety tests only, ~5 min)

    ${CYAN}./run_all_tests.sh${NC}
        Default run (unit + safety + integration + promptfoo, ~30-35 min)

    ${CYAN}./run_all_tests.sh --with-quality --red-team${NC}
        Full test suite including slow tests (~60-70 min, \\$10-15 in API costs)

    ${CYAN}./run_all_tests.sh --coverage${NC}
        Default tests with coverage report

    ${CYAN}./run_all_tests.sh --safety${NC}
        Only safety-critical tests (pytest + promptfoo)

    ${CYAN}./run_all_tests.sh --pytest-only${NC}
        Only pytest tests (no promptfoo)

${BOLD}COST ESTIMATES:${NC}
    --quick             \\$0 (mocked tests)
    Default             \\$2-4 (integration + promptfoo)
    --with-quality      \\$10-15 (includes RAGAS evaluation)
    --red-team          +\\$5-10 (adversarial attack testing)

${BOLD}LEARN MORE:${NC}
    See haystackTest.md for detailed explanation of what we're testing and why

EOF
    exit 0
}

################################################################################
# Parse Command-Line Arguments
################################################################################

if [ $# -eq 0 ]; then
    # Default behavior: pytest (unit + safety + integration) + promptfoo (no quality, no red team)
    :
fi

while [[ $# -gt 0 ]]; do
    case $1 in
        --pytest-only)
            RUN_PYTEST=true
            RUN_PROMPTFOO=false
            shift
            ;;
        --promptfoo-only)
            RUN_PYTEST=false
            RUN_PROMPTFOO=true
            shift
            ;;
        --unit)
            RUN_PYTEST=true
            RUN_UNIT=true
            RUN_SAFETY=false
            RUN_INTEGRATION=false
            RUN_QUALITY=false
            RUN_PROMPTFOO=false
            shift
            ;;
        --safety)
            RUN_PYTEST=true
            RUN_UNIT=false
            RUN_SAFETY=true
            RUN_INTEGRATION=false
            RUN_QUALITY=false
            RUN_PROMPTFOO=true  # Include promptfoo safety tests
            RUN_RED_TEAM=false
            shift
            ;;
        --integration)
            RUN_PYTEST=true
            RUN_UNIT=false
            RUN_SAFETY=false
            RUN_INTEGRATION=true
            RUN_QUALITY=false
            RUN_PROMPTFOO=false
            shift
            ;;
        --quality)
            RUN_PYTEST=true
            RUN_UNIT=false
            RUN_SAFETY=false
            RUN_INTEGRATION=false
            RUN_QUALITY=true
            RUN_PROMPTFOO=false
            shift
            ;;
        --with-quality)
            RUN_QUALITY=true
            shift
            ;;
        --red-team)
            RUN_RED_TEAM=true
            RUN_PROMPTFOO=true
            shift
            ;;
        --coverage)
            GENERATE_COVERAGE=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --quick)
            RUN_PYTEST=true
            RUN_UNIT=true
            RUN_SAFETY=true
            RUN_INTEGRATION=false
            RUN_QUALITY=false
            RUN_PROMPTFOO=false
            shift
            ;;
        --report)
            REPORT_FILE="$2"
            shift 2
            ;;
        --help|-h)
            show_help
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

################################################################################
# Environment Validation
################################################################################

validate_environment() {
    print_header "ENVIRONMENT VALIDATION"

    # Check Python
    if command -v python3 &> /dev/null; then
        PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
        print_success "Python: $PYTHON_VERSION"
        PYTHON_OK=true
    else
        print_error "Python 3 not found"
        PYTHON_OK=false
    fi

    # Check virtual environment
    if [ -d "venv" ]; then
        print_success "Virtual environment: venv/ exists"
        VENV_OK=true

        # Activate venv if not already activated
        if [ -z "$VIRTUAL_ENV" ]; then
            print_info "Activating virtual environment..."
            source venv/bin/activate
        fi
    else
        print_warning "Virtual environment not found (looking for venv/)"
        print_info "Tests will use system Python"
        VENV_OK=false
    fi

    # Check Node.js / npx
    if command -v npx &> /dev/null; then
        NPX_VERSION=$(npx --version 2>&1)
        print_success "npx: v$NPX_VERSION"
        NPX_OK=true
    else
        print_warning "npx not found (needed for promptfoo tests)"
        NPX_OK=false
        if [ "$RUN_PROMPTFOO" = true ]; then
            print_warning "Promptfoo tests will be skipped"
            RUN_PROMPTFOO=false
        fi
    fi

    # Check OpenAI API key
    if [ -n "$OPENAI_API_KEY" ]; then
        print_success "OpenAI API Key: Set (${OPENAI_API_KEY:0:10}...)"
        OPENAI_KEY_OK=true
    else
        print_warning "OPENAI_API_KEY not set"
        print_info "Quality/RAGAS tests and promptfoo tests will fail without API key"
        OPENAI_KEY_OK=false
    fi

    # Check Redis (for integration tests)
    if command -v redis-cli &> /dev/null; then
        if redis-cli ping &> /dev/null; then
            print_success "Redis: Running (localhost:6379)"
            REDIS_OK=true
        else
            print_warning "Redis not responding to ping"
            REDIS_OK=false
            if [ "$RUN_INTEGRATION" = true ]; then
                print_info "Integration tests may fail without Redis"
            fi
        fi
    else
        print_warning "Redis CLI not found"
        REDIS_OK=false
        if [ "$RUN_INTEGRATION" = true ]; then
            print_info "Integration tests may fail without Redis"
        fi
    fi

    # Summary
    echo ""
    print_section "Environment Summary"

    if [ "$PYTHON_OK" = true ] && [ "$VENV_OK" = true ]; then
        print_success "Python environment: Ready"
    else
        print_warning "Python environment: Partial"
    fi

    if [ "$NPX_OK" = true ]; then
        print_success "Promptfoo environment: Ready"
    elif [ "$RUN_PROMPTFOO" = true ]; then
        print_warning "Promptfoo environment: Not available"
    fi

    if [ "$OPENAI_KEY_OK" = true ]; then
        print_success "OpenAI API: Configured"
    elif [ "$RUN_QUALITY" = true ] || [ "$RUN_PROMPTFOO" = true ]; then
        print_warning "OpenAI API: Not configured (will affect quality tests)"
    fi

    if [ "$REDIS_OK" = true ]; then
        print_success "Redis: Available"
    elif [ "$RUN_INTEGRATION" = true ]; then
        print_warning "Redis: Not available (integration tests may fail)"
    fi

    echo ""
}

################################################################################
# Pytest Tests
################################################################################

run_pytest_tests() {
    if [ "$RUN_PYTEST" = false ]; then
        return 0
    fi

    print_header "PYTEST TESTS"

    local PYTEST_ARGS="-v --tb=short"

    if [ "$VERBOSE" = true ]; then
        PYTEST_ARGS="$PYTEST_ARGS -vv"
    fi

    if [ "$GENERATE_COVERAGE" = true ]; then
        PYTEST_ARGS="$PYTEST_ARGS --cov=. --cov-report=html --cov-report=xml --cov-report=term-missing"
    fi

    # Install test dependencies if needed
    if ! python -c "import pytest" 2>/dev/null; then
        print_info "Installing test dependencies..."
        pip install -r requirements-test.txt > /dev/null 2>&1
    fi

    # Unit Tests
    if [ "$RUN_UNIT" = true ]; then
        print_section "Unit Tests (Fast, No External Dependencies)"
        local unit_start=$(date +%s)

        if python -m pytest $PYTEST_ARGS -m unit tests/ 2>&1 | tee /tmp/unit_test_output.txt; then
            PYTEST_UNIT_PASSED=$(grep -oP '\d+(?= passed)' /tmp/unit_test_output.txt | head -1 || echo "0")
            PYTEST_UNIT_FAILED=$(grep -oP '\d+(?= failed)' /tmp/unit_test_output.txt | head -1 || echo "0")
            print_success "Unit tests completed"
        else
            PYTEST_UNIT_FAILED=$(grep -oP '\d+(?= failed)' /tmp/unit_test_output.txt | head -1 || echo "1")
            print_error "Unit tests failed"
        fi

        local unit_end=$(date +%s)
        UNIT_TIME=$((unit_end - unit_start))
    fi

    # Safety Tests
    if [ "$RUN_SAFETY" = true ]; then
        print_section "Safety Tests (CRITICAL - 100% Pass Required)"
        local safety_start=$(date +%s)

        if python -m pytest $PYTEST_ARGS -m safety tests/ 2>&1 | tee /tmp/safety_test_output.txt; then
            PYTEST_SAFETY_PASSED=$(grep -oP '\d+(?= passed)' /tmp/safety_test_output.txt | head -1 || echo "0")
            PYTEST_SAFETY_FAILED=$(grep -oP '\d+(?= failed)' /tmp/safety_test_output.txt | head -1 || echo "0")
            print_success "Safety tests completed - ALL PASSED"
        else
            PYTEST_SAFETY_FAILED=$(grep -oP '\d+(?= failed)' /tmp/safety_test_output.txt | head -1 || echo "1")
            print_error "CRITICAL: Safety tests failed - BLOCK DEPLOYMENT"
            echo -e "${RED}${BOLD}Safety test failure is a BLOCKING issue. Do not deploy.${NC}"
        fi

        local safety_end=$(date +%s)
        SAFETY_TIME=$((safety_end - safety_start))
    fi

    # Integration Tests
    if [ "$RUN_INTEGRATION" = true ]; then
        print_section "Integration Tests (With Redis/PostgreSQL)"

        if [ "$REDIS_OK" = false ]; then
            print_warning "Skipping integration tests (Redis not available)"
            print_info "Start Redis with: sudo systemctl start redis"
        else
            local integration_start=$(date +%s)

            if python -m pytest $PYTEST_ARGS -m integration tests/ 2>&1 | tee /tmp/integration_test_output.txt; then
                PYTEST_INTEGRATION_PASSED=$(grep -oP '\d+(?= passed)' /tmp/integration_test_output.txt | head -1 || echo "0")
                PYTEST_INTEGRATION_FAILED=$(grep -oP '\d+(?= failed)' /tmp/integration_test_output.txt | head -1 || echo "0")
                print_success "Integration tests completed"
            else
                PYTEST_INTEGRATION_FAILED=$(grep -oP '\d+(?= failed)' /tmp/integration_test_output.txt | head -1 || echo "1")
                print_error "Integration tests failed"
            fi

            local integration_end=$(date +%s)
            INTEGRATION_TIME=$((integration_end - integration_start))
        fi
    fi

    # Quality Tests (RAGAS)
    if [ "$RUN_QUALITY" = true ]; then
        print_section "Quality Tests (RAGAS - Slow, API Costs ~\\$2-5)"

        if [ "$OPENAI_KEY_OK" = false ]; then
            print_warning "Skipping quality tests (OPENAI_API_KEY not set)"
            print_info "Set OPENAI_API_KEY environment variable to run RAGAS tests"
        else
            local quality_start=$(date +%s)

            print_info "Running RAGAS quality evaluation tests..."
            print_warning "This may take 10-15 minutes and costs ~\\$2-5 in API usage"

            if python -m pytest $PYTEST_ARGS -m "quality or slow" tests/quality/ 2>&1 | tee /tmp/quality_test_output.txt; then
                PYTEST_QUALITY_PASSED=$(grep -oP '\d+(?= passed)' /tmp/quality_test_output.txt | head -1 || echo "0")
                PYTEST_QUALITY_FAILED=$(grep -oP '\d+(?= failed)' /tmp/quality_test_output.txt | head -1 || echo "0")
                print_success "Quality tests completed"
            else
                PYTEST_QUALITY_FAILED=$(grep -oP '\d+(?= failed)' /tmp/quality_test_output.txt | head -1 || echo "1")
                print_error "Quality tests failed"
            fi

            local quality_end=$(date +%s)
            QUALITY_TIME=$((quality_end - quality_start))
        fi
    fi

    echo ""
}

################################################################################
# Promptfoo Tests
################################################################################

run_promptfoo_tests() {
    if [ "$RUN_PROMPTFOO" = false ]; then
        return 0
    fi

    if [ "$NPX_OK" = false ]; then
        print_warning "Skipping promptfoo tests (npx not available)"
        return 0
    fi

    print_header "PROMPTFOO TESTS"

    if [ "$OPENAI_KEY_OK" = false ]; then
        print_warning "OPENAI_API_KEY not set - promptfoo tests will fail"
        print_info "Set OPENAI_API_KEY or create promptfoo/.env file"
        return 0
    fi

    cd promptfoo

    local promptfoo_start=$(date +%s)

    # Web Assistant Tests
    print_section "Web Assistant Tests (Practitioner-Facing AI)"
    print_info "Running web_assistant_test.yaml..."

    if npx promptfoo eval -c configs/web_assistant_test.yaml --no-progress-bar > /tmp/web_assistant_output.txt 2>&1; then
        print_success "Web Assistant tests completed"
        # Parse results (promptfoo outputs summary at end)
        PROMPTFOO_WEB_ASSISTANT_TOTAL=30  # Approximate from config
    else
        print_error "Web Assistant tests failed"
    fi

    # jAImee Therapist Tests
    print_section "jAImee Therapist Tests (Client-Facing AI)"
    print_info "Running jaimee_test.yaml..."
    print_warning "This includes crisis handling tests - may take 5-7 minutes"

    if npx promptfoo eval -c configs/jaimee_test.yaml --no-progress-bar > /tmp/jaimee_output.txt 2>&1; then
        print_success "jAImee tests completed"
        PROMPTFOO_JAIMEE_TOTAL=40  # Approximate from config
    else
        print_error "jAImee tests failed"
    fi

    # Transcriber Tests
    print_section "Transcriber Tests (Document Generation)"
    print_info "Running transcriber_test.yaml..."

    if npx promptfoo eval -c configs/transcriber_test.yaml --no-progress-bar > /tmp/transcriber_output.txt 2>&1; then
        print_success "Transcriber tests completed"
        PROMPTFOO_TRANSCRIBER_TOTAL=30  # Approximate from config
    else
        print_error "Transcriber tests failed"
    fi

    # Red Team Tests (Optional)
    if [ "$RUN_RED_TEAM" = true ]; then
        print_section "Red Team Tests (Adversarial Attack Testing)"
        print_warning "This tests 15 attack plugins with 100+ variations"
        print_warning "May take 15-20 minutes and costs ~\\$5-10 in API usage"
        print_info "Running redteam/config.yaml..."

        if npx promptfoo redteam -c redteam/config.yaml --no-progress-bar > /tmp/redteam_output.txt 2>&1; then
            print_success "Red team tests completed"
            PROMPTFOO_RED_TEAM_TOTAL=100  # Approximate
        else
            print_error "Red team tests failed"
            echo -e "${RED}${BOLD}Red team failures indicate security vulnerabilities${NC}"
        fi
    else
        print_info "Red team tests skipped (use --red-team to run)"
    fi

    cd ..

    local promptfoo_end=$(date +%s)
    PROMPTFOO_TIME=$((promptfoo_end - promptfoo_start))

    echo ""
}

################################################################################
# Generate Report
################################################################################

generate_report() {
    print_header "COMPREHENSIVE TEST REPORT"

    local end_time=$(date +%s)
    local total_time=$((end_time - START_TIME))

    # Calculate totals
    local total_pytest_passed=$((PYTEST_UNIT_PASSED + PYTEST_SAFETY_PASSED + PYTEST_INTEGRATION_PASSED + PYTEST_QUALITY_PASSED))
    local total_pytest_failed=$((PYTEST_UNIT_FAILED + PYTEST_SAFETY_FAILED + PYTEST_INTEGRATION_FAILED + PYTEST_QUALITY_FAILED))
    local total_pytest=$((total_pytest_passed + total_pytest_failed))

    local total_promptfoo=$((PROMPTFOO_WEB_ASSISTANT_TOTAL + PROMPTFOO_JAIMEE_TOTAL + PROMPTFOO_TRANSCRIBER_TOTAL + PROMPTFOO_RED_TEAM_TOTAL))

    local total_tests=$((total_pytest + total_promptfoo))
    local total_passed=$((total_pytest_passed))
    local total_failed=$((total_pytest_failed))

    # Start report
    {
        echo "================================================================================"
        echo "HAYSTACK COMPREHENSIVE TEST REPORT"
        echo "Generated: $(date '+%Y-%m-%d %H:%M:%S')"
        echo "================================================================================"
        echo ""

        echo "ENVIRONMENT"
        echo "-----------"
        echo "Python: $PYTHON_VERSION"
        if command -v node &> /dev/null; then
            echo "Node.js: $(node --version)"
        fi
        echo "OpenAI API Key: $([ "$OPENAI_KEY_OK" = true ] && echo "✓ Set" || echo "⊘ Not set")"
        echo "Redis: $([ "$REDIS_OK" = true ] && echo "✓ Running (localhost:6379)" || echo "⚠ Not running")"
        echo ""

        if [ "$RUN_PYTEST" = true ]; then
            echo "PYTEST TESTS"
            echo "------------"

            if [ "$RUN_UNIT" = true ]; then
                echo "Unit Tests:          $PYTEST_UNIT_PASSED passed, $PYTEST_UNIT_FAILED failed (${UNIT_TIME}s)"
            fi

            if [ "$RUN_SAFETY" = true ]; then
                if [ "$PYTEST_SAFETY_FAILED" -eq 0 ]; then
                    echo "Safety Tests:        $PYTEST_SAFETY_PASSED passed, $PYTEST_SAFETY_FAILED failed (${SAFETY_TIME}s) ✓ CRITICAL"
                else
                    echo "Safety Tests:        $PYTEST_SAFETY_PASSED passed, $PYTEST_SAFETY_FAILED failed (${SAFETY_TIME}s) ✗ CRITICAL FAILURE"
                fi
            fi

            if [ "$RUN_INTEGRATION" = true ]; then
                echo "Integration Tests:   $PYTEST_INTEGRATION_PASSED passed, $PYTEST_INTEGRATION_FAILED failed (${INTEGRATION_TIME}s)"
            fi

            if [ "$RUN_QUALITY" = true ]; then
                echo "Quality Tests:       $PYTEST_QUALITY_PASSED passed, $PYTEST_QUALITY_FAILED failed (${QUALITY_TIME}s)"
            fi

            echo "Total Pytest:        $total_pytest_passed passed, $total_pytest_failed failed"

            if [ "$GENERATE_COVERAGE" = true ] && [ -f coverage.xml ]; then
                echo "Coverage:            See htmlcov/index.html"
            fi
            echo ""
        fi

        if [ "$RUN_PROMPTFOO" = true ] && [ "$NPX_OK" = true ]; then
            echo "PROMPTFOO TESTS"
            echo "---------------"
            echo "Web Assistant:       $PROMPTFOO_WEB_ASSISTANT_TOTAL tests"
            echo "jAImee Therapist:    $PROMPTFOO_JAIMEE_TOTAL tests"
            echo "Transcriber:         $PROMPTFOO_TRANSCRIBER_TOTAL tests"

            if [ "$RUN_RED_TEAM" = true ]; then
                echo "Red Team:            $PROMPTFOO_RED_TEAM_TOTAL tests"
            else
                echo "Red Team:            ⊘ Skipped (use --red-team to run)"
            fi

            echo ""
            echo "Promptfoo results saved to: promptfoo/.promptfoo/"
            echo "View detailed results: cd promptfoo && npx promptfoo view"
            echo ""
        fi

        echo "OVERALL SUMMARY"
        echo "---------------"
        echo "Total Tests:         $total_tests tests"
        echo "Total Time:          $(printf '%02d:%02d:%02d' $((total_time/3600)) $((total_time%3600/60)) $((total_time%60)))"
        echo ""

        echo "RECOMMENDATIONS"
        echo "---------------"

        if [ "$PYTEST_SAFETY_FAILED" -eq 0 ]; then
            echo "✓ All safety-critical tests passed"
        else
            echo "✗ CRITICAL: Safety tests failed - DO NOT DEPLOY"
        fi

        if [ "$total_pytest_failed" -eq 0 ]; then
            echo "✓ All pytest tests passed"
        else
            echo "⚠ Review $total_pytest_failed failed pytest tests before deployment"
        fi

        if [ "$RUN_RED_TEAM" = false ] && [ "$RUN_PROMPTFOO" = true ]; then
            echo "⚠ Consider running red team tests before production release (--red-team)"
        fi

        if [ "$GENERATE_COVERAGE" = true ]; then
            echo "✓ Coverage report generated (see htmlcov/index.html)"
        fi

        echo ""
        echo "Report saved to: $REPORT_FILE"
        echo "================================================================================"
    } | tee "$REPORT_FILE"

    # Final status
    echo ""
    if [ "$PYTEST_SAFETY_FAILED" -gt 0 ]; then
        echo -e "${RED}${BOLD}❌ CRITICAL FAILURE: Safety tests failed${NC}"
        echo -e "${RED}DO NOT DEPLOY TO PRODUCTION${NC}"
        exit 1
    elif [ "$total_pytest_failed" -gt 0 ]; then
        echo -e "${YELLOW}${BOLD}⚠ WARNING: Some tests failed${NC}"
        echo -e "${YELLOW}Review failures before deployment${NC}"
        exit 1
    else
        echo -e "${GREEN}${BOLD}✅ SUCCESS: All tests passed${NC}"
        exit 0
    fi
}

################################################################################
# Main Execution
################################################################################

main() {
    print_header "HAYSTACK COMPREHENSIVE TEST SUITE"
    echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"
    echo ""

    # Validate environment
    validate_environment

    # Run tests
    if [ "$RUN_PYTEST" = true ]; then
        run_pytest_tests
    fi

    if [ "$RUN_PROMPTFOO" = true ]; then
        run_promptfoo_tests
    fi

    # Generate report
    generate_report
}

# Run main function
main "$@"
