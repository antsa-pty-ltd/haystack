#!/bin/bash

# Haystack Service Test Runner
# Usage: ./run_tests.sh [options]

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}==================================${NC}"
echo -e "${GREEN}Haystack Service Test Runner${NC}"
echo -e "${GREEN}==================================${NC}"
echo ""

# Check if we're in the right directory
if [ ! -f "main.py" ]; then
    echo -e "${RED}Error: Must run from haystack directory${NC}"
    echo -e "${YELLOW}Run: cd haystack && ./run_tests.sh${NC}"
    exit 1
fi

# Check if test dependencies are installed
echo -e "${YELLOW}Checking dependencies...${NC}"
if ! python3 -c "import pytest" 2>/dev/null; then
    echo -e "${YELLOW}Installing test dependencies...${NC}"
    pip3 install -r tests/requirements-test.txt
else
    echo -e "${GREEN}✓ Dependencies installed${NC}"
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Warning: .env file not found${NC}"
    echo -e "${YELLOW}Creating from .env.example...${NC}"
    cp .env.example .env
    echo -e "${YELLOW}Please update .env with your API keys${NC}"
fi

# Check OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    if [ -f ".env" ] && grep -q "OPENAI_API_KEY=" .env; then
        # Load environment variable from .env file safely
        # Extract the API key value after the = sign
        OPENAI_API_KEY=$(grep "^OPENAI_API_KEY=" .env | cut -d '=' -f 2-)
        export OPENAI_API_KEY
    fi
fi

# Check Redis (optional)
echo -e "${YELLOW}Checking Redis connection (optional)...${NC}"
if redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Redis is running${NC}"
else
    echo -e "${YELLOW}⚠ Redis not running (will use in-memory fallback)${NC}"
fi

echo ""
echo -e "${GREEN}==================================${NC}"
echo -e "${GREEN}Running Tests${NC}"
echo -e "${GREEN}==================================${NC}"
echo ""

# Default test command
TEST_CMD="python3 -m pytest tests/ -v"

# Parse command line arguments
case "$1" in
    "quick")
        echo -e "${YELLOW}Running quick tests (no integration)${NC}"
        TEST_CMD="python3 -m pytest tests/ -v -m \"not integration\" -x"
        ;;
    "integration")
        echo -e "${YELLOW}Running integration tests only${NC}"
        TEST_CMD="python3 -m pytest tests/ -v -m integration"
        ;;
    "coverage")
        echo -e "${YELLOW}Running tests with coverage${NC}"
        TEST_CMD="python3 -m pytest tests/ -v --cov=. --cov-report=html --cov-report=term"
        ;;
    "parallel")
        echo -e "${YELLOW}Running tests in parallel${NC}"
        TEST_CMD="python3 -m pytest tests/ -v -n auto"
        ;;
    "watch")
        echo -e "${YELLOW}Running tests in watch mode${NC}"
        echo -e "${YELLOW}Tests will re-run on file changes${NC}"
        python3 -m pytest_watch tests/ -v
        exit 0
        ;;
    "health")
        echo -e "${YELLOW}Running health tests only${NC}"
        TEST_CMD="python3 -m pytest tests/test_service_health.py -v"
        ;;
    "websocket")
        echo -e "${YELLOW}Running WebSocket tests only${NC}"
        TEST_CMD="python3 -m pytest tests/test_websocket_integration.py -v"
        ;;
    "session")
        echo -e "${YELLOW}Running session tests only${NC}"
        TEST_CMD="python3 -m pytest tests/test_session_manager.py -v"
        ;;
    "help")
        echo "Usage: ./run_tests.sh [option]"
        echo ""
        echo "Options:"
        echo "  (none)       - Run all tests"
        echo "  quick        - Run quick tests (skip integration)"
        echo "  integration  - Run integration tests only"
        echo "  coverage     - Run tests with coverage report"
        echo "  parallel     - Run tests in parallel"
        echo "  watch        - Run tests in watch mode"
        echo "  health       - Run health tests only"
        echo "  websocket    - Run WebSocket tests only"
        echo "  session      - Run session tests only"
        echo "  help         - Show this help message"
        exit 0
        ;;
    *)
        if [ -n "$1" ]; then
            echo -e "${YELLOW}Running custom pytest command: $@${NC}"
            TEST_CMD="python3 -m pytest $@"
        fi
        ;;
esac

# Run the tests
echo -e "${YELLOW}Command: $TEST_CMD${NC}"
echo ""

if eval "$TEST_CMD"; then
    echo ""
    echo -e "${GREEN}==================================${NC}"
    echo -e "${GREEN}✓ All tests passed!${NC}"
    echo -e "${GREEN}==================================${NC}"

    # Show coverage report location if generated
    if [ "$1" = "coverage" ] && [ -d "htmlcov" ]; then
        echo ""
        echo -e "${YELLOW}Coverage report generated:${NC}"
        echo -e "${YELLOW}  file://$(pwd)/htmlcov/index.html${NC}"
    fi

    exit 0
else
    echo ""
    echo -e "${RED}==================================${NC}"
    echo -e "${RED}✗ Tests failed${NC}"
    echo -e "${RED}==================================${NC}"
    exit 1
fi