#!/bin/bash
# Test MCP server integration with Claude CLI
#
# Usage:
#   ./scripts/test-mcp-integration.sh              # Run discovery tests only
#   ./scripts/test-mcp-integration.sh --all        # Run all tests (requires OpenROAD)
#   CLAUDE_BIN=/path/to/claude ./scripts/test-mcp-integration.sh
#
# Environment variables:
#   CLAUDE_BIN     - Path to claude binary (default: claude)
#   OPENROAD_EXE   - Path to openroad binary (for --all tests)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_CONFIG="${PROJECT_ROOT}/.mcp.json"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
RESULTS_DIR="${PROJECT_ROOT}/.test-results/mcp-cli"
RUN_ALL=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --all|-a)
            RUN_ALL=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --all, -a    Run all tests including session tests (requires OpenROAD)"
            echo "  --help, -h   Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  CLAUDE_BIN    Path to claude binary (default: claude)"
            echo "  OPENROAD_EXE  Path to openroad binary (required for --all)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Setup results directory
mkdir -p "${RESULTS_DIR}"

# Check for nested session (running inside Claude Code)
if [[ -n "${CLAUDECODE}" ]]; then
    echo -e "${YELLOW}WARNING: Running inside Claude Code session.${NC}"
    echo "Tests will fail due to nested session restriction."
    echo "This is expected - tests will pass in CI environment."
    echo ""
fi

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"

    # Check claude binary
    if ! command -v "${CLAUDE_BIN}" &> /dev/null; then
        echo -e "${RED}ERROR: Claude CLI not found at '${CLAUDE_BIN}'${NC}"
        echo "Install from: https://docs.anthropic.com/en/docs/claude-cli"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Claude CLI found: $(command -v "${CLAUDE_BIN}")"

    # Check MCP config
    if [[ ! -f "${MCP_CONFIG}" ]]; then
        echo -e "${RED}ERROR: MCP config not found at '${MCP_CONFIG}'${NC}"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} MCP config found: ${MCP_CONFIG}"

    # Check for OpenROAD if running all tests
    if [[ "${RUN_ALL}" == "true" ]]; then
        if [[ -z "${OPENROAD_EXE}" ]] || [[ ! -x "${OPENROAD_EXE}" ]]; then
            echo -e "${RED}ERROR: OPENROAD_EXE not set or not executable for --all tests${NC}"
            exit 1
        fi
        echo -e "  ${GREEN}✓${NC} OpenROAD found: ${OPENROAD_EXE}"
    fi

    echo ""
}

# Run a single test
# Args: test_name prompt [expected_pattern]
run_test() {
    local name="$1"
    local prompt="$2"
    local expected="${3:-}"
    local output_file="${RESULTS_DIR}/${name}.txt"
    local start_time end_time duration

    echo -e "${YELLOW}Running: ${name}${NC}"
    echo "  Prompt: ${prompt}"

    start_time=$(date +%s)

    # Run claude with the prompt
    set +e
    local stdout stderr exit_code
    stdout=$("${CLAUDE_BIN}" \
        --mcp-config "${MCP_CONFIG}" \
        --print \
        "${prompt}" 2>&1)
    exit_code=$?
    set -e

    end_time=$(date +%s)
    duration=$((end_time - start_time))

    # Save output
    echo "${stdout}" > "${output_file}"

    # Check result
    if [[ ${exit_code} -ne 0 ]]; then
        echo -e "  ${RED}✗ FAILED${NC} (exit code: ${exit_code}, ${duration}s)"
        echo "  Output saved to: ${output_file}"
        echo "  Error: ${stdout}"
        return 1
    fi

    # Check expected pattern if provided
    if [[ -n "${expected}" ]] && ! echo "${stdout}" | grep -qiE "${expected}"; then
        echo -e "  ${RED}✗ FAILED${NC} (expected pattern not found: ${expected})"
        echo "  Output saved to: ${output_file}"
        return 1
    fi

    echo -e "  ${GREEN}✓ PASSED${NC} (${duration}s)"
    return 0
}

# Discovery tests (no OpenROAD required)
run_discovery_tests() {
    echo -e "${YELLOW}=== Discovery Tests ===${NC}"
    echo "These tests verify MCP server discovery without requiring OpenROAD."
    echo ""

    local passed=0
    local failed=0

    # Test 1: List tools
    if run_test "list_tools" \
        "List all MCP tools available from the openroad-mcp server. Just list their names." \
        "interactive_openroad|create_interactive_session"; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 2: Get session metrics
    if run_test "get_metrics" \
        "Call the get_session_metrics MCP tool and report the result." \
        "total_sessions|active_sessions"; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 3: List sessions
    if run_test "list_sessions" \
        "Use the list_interactive_sessions MCP tool to show all current sessions." \
        "sessions"; then
        ((passed++))
    else
        ((failed++))
    fi

    echo ""
    echo -e "${YELLOW}Discovery Tests Summary:${NC} ${passed} passed, ${failed} failed"
    echo ""

    return $((failed > 0 ? 1 : 0))
}

# Session tests (requires OpenROAD)
run_session_tests() {
    echo -e "${YELLOW}=== Session Tests ===${NC}"
    echo "These tests verify interactive session functionality (requires OpenROAD)."
    echo ""

    local passed=0
    local failed=0
    local session_id="test-cli-$$"

    # Test 1: Create session
    if run_test "create_session" \
        "Create an OpenROAD interactive session with session_id '${session_id}'. Report the session_id created."; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 2: Execute command
    if run_test "execute_command" \
        "In session '${session_id}', execute the TCL command 'puts hello' using interactive_openroad."; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 3: Get history
    if run_test "get_history" \
        "Get the command history for session '${session_id}' using get_session_history."; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 4: Inspect session
    if run_test "inspect_session" \
        "Inspect session '${session_id}' using inspect_interactive_session and report its state."; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 5: Terminate session
    if run_test "terminate_session" \
        "Terminate session '${session_id}' using terminate_interactive_session."; then
        ((passed++))
    else
        ((failed++))
    fi

    # Cleanup: ensure session is terminated
    "${CLAUDE_BIN}" --mcp-config "${MCP_CONFIG}" --print \
        "Terminate session '${session_id}' if it exists." 2>/dev/null || true

    echo ""
    echo -e "${YELLOW}Session Tests Summary:${NC} ${passed} passed, ${failed} failed"
    echo ""

    return $((failed > 0 ? 1 : 0))
}

# Report image tests (requires ORFS data)
run_report_tests() {
    echo -e "${YELLOW}=== Report Image Tests ===${NC}"
    echo "These tests verify report image functionality."
    echo ""

    local passed=0
    local failed=0

    # Test: List report images (may fail if no data available)
    if run_test "list_report_images" \
        "Use list_report_images to check for available reports. List platforms and designs if any."; then
        ((passed++))
    else
        ((failed++))
    fi

    echo ""
    echo -e "${YELLOW}Report Tests Summary:${NC} ${passed} passed, ${failed} failed"
    echo ""

    return $((failed > 0 ? 1 : 0))
}

# Main
main() {
    echo "========================================"
    echo "  MCP CLI Integration Tests"
    echo "========================================"
    echo ""

    check_prerequisites

    local total_failed=0

    # Run discovery tests
    if ! run_discovery_tests; then
        ((total_failed++))
    fi

    # Run session tests if --all flag provided
    if [[ "${RUN_ALL}" == "true" ]]; then
        if ! run_session_tests; then
            ((total_failed++))
        fi

        if ! run_report_tests; then
            ((total_failed++))
        fi
    else
        echo -e "${YELLOW}Skipping session tests (use --all to include)${NC}"
        echo ""
    fi

    echo "========================================"
    if [[ ${total_failed} -eq 0 ]]; then
        echo -e "${GREEN}All tests passed!${NC}"
        echo "Results saved to: ${RESULTS_DIR}"
        exit 0
    else
        echo -e "${RED}Some tests failed.${NC}"
        echo "Results saved to: ${RESULTS_DIR}"
        exit 1
    fi
}

main
