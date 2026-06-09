"""Baseline benchmark condition: plain-text output injection, no MCP server."""

from __future__ import annotations

import os
import time

from google import genai
from google.genai import types

from ..fixture import SYSTEM_INSTRUCTION, FixtureSpec, TurnSpec, run_real_command
from .base import BenchmarkCondition, BenchmarkResult, TurnMetrics


class BaselineCondition(BenchmarkCondition):
    """Injects OpenROAD outputs as plain text in user messages.

    Cache contains only the system instruction. No tool schemas.
    One API call per turn.
    """

    def __init__(self, model: str) -> None:
        super().__init__(model)
        self._cache: types.CachedContent | None = None

    async def run(self, runs: int, fixture: FixtureSpec) -> BenchmarkResult:
        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

        self._cache = await client.aio.caches.create(
            model=self.model,
            config=types.CreateCachedContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                ttl="3600s",
            ),
        )

        cache = self._cache
        assert cache is not None

        all_metrics: list[TurnMetrics] = []
        for run_idx in range(runs + 1):
            metrics = await self._run_single(client, cache, run_idx, fixture)
            all_metrics.extend(metrics)

        return BenchmarkResult(
            condition="baseline",
            model=self.model,
            runs=runs,
            turns_per_run=len(fixture.api_turns),
            all_turn_metrics=all_metrics,
        )

    async def _run_single(
        self,
        client: genai.Client,
        cache: types.CachedContent,
        run_idx: int,
        fixture: FixtureSpec,
    ) -> list[TurnMetrics]:
        contents: list[types.Content] = []
        turn_metrics: list[TurnMetrics] = []

        for turn_spec in fixture.api_turns:
            tool_output = self._get_output(turn_spec, fixture.dry_run)

            user_text = f"{turn_spec.user_prompt}\n\n[OpenROAD output]:\n{tool_output}"
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(user_text)],
            ))

            t0 = time.perf_counter()
            response = await client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    cached_content=cache.name,
                    max_output_tokens=512,
                ),
            )
            elapsed_ms = (time.perf_counter() - t0) * 1000

            contents.append(types.Content(
                role="model",
                parts=response.candidates[0].content.parts,
            ))

            u = response.usage_metadata
            turn_metrics.append(TurnMetrics(
                turn=turn_spec.turn_index,
                condition="baseline",
                run=run_idx,
                prompt_tokens=u.prompt_token_count or 0,
                cached_content_tokens=u.cached_content_token_count or 0,
                candidates_tokens=u.candidates_token_count or 0,
                latency_ms=elapsed_ms,
                api_calls=1,
                command_name=turn_spec.tool_name,
            ))

        return turn_metrics

    def _get_output(self, turn_spec: TurnSpec, dry_run: bool) -> str:
        if not dry_run and os.environ.get("OPENROAD_BIN"):
            return run_real_command(turn_spec.arguments.get("command", ""))
        return turn_spec.mock_output

    async def cleanup(self) -> None:
        if self._cache is not None:
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            await client.aio.caches.delete(name=self._cache.name)
            self._cache = None
