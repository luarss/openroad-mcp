#!/usr/bin/env python3
"""
Helper script to run the OpenROAD MCP benchmark against an LLM.

This script loads the benchmark prompts and provides a framework for
testing your LLM's tool calling capabilities.
"""

import argparse
import json
from collections.abc import Callable
from typing import Any


class BenchmarkRunner:
    """Runs benchmark prompts through an LLM and collects results."""

    def __init__(self, benchmark_path: str):
        """Load the benchmark dataset."""
        with open(benchmark_path) as f:
            self.benchmark = json.load(f)
        self.test_cases = self.benchmark["test_cases"]

    def get_prompts(
        self, category: str | None = None, difficulty: str | None = None, limit: int | None = None
    ) -> list[dict]:
        """
        Get benchmark prompts with optional filtering.

        Args:
            category: Filter by category (single_tool, sequential_workflow, etc.)
            difficulty: Filter by difficulty (easy, medium, hard)
            limit: Maximum number of prompts to return

        Returns:
            List of test cases with id, prompt, category, difficulty
        """
        filtered = self.test_cases

        if category:
            filtered = [tc for tc in filtered if tc["category"] == category]

        if difficulty:
            filtered = [tc for tc in filtered if tc["difficulty"] == difficulty]

        if limit:
            filtered = filtered[:limit]

        return [
            {"id": tc["id"], "prompt": tc["prompt"], "category": tc["category"], "difficulty": tc["difficulty"]}
            for tc in filtered
        ]

    def create_results_template(
        self, output_path: str, category: str | None = None, difficulty: str | None = None
    ) -> None:
        """
        Create a template results file for manual testing.

        Args:
            output_path: Where to save the template
            category: Filter by category
            difficulty: Filter by difficulty
        """
        prompts = self.get_prompts(category=category, difficulty=difficulty)

        template = {}
        for prompt_data in prompts:
            template[prompt_data["id"]] = {
                "prompt": prompt_data["prompt"],
                "category": prompt_data["category"],
                "difficulty": prompt_data["difficulty"],
                "tools_called": [
                    # Fill this in with your LLM's response
                    # {
                    #   "name": "tool_name",
                    #   "parameters": {...}
                    # }
                ],
            }

        with open(output_path, "w") as f:
            json.dump(template, f, indent=2)

        print(f"Template created with {len(template)} test cases: {output_path}")
        print("\nNext steps:")
        print("1. Run your LLM on each prompt")
        print("2. Fill in the 'tools_called' arrays with the LLM's tool calls")
        print("3. Run: python evaluate.py --results your_results.json")

    def run_with_custom_llm(
        self,
        llm_function: Callable[[str], list[dict[str, Any]]],
        output_path: str,
        category: str | None = None,
        difficulty: str | None = None,
        limit: int | None = None,
    ) -> None:
        """
        Run benchmark using a custom LLM function.

        Args:
            llm_function: Callable that takes a prompt string and returns list of tool calls
                         Expected signature: llm_function(prompt: str) -> List[Dict]
                         Each dict should have 'name' and 'parameters' keys
            output_path: Where to save results
            category: Filter by category
            difficulty: Filter by difficulty
            limit: Maximum number of test cases to run

        Example:
            def my_llm(prompt: str) -> List[Dict]:
                # Your LLM integration here
                response = llm_client.chat(prompt)
                return response.tool_calls

            runner.run_with_custom_llm(my_llm, "results.json", limit=10)
        """
        prompts = self.get_prompts(category=category, difficulty=difficulty, limit=limit)
        results = {}

        print(f"Running {len(prompts)} test cases...")
        for i, prompt_data in enumerate(prompts, 1):
            test_id = prompt_data["id"]
            prompt = prompt_data["prompt"]

            print(f"[{i}/{len(prompts)}] {test_id}: {prompt[:60]}...")

            try:
                tools_called = llm_function(prompt)
                results[test_id] = {"tools_called": tools_called}
            except Exception as e:
                print(f"  ERROR: {e}")
                results[test_id] = {"tools_called": [], "error": str(e)}  # type: ignore[dict-item]

        # Save results
        with open(output_path, "w") as f:
            json.dump(results, f, indent=2)

        print(f"\n✓ Results saved to: {output_path}")
        print(f"\nEvaluate with: python evaluate.py --results {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run OpenROAD MCP benchmark")
    parser.add_argument(
        "--benchmark", type=str, default="openroad_mcp_benchmark.json", help="Path to benchmark JSON file"
    )
    parser.add_argument("--template", type=str, help="Create a results template file at this path")
    parser.add_argument(
        "--category",
        type=str,
        choices=["single_tool", "sequential_workflow", "parallel_execution", "state_management", "error_handling"],
        help="Filter by category",
    )
    parser.add_argument("--difficulty", type=str, choices=["easy", "medium", "hard"], help="Filter by difficulty")
    parser.add_argument("--limit", type=int, help="Limit number of test cases")
    parser.add_argument("--list", action="store_true", help="List all test cases")

    args = parser.parse_args()

    runner = BenchmarkRunner(args.benchmark)

    if args.list:
        # List all test cases
        prompts = runner.get_prompts(category=args.category, difficulty=args.difficulty, limit=args.limit)
        print(f"\n{'ID':<10} {'Category':<25} {'Difficulty':<10} {'Prompt'}")
        print("=" * 100)
        for p in prompts:
            prompt_preview = p["prompt"][:50] + "..." if len(p["prompt"]) > 50 else p["prompt"]
            print(f"{p['id']:<10} {p['category']:<25} {p['difficulty']:<10} {prompt_preview}")
        print(f"\nTotal: {len(prompts)} test cases")

    elif args.template:
        # Create template
        runner.create_results_template(args.template, category=args.category, difficulty=args.difficulty)

    else:
        parser.print_help()
        print("\n\nExamples:")
        print("  # List all test cases")
        print("  python run_benchmark.py --list")
        print("\n  # List only easy single_tool tests")
        print("  python run_benchmark.py --list --category single_tool --difficulty easy")
        print("\n  # Create template for first 10 tests")
        print("  python run_benchmark.py --template results_template.json --limit 10")
        print("\n  # Create template for all sequential_workflow tests")
        print("  python run_benchmark.py --template seq_tests.json --category sequential_workflow")


if __name__ == "__main__":
    main()
