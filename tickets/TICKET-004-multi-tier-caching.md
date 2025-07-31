# TICKET-004: Multi-Tier Caching System for OpenSTA Queries

## Description
Implement a multi-tier caching system optimized for OpenSTA timing queries to achieve 10x performance improvement. The system will cache OpenSTA command results, timing paths, and pre-computed aggregations with intelligent invalidation based on design changes.

## High-Level Specification
- Implement L1 LRUCache for hot OpenSTA query results
- Create L2 DiskCache for persistent timing reports and aggregations
- Design OpenSTA-aware cache invalidation strategy
- Cache frequently used report_checks outputs
- Implement intelligent cache warming for common timing queries
- Add bloom filters for negative query optimization
- Monitor OpenSTA command patterns for adaptive caching

## Relevant Files
- `src/openroad_mcp/timing/cache/l1_cache.py` (to be created)
- `src/openroad_mcp/timing/cache/l2_cache.py` (to be created)
- `src/openroad_mcp/timing/cache/opensta_cache_manager.py` (to be created)
- `src/openroad_mcp/timing/cache/invalidation.py` (to be created)
- `src/openroad_mcp/timing/cache/policies.py` (to be created)
- `tests/test_caching.py` (to be created)

## Acceptance Criteria
- [ ] L1 cache provides <1ms access for cached OpenSTA results
- [ ] L2 cache handles 100GB+ of timing reports
- [ ] Cache hit rate >80% for repeated OpenSTA queries
- [ ] Memory usage stays within 500MB limit for L1
- [ ] OpenSTA-aware invalidation on design changes
- [ ] Partial result caching for large reports
- [ ] Cache warming from common query patterns
- [ ] Integration with streaming query engine
- [ ] Monitoring provides OpenSTA-specific metrics

## Implementation Steps
- [ ] Design cache architecture for OpenSTA results
- [ ] Implement L1 cache with OpenSTA query keys
- [ ] Create L2 disk cache with compressed storage
- [ ] Build OpenSTA-aware cache manager
- [ ] Implement cache key generation from commands
- [ ] Add invalidation based on design modifications
- [ ] Create partial result caching for streaming
- [ ] Implement cache warming from query history
- [ ] Add bloom filters for path existence checks
- [ ] Write benchmarks with real OpenSTA workloads

## Priority
High

## Status
Todo

## Dependencies
- TICKET-001: Delta-Compressed Checkpoint System (for storage format)
- TICKET-002: Spatial Indexing (for region-based caching)
- TICKET-003: Streaming Query Engine (for partial caching)
- OpenSTA command patterns understanding

## Technical Details
### OpenSTA Cache Architecture
```python
class OpenSTACacheManager:
    def __init__(self):
        self.l1_cache = LRUCache(max_size=10000, max_memory="500MB")
        self.l2_cache = DiskCache(path="/tmp/opensta_cache", max_size="100GB")
        self.bloom_filter = BloomFilter(expected_items=10_000_000)
        self.query_history = QueryPatternAnalyzer()

    async def get_report_checks(self, args: Dict) -> Optional[TimingReport]:
        cache_key = self._generate_cache_key("report_checks", args)

        # Check if paths exist before running command
        if args.get("from") and not self.bloom_filter.might_contain(args["from"]):
            return EmptyReport()  # Fast negative response

        # Multi-tier lookup
        if result := self.l1_cache.get(cache_key):
            return result

        if result := await self.l2_cache.get(cache_key):
            self._promote_to_l1(cache_key, result)
            return result

        return None

    def invalidate_on_change(self, change_type: str, affected_nets: List[str]):
        # Smart invalidation based on OpenSTA dependencies
        if change_type == "placement":
            self._invalidate_spatial_queries(affected_nets)
        elif change_type == "timing_constraint":
            self._invalidate_all_timing()  # Conservative
```

### Cache Key Generation
```python
def _generate_cache_key(self, command: str, args: Dict) -> str:
    # Create deterministic key from OpenSTA command + args
    # Include design checkpoint version for consistency
    normalized_args = self._normalize_args(args)
    key_data = {
        "cmd": command,
        "args": normalized_args,
        "design_version": self.get_design_version(),
        "corner": self.get_active_corner()
    }
    return hashlib.sha256(json.dumps(key_data).encode()).hexdigest()
```

### Partial Result Caching
```python
class StreamingCache:
    def cache_streaming_results(self, query_id: str, chunk: List[TimingPath]):
        # Cache chunks for resumable queries
        chunk_key = f"{query_id}:chunk:{self.chunk_counter}"
        self.l1_cache.put(chunk_key, chunk, ttl=3600)  # 1 hour TTL

    def get_cached_stream(self, query_id: str) -> AsyncIterator[List[TimingPath]]:
        # Resume from cached chunks if available
        chunk_num = 0
        while chunk := self.l1_cache.get(f"{query_id}:chunk:{chunk_num}"):
            yield chunk
            chunk_num += 1
```

### Cache Warming Strategies
```python
class OpenSTACacheWarmer:
    async def warm_critical_paths(self):
        # Pre-compute worst paths for each clock domain
        for clock in self.get_clocks():
            await self.cache_manager.warm_query(
                "report_checks",
                {"clock": clock, "endpoints": 100, "path_delay": "max"}
            )

    async def warm_from_history(self):
        # Analyze query patterns and pre-cache frequent queries
        frequent_queries = self.query_history.get_top_queries(20)
        for query in frequent_queries:
            await self.cache_manager.warm_query(query.command, query.args)
```

### Performance Targets
- L1 hit latency: <1ms for OpenSTA results
- L2 hit latency: <10ms for compressed reports
- Cache miss penalty: Same as OpenSTA execution
- Bloom filter false positive rate: <0.1%
- Cache warming: <60s for top 100 queries

## Notes
- Consider caching at multiple granularities (full report, paths, summaries)
- Implement compression for L2 cache (timing reports compress well)
- Monitor OpenSTA command patterns for adaptive caching
- Support incremental cache updates for ECO flows
- Consider distributed caching for team environments
