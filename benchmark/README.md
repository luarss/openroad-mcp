# OpenROAD MCP Tool Calling Benchmark

A comprehensive benchmark for evaluating Large Language Model (LLM) tool calling accuracy on the OpenROAD MCP server. This benchmark tests an LLM's ability to correctly select tools, provide accurate parameters, handle complex workflows, and avoid unnecessary tool calls.

## Overview

The benchmark consists of **100 test cases** across 5 categories, designed to evaluate different aspects of tool calling capabilities:

1. **Single Tool Selection** (40 cases, 35% weight) - Basic tool selection and parameter accuracy
2. **Sequential Workflows** (25 cases, 25% weight) - Multi-step dependent operations
3. **Parallel Execution** (15 cases, 15% weight) - Concurrent independent operations
4. **State Management** (15 cases, 15% weight) - Conditional logic and session lifecycle
5. **Error Handling** (10 cases, 10% weight) - Edge cases and inappropriate tool usage

Each test case includes:
- Difficulty level (easy/medium/hard)
- Natural language prompt
- Expected tool calls with parameters
- Scoring criteria

## Benchmark Design Philosophy

This benchmark is inspired by leading tool calling benchmarks:

- **Berkeley Function Calling Leaderboard (BFCL)** - Comprehensive evaluation framework
- **NESTful** - Nested sequence evaluation
- **API-Bank** - Tool planning and retrieval assessment

Our benchmark is specifically tailored for:
- **Domain-specific tools** (VLSI chip design with OpenROAD)
- **Session management** scenarios
- **Interactive command execution** workflows
- **Report and image handling** operations

## Files

```
benchmark/
├── openroad_mcp_benchmark.json  # Complete benchmark dataset (100 test cases)
├── evaluate.py                   # DeepEval-based evaluation (research-backed metrics)
├── run_benchmark.py              # Helper script to run benchmark tests
├── example_results.json          # Example LLM results format
├── requirements.txt              # Dependencies (DeepEval)
├── README.md                     # This file (comprehensive documentation)
└── QUICKSTART.md                 # Quick start guide
```

## Evaluation Method

This benchmark uses **DeepEval** for research-backed agent evaluation:

- ✅ Research-backed evaluation metrics
- ✅ LLM-as-a-Judge for nuanced assessment
- ✅ Agent-specific metrics (Tool Correctness, Task Completion)
- ✅ Integration with Confident AI platform
- 📊 Evaluates: tool correctness, parameter accuracy, workflow ordering
- 📦 Requires: `pip install deepeval`

## Test Categories

### Category 1: Single Tool Selection (40 cases)

Tests basic tool calling ability:
- Correct tool selection from 9 available tools
- Required vs optional parameters
- Parameter type accuracy
- Value formatting

**Example:**
```
Prompt: "Create a new OpenROAD interactive session"
Expected: create_interactive_session with {} parameters
```

### Category 2: Sequential Workflows (25 cases)

Tests multi-step dependent operations:
- Correct ordering of tool calls
- Session ID propagation
- Dependent parameter usage
- Command chaining

**Example:**
```
Prompt: "Create a session called 'test-flow', then run 'report_design_area'"
Expected:
  1. create_interactive_session(session_id="test-flow")
  2. interactive_openroad(command="report_design_area", session_id="test-flow")
```

### Category 3: Parallel Execution (15 cases)

Tests recognition of independent operations:
- Identifying parallelizable operations
- Concurrent tool calls
- No dependency between operations

**Example:**
```
Prompt: "Get session metrics and list all active sessions at the same time"
Expected: get_session_metrics() || list_interactive_sessions()
```

### Category 4: State Management (15 cases)

Tests conditional logic and session awareness:
- State-dependent decisions
- Conditional tool execution
- Session lifecycle understanding
- Resource management

**Example:**
```
Prompt: "Inspect session long-running, and if idle >5min, terminate it"
Expected:
  1. inspect_interactive_session(session_id="long-running")
  2. [conditional] terminate_interactive_session(session_id="long-running")
```

### Category 5: Error Handling (10 cases)

Tests ability to avoid inappropriate tool calls:
- Recognizing informational queries
- Conversational responses
- Explaining limitations
- Handling unavailable operations

**Example:**
```
Prompt: "What is OpenROAD?"
Expected: [] (no tool calls, provide informational response)
```

## Usage

### 1. Generate LLM Results

Have your LLM process the prompts from the benchmark and save results in this format:

```json
{
  "test_id": {
    "tools_called": [
      {
        "name": "tool_name",
        "parameters": {
          "param1": "value1",
          "param2": "value2"
        }
      }
    ]
  }
}
```

See `example_results.json` for a complete example.

### 2. Run Evaluation

First, install DeepEval:
```bash
pip install deepeval
```

Then run evaluation:
```bash
python evaluate.py --results your_llm_results.json --output report.json
```

Options:
- `--benchmark`: Path to benchmark file (default: openroad_mcp_benchmark.json)
- `--results`: Path to your LLM results file (required)
- `--output`: Path to save evaluation report (default: deepeval_report.json)

DeepEval provides:
- **Tool Correctness Metric**: Validates proper tool selection and usage
- **G-Eval Metrics**: Custom evaluation criteria for parameter accuracy and workflow ordering
- **Research-backed scoring**: Uses LLM-as-a-Judge for nuanced evaluation
- **Confident AI Platform Integration**: Optional cloud-based monitoring and analysis

### 3. View Results

The script outputs:
- Overall pass rate and average score
- Performance by category
- Performance by difficulty level
- Individual test results (with --verbose)

Example output:
```
================================================================================
OpenROAD MCP Tool Calling Benchmark - Evaluation Report
================================================================================

Overall Performance:
  Total Tests: 100
  Passed: 87
  Pass Rate: 87.0%
  Average Score: 0.891


By Category:
  single_tool              :  92.5% (37/40) - Avg: 0.934
  sequential_workflow      :  84.0% (21/25) - Avg: 0.867
  parallel_execution       :  86.7% (13/15) - Avg: 0.889
  state_management         :  73.3% (11/15) - Avg: 0.801
  error_handling           :  90.0% (9/10)  - Avg: 0.920


By Difficulty:
  easy      :  95.0% (19/20) - Avg: 0.962
  medium    :  87.5% (35/40) - Avg: 0.891
  hard      :  82.5% (33/40) - Avg: 0.845
```

## Scoring Methodology

Each test case is scored based on multiple dimensions:

### Tool Selection (typically 40% weight)
- Correct tool name(s)
- Correct number of tool calls
- No extraneous tools

### Parameter Accuracy (typically 35% weight)
- All required parameters present
- Correct parameter values
- Proper parameter types
- No unexpected parameters (unless allowed)

### Execution Order (workflow-specific, 15% when applicable)
- Correct sequence for dependent operations
- Proper dependency handling

### Parallel Execution (parallel-specific, 15% when applicable)
- All parallel tools identified
- No missing parallel opportunities

### No Tool Call (error handling, 100% when applicable)
- Correctly avoiding tool calls when inappropriate

**Total Score Formula:**
```
score = (tool_selection × weight_ts) +
        (parameter_accuracy × weight_pa) +
        (execution_order × weight_eo) +
        (parallel_execution × weight_pe)
```

**Pass Threshold:** 90% (0.9)

## Tools Reference

The benchmark evaluates tool calling for these 9 MCP tools:

| Tool | Required Params | Optional Params |
|------|----------------|-----------------|
| `interactive_openroad` | command | session_id, timeout_ms |
| `create_interactive_session` | - | session_id, command, cwd, env |
| `list_interactive_sessions` | - | - |
| `terminate_interactive_session` | session_id | force |
| `inspect_interactive_session` | session_id | - |
| `get_session_history` | session_id | limit, search |
| `get_session_metrics` | - | - |
| `list_report_images` | platform, design, run_slug | stage |
| `read_report_image` | platform, design, run_slug, image_name | - |

## Difficulty Levels

- **Easy (20 cases)**: Single tool, obvious selection, minimal parameters
- **Medium (40 cases)**: Multiple parameters, some ambiguity, 2-3 step workflows
- **Hard (40 cases)**: Complex parameters, conditional logic, 3+ step workflows, edge cases

## Benchmark Statistics

| Category | Easy | Medium | Hard | Total |
|----------|------|--------|------|-------|
| Single Tool | 8 | 16 | 16 | 40 |
| Sequential Workflow | 0 | 12 | 13 | 25 |
| Parallel Execution | 2 | 8 | 5 | 15 |
| State Management | 0 | 6 | 9 | 15 |
| Error Handling | 3 | 4 | 3 | 10 |
| **Total** | **13** | **46** | **46** | **100** |

## Extending the Benchmark

To add new test cases:

1. Add to `test_cases` array in `openroad_mcp_benchmark.json`
2. Follow the schema:
```json
{
  "id": "CATEGORY_NNN",
  "category": "single_tool|sequential_workflow|parallel_execution|state_management|error_handling",
  "difficulty": "easy|medium|hard",
  "prompt": "Natural language instruction",
  "expected_tools": [
    {
      "name": "tool_name",
      "parameters": {...},
      "order": 1,  // For sequential
      "parallel_with": [...],  // For parallel
      "conditional": true,  // For state management
      "allow_extra_params": false
    }
  ],
  "scoring": {
    "tool_selection": 1.0,
    "parameter_accuracy": 1.0,
    "execution_order": 1.0,  // If applicable
    "parallel_execution": 1.0  // If applicable
  }
}
```

3. Update category counts in `benchmark_info`

## Comparison with Other Benchmarks

| Feature | BFCL | NESTful | API-Bank | OpenROAD MCP |
|---------|------|---------|----------|--------------|
| Test Cases | 2000+ | 762 | 753 | 100 |
| Domain | General | General | General | VLSI/Chip Design |
| Multi-turn | ✓ | ✓ | ✓ | ✓ |
| Parallel Calls | ✓ | - | - | ✓ |
| State Management | - | - | - | ✓ |
| Session Lifecycle | - | - | - | ✓ |
| Conditional Logic | - | - | - | ✓ |

## Citation

If you use this benchmark in your research, please cite:

```bibtex
@misc{openroad-mcp-benchmark,
  title={OpenROAD MCP Tool Calling Benchmark},
  author={OpenROAD MCP Contributors},
  year={2024},
  howpublished={\url{https://github.com/your-org/openroad-mcp}}
}
```

## References

- [Berkeley Function Calling Leaderboard (BFCL)](https://gorilla.cs.berkeley.edu/leaderboard.html)
- [NESTful: Nested Sequences of API Calls](https://arxiv.org/html/2409.03797v2)
- [Docker: Local LLM Tool Calling Evaluation](https://www.docker.com/blog/local-llm-tool-calling-a-practical-evaluation/)
- [OpenROAD Project](https://theopenroadproject.org/)

## License

This benchmark is released under the same license as the OpenROAD MCP server.

## Contributing

Contributions are welcome! Please:
1. Follow the existing test case format
2. Ensure balanced distribution across categories and difficulties
3. Test your additions with the evaluation script
4. Submit a pull request with clear description

## Acknowledgments

This benchmark design was informed by:
- Berkeley's BFCL team for function calling evaluation methodology
- The OpenROAD community for domain expertise
- LangChain for agent benchmarking best practices
