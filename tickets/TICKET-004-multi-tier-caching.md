# TICKET-004: Multi-Tier Caching System

## Description
Implement a multi-tier caching system to achieve 10x performance improvement for timing queries. The system will include an L1 in-memory LRU cache for hot paths, an L2 disk-based cache for pre-computed aggregations, and intelligent cache warming strategies.

## High-Level Specification
- Implement L1 LRUCache for 1000 most accessed timing paths
- Create L2 DiskCache for pre-computed aggregations and results
- Design cache coherency strategy between tiers
- Implement cache warming for predictable access patterns
- Build configurable eviction policies and size management
- Add cache statistics and monitoring

## Relevant Files
- `src/openroad_mcp/timing/cache/l1_cache.py` (to be created)
- `src/openroad_mcp/timing/cache/l2_cache.py` (to be created)
- `src/openroad_mcp/timing/cache/cache_manager.py` (to be created)
- `src/openroad_mcp/timing/cache/policies.py` (to be created)
- `tests/test_caching.py` (to be created)

## Acceptance Criteria
- [ ] L1 cache provides <1ms access for cached paths
- [ ] L2 cache handles 100GB+ of pre-computed data
- [ ] Cache hit rate >80% for common queries
- [ ] Memory usage stays within 500MB limit for L1
- [ ] Cache coherency maintained across tiers
- [ ] Eviction policies prevent memory overflow
- [ ] Cache warming reduces cold start latency
- [ ] Monitoring provides hit/miss statistics

## Implementation Steps
- [ ] Design cache architecture and interfaces
- [ ] Implement L1 LRUCache with size limits
- [ ] Create L2 DiskCache with efficient serialization
- [ ] Build CacheManager to coordinate tiers
- [ ] Implement cache coherency protocol
- [ ] Add eviction policies (LRU, LFU, adaptive)
- [ ] Create cache warming strategies
- [ ] Implement cache statistics collection
- [ ] Add cache persistence for restart
- [ ] Write performance benchmarks

## Priority
High

## Status
Todo

## Dependencies
- TICKET-001: Delta-Compressed Checkpoint System (for persistent storage)
- TICKET-002: Spatial Indexing (for query patterns)

## Technical Details
### Cache Architecture
```python
class CacheManager:
    def __init__(self):
        self.l1_cache = LRUCache(max_size=1000, max_memory="500MB")
        self.l2_cache = DiskCache(path="/tmp/openroad_cache", max_size="100GB")
        self.bloom_filter = BloomFilter(expected_items=1_000_000)

    async def get(self, key: str) -> Optional[TimingPath]:
        # Check bloom filter first (negative cache)
        if not self.bloom_filter.might_contain(key):
            return None

        # Try L1
        if result := self.l1_cache.get(key):
            return result

        # Try L2
        if result := await self.l2_cache.get(key):
            self.l1_cache.put(key, result)  # Promote to L1
            return result

        return None
```

### Cache Warming Strategies
- Pre-load critical paths on startup
- Predictive loading based on access patterns
- Background warming during idle time
- Query-based warming for related paths

### Eviction Policies
- LRU with age-based weight
- Adaptive replacement cache (ARC)
- Size-aware eviction for large objects
- Priority-based retention for critical paths

### Performance Targets
- L1 hit latency: <1ms
- L2 hit latency: <10ms
- Cache miss penalty: <100ms
- Warming time: <30s for common patterns

## Notes
- Consider using Redis for L2 if disk performance insufficient
- Implement cache compression for L2 storage
- Monitor cache effectiveness and adjust sizes
- Support cache sharing across MCP instances
