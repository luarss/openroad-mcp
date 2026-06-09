"""Base data structures and abstract class for benchmark conditions."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..fixture import FixtureSpec


@dataclass
class TurnMetrics:
    turn: int
    condition: str
    run: int  # 0 = warmup, 1..N = measured
    prompt_tokens: int  # total prompt tokens (includes cached portion)
    cached_content_tokens: int  # tokens served from Gemini context cache
    candidates_tokens: int  # output tokens
    latency_ms: float  # wall time for all API calls in this turn
    api_calls: int  # 2 for mcp (tool-call + response), 1 for baseline
    command_name: str

    @property
    def cache_hit_rate(self) -> float:
        return self.cached_content_tokens / self.prompt_tokens if self.prompt_tokens else 0.0

    @property
    def uncached_tokens(self) -> int:
        return self.prompt_tokens - self.cached_content_tokens

    # Used for timing-only sentinel construction
    @staticmethod
    def _wall_time() -> float:
        return time.perf_counter()


@dataclass
class BenchmarkResult:
    condition: str
    model: str
    runs: int
    turns_per_run: int
    all_turn_metrics: list[TurnMetrics] = field(default_factory=list)

    @property
    def measured_metrics(self) -> list[TurnMetrics]:
        return [m for m in self.all_turn_metrics if m.run > 0]

    @property
    def avg_cache_hit_rate(self) -> float:
        m = self.measured_metrics
        return sum(t.cache_hit_rate for t in m) / len(m) if m else 0.0

    @property
    def total_prompt_tokens(self) -> int:
        return sum(t.prompt_tokens for t in self.measured_metrics)

    @property
    def total_cached_tokens(self) -> int:
        return sum(t.cached_content_tokens for t in self.measured_metrics)

    @property
    def avg_latency_ms(self) -> float:
        m = self.measured_metrics
        return sum(t.latency_ms for t in m) / len(m) if m else 0.0


class BenchmarkCondition(ABC):
    def __init__(self, model: str) -> None:
        self.model = model

    @abstractmethod
    async def run(self, runs: int, fixture: FixtureSpec) -> BenchmarkResult:
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        ...
