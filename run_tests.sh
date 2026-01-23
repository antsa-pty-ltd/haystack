#!/bin/bash
# Run AI Scribe tests
# Usage: ./run_tests.sh [options]
#
# Options:
#   --unit        Run only unit tests
#   --integration Run only integration tests
#   --safety      Run only safety/policy tests
#   --coverage    Generate coverage report
#   --verbose     Verbose output

set -e

# Change to haystack directory
cd "$(dirname "$0")"

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install test dependencies if needed
if ! python -c "import pytest" 2>/dev/null; then
    echo "Installing test dependencies..."
    pip install -r requirements-test.txt
fi

# Parse arguments
PYTEST_ARGS="-v"
MARKERS=""

for arg in "$@"; do
    case $arg in
        --unit)
            MARKERS="unit"
            ;;
        --integration)
            MARKERS="integration"
            ;;
        --safety)
            MARKERS="safety"
            ;;
        --coverage)
            PYTEST_ARGS="$PYTEST_ARGS --cov=. --cov-report=html --cov-report=term-missing"
            ;;
        --verbose)
            PYTEST_ARGS="$PYTEST_ARGS -vv"
            ;;
        *)
            ;;
    esac
done

# Add marker filter if specified
if [ -n "$MARKERS" ]; then
    PYTEST_ARGS="$PYTEST_ARGS -m $MARKERS"
fi

# Run tests
echo "Running AI Scribe tests..."
echo "Command: pytest $PYTEST_ARGS tests/"
echo ""

python -m pytest $PYTEST_ARGS tests/

echo ""
echo "Tests completed!"
