# Quick Start Guide

Get started with the OpenROAD MCP Tool Calling Benchmark in 5 minutes!

## Installation

No dependencies beyond Python 3.7+ standard library. The benchmark is self-contained.

```bash
cd benchmark/
```

## Quick Test Run

### Step 1: Explore the Benchmark

List all test cases:
```bash
python run_benchmark.py --list
```

List only easy tests:
```bash
python run_benchmark.py --list --difficulty easy
```

View the first 10 test cases:
```bash
python run_benchmark.py --list --limit 10
```

### Step 2: Create a Results Template

Generate a template for manual testing (first 5 tests):
```bash
python run_benchmark.py --template my_results.json --limit 5
```

This creates a JSON file with prompts and empty spaces for tool calls.

### Step 3: Fill in LLM Responses

Open `my_results.json` and fill in the `tools_called` arrays based on your LLM's responses.

Example:
```json
{
  "ST001": {
    "prompt": "Create a new OpenROAD interactive session",
    "category": "single_tool",
    "difficulty": "easy",
    "tools_called": [
      {
        "name": "create_interactive_session",
        "parameters": {}
      }
    ]
  }
}
```

### Step 4: Evaluate Results

First, install DeepEval:
```bash
pip install deepeval
```

Run the evaluation:
```bash
python evaluate.py --results my_results.json --output my_report.json
```

## Automated Testing (with Custom LLM)

If you have an LLM API, you can automate testing:

```python
from run_benchmark import BenchmarkRunner

def my_llm(prompt: str):
    """Your LLM integration here."""
    # Example with OpenAI
    response = openai.ChatCompletion.create(
        model="gpt-4",
        messages=[{"role": "user", "content": prompt}],
        tools=OPENROAD_MCP_TOOLS  # Define your tools
    )
    return response.tool_calls  # Format as needed

runner = BenchmarkRunner("openroad_mcp_benchmark.json")
runner.run_with_custom_llm(my_llm, "results.json", limit=10)
```

Then evaluate:
```bash
python evaluate.py --results results.json
```

## Testing by Category

### Test Single Tool Selection (40 cases)
```bash
python run_benchmark.py --template single_tool.json --category single_tool
# Fill in results, then:
python evaluate.py --results single_tool.json
```

### Test Sequential Workflows (25 cases)
```bash
python run_benchmark.py --template workflows.json --category sequential_workflow
# Fill in results, then:
python evaluate.py --results workflows.json
```

### Test Parallel Execution (15 cases)
```bash
python run_benchmark.py --template parallel.json --category parallel_execution
# Fill in results, then:
python evaluate.py --results parallel.json
```

### Test State Management (15 cases)
```bash
python run_benchmark.py --template state.json --category state_management
# Fill in results, then:
python evaluate.py --results state.json
```

### Test Error Handling (10 cases)
```bash
python run_benchmark.py --template errors.json --category error_handling
# Fill in results, then:
python evaluate.py --results errors.json
```

## Testing by Difficulty

### Easy Tests Only
```bash
python run_benchmark.py --template easy.json --difficulty easy
python evaluate.py --results easy.json
```

### Medium Tests Only
```bash
python run_benchmark.py --template medium.json --difficulty medium
python evaluate.py --results medium.json
```

### Hard Tests Only
```bash
python run_benchmark.py --template hard.json --difficulty hard
python evaluate.py --results hard.json
```

## Understanding Scores

- **Pass Threshold**: 90% (0.9)
- **Tool Selection**: Did it call the right tools?
- **Parameter Accuracy**: Are all parameters correct?
- **Execution Order**: For workflows, is the sequence right?
- **Parallel Execution**: Did it identify parallelizable operations?

Example output:
```
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
```

## Tips for Best Results

1. **Start Small**: Test with 5-10 cases first to understand the format
2. **Use Templates**: Always generate templates to ensure correct JSON format
3. **Check Examples**: Review `example_results.json` for reference
4. **Read Prompts Carefully**: Some prompts have subtle requirements
5. **Verify Parameters**: Parameter types and values must match exactly
6. **Order Matters**: For sequential workflows, tool order is evaluated
7. **Test Systematically**: Run each category separately to identify weaknesses

## Common Issues

### Issue: "Test case not found"
**Solution**: Ensure your test IDs match exactly (case-sensitive)

### Issue: Low parameter accuracy scores
**Solution**: Check parameter types (strings vs numbers), spelling, and required vs optional params

### Issue: Failed execution order
**Solution**: Ensure dependent operations are in the right sequence

### Issue: Parallel execution failures
**Solution**: Independent operations should be called together, not sequentially

## Next Steps

1. Run the full benchmark (100 cases)
2. Analyze category-specific performance
3. Improve your LLM's weak areas
4. Compare results with baseline models
5. Share your results with the community!

## Getting Help

- Check the main [README.md](README.md) for detailed documentation
- Review the benchmark JSON for test case details
- See `example_results.json` for correct format
- Open an issue for bugs or questions

## Example Complete Workflow

```bash
# 1. List test cases to understand scope
python run_benchmark.py --list --category single_tool --difficulty easy

# 2. Create template for those tests
python run_benchmark.py --template test_run.json --category single_tool --difficulty easy

# 3. Open test_run.json and fill in your LLM's responses

# 4. Evaluate
python evaluate.py --results test_run.json --output report.json --verbose

# 5. Review report.json and terminal output
cat report.json | jq '.overall'
```

Happy benchmarking! 🚀
