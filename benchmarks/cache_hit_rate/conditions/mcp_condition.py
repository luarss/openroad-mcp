"""MCP benchmark condition: Gemini function calling via openroad-mcp server."""

from __future__ import annotations

import asyncio
import os
import time

from google import genai
from google.genai import types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from ..fixture import SYSTEM_INSTRUCTION, FixtureSpec, TurnSpec, run_real_command
from .base import BenchmarkCondition, BenchmarkResult, TurnMetrics


def _convert_mcp_tools(mcp_tools: list) -> list[types.Tool]:  # type: ignore[type-arg]
    """Convert MCP tool schemas to a single Gemini Tool with all function declarations."""
    declarations = []
    for tool in mcp_tools:
        declarations.append(
            types.FunctionDeclaration(
                name=tool.name,
                description=tool.description or "",
                parameters=tool.inputSchema,
            )
        )
    return [types.Tool(function_declarations=declarations)]


class MCPCondition(BenchmarkCondition):
    """Benchmark condition using openroad-mcp with Gemini function calling.

    Cache contains system instruction + all MCP tool schemas.
    Two API calls per turn: (1) user asks → model calls tool, (2) tool result → model responds.
    Token counts from both calls are summed into one TurnMetrics.
    """

    def __init__(self, model: str) -> None:
        super().__init__(model)
        self._cache: types.CachedContent | None = None

    async def run(self, runs: int, fixture: FixtureSpec) -> BenchmarkResult:
        env = {**os.environ, "OPENROAD_WHITELIST_ENABLED": "false"}
        server_params = StdioServerParameters(
            command="python",
            args=["-m", "openroad_mcp.main"],
            env=env,
        )

        client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
        all_metrics: list[TurnMetrics] = []

        try:
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as mcp_session:
                    await mcp_session.initialize()
                    await asyncio.sleep(1.0)

                    tools_result = await mcp_session.list_tools()
                    gemini_tools = _convert_mcp_tools(tools_result.tools)

                    self._cache = await client.aio.caches.create(
                        model=self.model,
                        config=types.CreateCachedContentConfig(
                            system_instruction=SYSTEM_INSTRUCTION,
                            tools=gemini_tools,
                            ttl="3600s",
                        ),
                    )
                    cache = self._cache

                    for run_idx in range(runs + 1):
                        metrics = await self._run_single(
                            client, mcp_session, cache, run_idx, fixture
                        )
                        all_metrics.extend(metrics)

        except RuntimeError as e:
            if "cancel scope" not in str(e):
                raise

        return BenchmarkResult(
            condition="mcp",
            model=self.model,
            runs=runs,
            turns_per_run=len(fixture.api_turns),
            all_turn_metrics=all_metrics,
        )

    async def _run_single(
        self,
        client: genai.Client,
        mcp_session: ClientSession,
        cache: types.CachedContent,
        run_idx: int,
        fixture: FixtureSpec,
    ) -> list[TurnMetrics]:
        contents: list[types.Content] = []
        turn_metrics: list[TurnMetrics] = []

        for turn_spec in fixture.api_turns:
            t0 = time.perf_counter()

            # API call 1: user asks → model decides which tool to call
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_text(turn_spec.user_prompt)],
            ))

            response1 = await client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    cached_content=cache.name,
                    tool_config=types.ToolConfig(
                        function_calling_config=types.FunctionCallingConfig(
                            mode=types.FunctionCallingConfigMode.ANY,
                        )
                    ),
                    max_output_tokens=256,
                ),
            )

            model_parts = response1.candidates[0].content.parts
            contents.append(types.Content(role="model", parts=model_parts))

            # Extract the function call (if any) and run it
            fn_call = next((p.function_call for p in model_parts if p.function_call), None)
            tool_output = self._get_output(fn_call, mcp_session, turn_spec, fixture)
            if asyncio.iscoroutine(tool_output):
                tool_output = await tool_output  # type: ignore[assignment]

            fn_name = fn_call.name if fn_call else turn_spec.tool_name
            contents.append(types.Content(
                role="user",
                parts=[types.Part.from_function_response(
                    name=fn_name,
                    response={"output": tool_output},
                )],
            ))

            # API call 2: model reads tool result and responds with analysis
            response2 = await client.aio.models.generate_content(
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
                parts=response2.candidates[0].content.parts,
            ))

            # Aggregate both calls' usage
            u1 = response1.usage_metadata
            u2 = response2.usage_metadata
            turn_metrics.append(TurnMetrics(
                turn=turn_spec.turn_index,
                condition="mcp",
                run=run_idx,
                prompt_tokens=(u1.prompt_token_count or 0) + (u2.prompt_token_count or 0),
                cached_content_tokens=(u1.cached_content_token_count or 0) + (u2.cached_content_token_count or 0),
                candidates_tokens=(u1.candidates_token_count or 0) + (u2.candidates_token_count or 0),
                latency_ms=elapsed_ms,
                api_calls=2,
                command_name=turn_spec.tool_name,
            ))

        return turn_metrics

    def _get_output(
        self,
        fn_call: types.FunctionCall | None,
        mcp_session: ClientSession,
        turn_spec: TurnSpec,
        fixture: FixtureSpec,
    ) -> str:
        if fixture.dry_run:
            return turn_spec.mock_output
        if os.environ.get("OPENROAD_BIN") and fn_call is None:
            return run_real_command(turn_spec.arguments.get("command", ""))
        if fn_call is not None:
            # Return a coroutine that callers must await
            return self._call_mcp_tool(mcp_session, fn_call)  # type: ignore[return-value]
        return turn_spec.mock_output

    async def _call_mcp_tool(
        self, mcp_session: ClientSession, fn_call: types.FunctionCall
    ) -> str:
        result = await mcp_session.call_tool(fn_call.name, arguments=dict(fn_call.args))
        if result.content and hasattr(result.content[0], "text"):
            return result.content[0].text
        return str(result.content)

    async def cleanup(self) -> None:
        if self._cache is not None:
            client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
            await client.aio.caches.delete(name=self._cache.name)
            self._cache = None
