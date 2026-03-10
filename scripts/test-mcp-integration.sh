#!/bin/bash
# Test MCP server integration with MCP Inspector CLI
#
# Usage:
#   ./scripts/test-mcp-integration.sh              # Run discovery tests only
#   ./scripts/test-mcp-integration.sh --all        # Run all tests (requires OpenROAD)
#
# Environment variables:
#   OPENROAD_EXE   - Path to openroad binary (for --all tests)
#
# Benefits of MCP Inspector CLI:
#   - No API key or OAuth required
#   - Direct MCP protocol access (deterministic JSON output)
#   - Faster execution (no LLM inference)
#   - Free (no API costs)

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_CONFIG="${PROJECT_ROOT}/.mcp.json"
INSPECTOR="npx @modelcontextprotocol/inspector@latest --cli"
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

# Check prerequisites
check_prerequisites() {
    echo -e "${YELLOW}Checking prerequisites...${NC}"

    # Check Node.js
    if ! command -v node &> /dev/null; then
        echo -e "${RED}ERROR: Node.js not found${NC}"
        echo "Install from: https://nodejs.org/"
        exit 1
    fi
    echo -e "  ${GREEN}✓${NC} Node.js found: $(node --version)"

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

# Run MCP method and capture output
# Args: method_name [--tool-name name] [--tool-arg key=value]...
run_mcp_method() {
    local method="$1"
    shift

    local cmd="${INSPECTOR} --config \"${MCP_CONFIG}\" --server openroad-mcp --method ${method}"
    while [[ $# -gt 0 ]]; do
        cmd="${cmd} $1 \"$2\""
        shift 2
    done

    eval "${cmd}" 2>&1
}

# Run a single test
# Args: test_name method [tool_name] [tool_args_json]
run_test() {
    local name="$1"
    local method="$2"
    local tool_name="${3:-}"
    local tool_args="${4:-}"
    local expected_patterns="${5:-}"
    local output_file="${RESULTS_DIR}/${name}.json"
    local start_time end_time duration

    echo -e "${YELLOW}Running: ${name}${NC}"
    echo "  Method: ${method}"
    [[ -n "${tool_name}" ]] && echo "  Tool: ${tool_name}"
    [[ -n "${tool_args}" ]] && echo "  Args: ${tool_args}"

    start_time=$(date +%s)

    # Build command
    local cmd="${INSPECTOR} --config \"${MCP_CONFIG}\" --server openroad-mcp --method ${method}"
    if [[ -n "${tool_name}" ]]; then
        cmd="${cmd} --tool-name ${tool_name}"
    fi
    if [[ -n "${tool_args}" ]]; then
        # Parse JSON args and add as --tool-arg key=value
        while IFS= read -r line; do
            if [[ -n "${line}" ]]; then
                cmd="${cmd} --tool-arg ${line}"
            fi
        done < <(echo "${tool_args}" | jq -r 'to_entries[] | "\(.key)=\(.value | tojson)"' 2>/dev/null || true)
    fi

    # Run MCP inspector
    set +e
    local stdout stderr exit_code
    stdout=$(eval "${cmd}" 2>&1)
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

    # Check expected patterns if provided
    if [[ -n "${expected_patterns}" ]]; then
        local pattern_failed=false
        for pattern in ${expected_patterns//,/ }; do
            if ! echo "${stdout}" | grep -qiE "${pattern}"; then
                echo -e "  ${RED}✗ FAILED${NC} (expected pattern not found: ${pattern})"
                pattern_failed=true
            fi
        done
        if [[ "${pattern_failed}" == "true" ]]; then
            echo "  Output saved to: ${output_file}"
            return 1
        fi
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
    if run_test "list_tools" "tools/list" "" "" \
        "interactive_openroad|create_interactive_session"; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 2: Get session metrics
    if run_test "get_metrics" "tools/call" "get_session_metrics" "" \
        "active_sessions|total_sessions"; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 3: List sessions
    if run_test "list_sessions" "tools/call" "list_interactive_sessions" "" \
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
    if run_test "create_session" "tools/call" "create_interactive_session" \
        "{\"session_id\": \"${session_id}\"}" \
        "session_id"; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 2: Execute command
    if run_test "execute_command" "tools/call" "interactive_openroad" \
        "{\"session_id\": \"${session_id}\", \"command\": \"puts hello\"}" \
        "hello"; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 3: Get history
    if run_test "get_history" "tools/call" "get_session_history" \
        "{\"session_id\": \"${session_id}\"}" \
        "puts"; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 4: Inspect session
    if run_test "inspect_session" "tools/call" "inspect_interactive_session" \
        "{\"session_id\": \"${session_id}\"}" \
        "session_id|state"; then
        ((passed++))
    else
        ((failed++))
    fi

    # Test 5: Terminate session
    if run_test "terminate_session" "tools/call" "terminate_interactive_session" \
        "{\"session_id\": \"${session_id}\"}" \
        "terminated|success"; then
        ((passed++))
    else
        ((failed++))
    fi

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
    if run_test "list_report_images" "tools/call" "list_report_images" \
        "{\"platform\": \"asap7\", \"design\": \"gcd\", \"run_slug\": \"base\"}" ""; then
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
    echo "  MCP Inspector CLI Integration Tests"
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
