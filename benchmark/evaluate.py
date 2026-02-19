#!/usr/bin/env python3
"""
DeepEval Integration for OpenROAD MCP Benchmark

This module integrates DeepEval's agent evaluation metrics with our benchmark,
providing research-backed evaluation using Tool Correctness and custom G-Eval metrics.
"""

import json
from typing import Any

from deepeval.metrics import GEval, ToolCorrectnessMetric  # type: ignore[import-not-found]
from deepeval.test_case import LLMTestCase  # type: ignore[import-not-found]


class DeepEvalBenchmarkRunner:
    """Run OpenROAD MCP benchmark using DeepEval metrics."""

    def __init__(self, benchmark_path: str):
        """Initialize with benchmark data."""

        with open(benchmark_path) as f:
            self.benchmark = json.load(f)
        self.test_cases = {tc["id"]: tc for tc in self.benchmark["test_cases"]}

        # Initialize metrics
        self.tool_correctness_metric = ToolCorrectnessMetric(
            threshold=0.9,  # 90% threshold for passing
        )

        # Custom G-Eval metrics for different categories
        self.parameter_accuracy_metric = GEval(
            name="Parameter Accuracy",
            criteria="Evaluate if the tool parameters are accurate and complete",
            evaluation_params=[
                "All required parameters are present",
                "Parameter values match expected values",
                "Parameter types are correct",
                "No unexpected parameters (unless allowed)",
            ],
            threshold=0.9,
        )

        self.workflow_ordering_metric = GEval(
            name="Workflow Ordering",
            criteria="Evaluate if tools are called in the correct sequence for dependent operations",
            evaluation_params=[
                "Dependencies are respected",
                "Tool execution order is logical",
                "Prerequisites are met before dependent calls",
            ],
            threshold=0.9,
        )

    def create_test_case(self, test_id: str, actual_tools: list[dict]) -> LLMTestCase:
        """
        Create a DeepEval test case from benchmark data.

        Args:
            test_id: Test case ID from benchmark
            actual_tools: List of tools called by the LLM

        Returns:
            LLMTestCase configured for evaluation
        """
        test_data = self.test_cases[test_id]
        expected_tools = test_data.get("expected_tools", [])

        # Format tools for DeepEval
        actual_tools_formatted = [
            {"name": tool.get("name"), "arguments": tool.get("parameters", {})} for tool in actual_tools
        ]

        expected_tools_formatted = [
            {"name": tool.get("name"), "arguments": tool.get("parameters", {})} for tool in expected_tools
        ]

        return LLMTestCase(
            input=test_data["prompt"],
            actual_output=json.dumps(actual_tools_formatted),
            expected_output=json.dumps(expected_tools_formatted),
            tools_used=actual_tools_formatted,
            expected_tools=expected_tools_formatted,
            context=[test_data["category"], test_data["difficulty"]],
        )

    def evaluate_single(self, test_id: str, actual_tools: list[dict]) -> dict[str, Any]:
        """
        Evaluate a single test case using DeepEval.

        Args:
            test_id: Test case ID
            actual_tools: Tools called by LLM

        Returns:
            Dictionary with DeepEval evaluation results
        """
        test_data = self.test_cases[test_id]
        test_case = self.create_test_case(test_id, actual_tools)

        metrics_to_use = [self.tool_correctness_metric]

        # Add category-specific metrics
        if test_data["category"] in ["sequential_workflow", "state_management"]:
            metrics_to_use.append(self.workflow_ordering_metric)

        if test_data["category"] != "error_handling":
            metrics_to_use.append(self.parameter_accuracy_metric)

        # Run evaluation
        results = {}
        for metric in metrics_to_use:
            metric.measure(test_case)
            results[metric.name] = {
                "score": metric.score,
                "success": metric.is_successful(),
                "reason": metric.reason if hasattr(metric, "reason") else None,
            }

        # Calculate overall score
        avg_score = sum(r["score"] for r in results.values()) / len(results)

        return {
            "test_id": test_id,
            "category": test_data["category"],
            "difficulty": test_data["difficulty"],
            "metrics": results,
            "overall_score": avg_score,
            "passed": avg_score >= 0.9,
        }

    def evaluate_all(self, results_file: str, output_file: str | None = None) -> dict[str, Any]:
        """
        Evaluate all test cases from results file using DeepEval.

        Args:
            results_file: JSON file with LLM results
            output_file: Where to save DeepEval report

        Returns:
            Complete evaluation report
        """
        with open(results_file) as f:
            llm_results = json.load(f)

        all_evaluations = []
        test_cases_for_deepeval = []

        print("🔬 Running DeepEval evaluation...")
        for i, (test_id, result_data) in enumerate(llm_results.items(), 1):
            actual_tools = result_data.get("tools_called", [])

            print(f"[{i}/{len(llm_results)}] Evaluating {test_id}...")

            try:
                eval_result = self.evaluate_single(test_id, actual_tools)
                all_evaluations.append(eval_result)

                # Also create test case for batch evaluation
                test_cases_for_deepeval.append(self.create_test_case(test_id, actual_tools))
            except Exception as e:
                print(f"  ⚠️  Error: {e}")
                all_evaluations.append({"test_id": test_id, "error": str(e), "passed": False})

        # Calculate aggregate metrics
        total = len(all_evaluations)
        passed = sum(1 for e in all_evaluations if e.get("passed", False))

        # By category
        category_stats = {}
        for category in [
            "single_tool",
            "sequential_workflow",
            "parallel_execution",
            "state_management",
            "error_handling",
        ]:
            cat_evals = [e for e in all_evaluations if e.get("category") == category]
            if cat_evals:
                category_stats[category] = {
                    "total": len(cat_evals),
                    "passed": sum(1 for e in cat_evals if e.get("passed", False)),
                    "avg_score": sum(e.get("overall_score", 0) for e in cat_evals) / len(cat_evals),
                    "pass_rate": sum(1 for e in cat_evals if e.get("passed", False)) / len(cat_evals),
                }

        # By difficulty
        difficulty_stats = {}
        for diff in ["easy", "medium", "hard"]:
            diff_evals = [e for e in all_evaluations if e.get("difficulty") == diff]
            if diff_evals:
                difficulty_stats[diff] = {
                    "total": len(diff_evals),
                    "passed": sum(1 for e in diff_evals if e.get("passed", False)),
                    "avg_score": sum(e.get("overall_score", 0) for e in diff_evals) / len(diff_evals),
                    "pass_rate": sum(1 for e in diff_evals if e.get("passed", False)) / len(diff_evals),
                }

        report = {
            "framework": "DeepEval",
            "overall": {
                "total_tests": total,
                "passed_tests": passed,
                "pass_rate": passed / total if total > 0 else 0,
                "average_score": sum(e.get("overall_score", 0) for e in all_evaluations) / total if total > 0 else 0,
            },
            "by_category": category_stats,
            "by_difficulty": difficulty_stats,
            "individual_results": all_evaluations,
        }

        # Save report
        if output_file:
            with open(output_file, "w") as f:
                json.dump(report, f, indent=2)
            print(f"\n✅ DeepEval report saved to: {output_file}")

        # Print summary
        self.print_report(report)

        return report

    def print_report(self, report: dict[str, Any]) -> None:
        """Print formatted evaluation report."""
        print("\n" + "=" * 80)
        print("DeepEval Evaluation Report - OpenROAD MCP Benchmark")
        print("=" * 80)
        print("\n📊 Overall Performance:")
        print(f"  Total Tests: {report['overall']['total_tests']}")
        print(f"  Passed: {report['overall']['passed_tests']}")
        print(f"  Pass Rate: {report['overall']['pass_rate']:.1%}")
        print(f"  Average Score: {report['overall']['average_score']:.3f}")

        print("\n📁 By Category:")
        for category, stats in report["by_category"].items():
            emoji = "✅" if stats["pass_rate"] >= 0.9 else "⚠️" if stats["pass_rate"] >= 0.7 else "❌"
            print(
                f"  {emoji} {category:25s}: {stats['pass_rate']:6.1%} "
                f"({stats['passed']}/{stats['total']}) - Avg: {stats['avg_score']:.3f}"
            )

        print("\n📈 By Difficulty:")
        for diff, stats in report["by_difficulty"].items():
            emoji = "✅" if stats["pass_rate"] >= 0.9 else "⚠️" if stats["pass_rate"] >= 0.7 else "❌"
            print(
                f"  {emoji} {diff:10s}: {stats['pass_rate']:6.1%} "
                f"({stats['passed']}/{stats['total']}) - Avg: {stats['avg_score']:.3f}"
            )

        print("=" * 80)


def main() -> None:
    """CLI for running DeepEval evaluation."""
    import argparse

    parser = argparse.ArgumentParser(description="Evaluate OpenROAD MCP benchmark using DeepEval")
    parser.add_argument(
        "--benchmark", type=str, default="openroad_mcp_benchmark.json", help="Path to benchmark JSON file"
    )
    parser.add_argument("--results", type=str, required=True, help="Path to LLM results JSON file")
    parser.add_argument("--output", type=str, default="deepeval_report.json", help="Path to save DeepEval report")

    args = parser.parse_args()

    runner = DeepEvalBenchmarkRunner(args.benchmark)
    runner.evaluate_all(args.results, args.output)


if __name__ == "__main__":
    main()
