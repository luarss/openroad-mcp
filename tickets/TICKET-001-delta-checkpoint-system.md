# TICKET-001: Delta-Compressed Checkpoint System with OpenSTA Integration

## Description
Implement a delta-compressed checkpoint system for efficient OpenSTA timing data storage and retrieval. This system will reduce checkpoint sizes from ~500MB to ~50MB by storing only incremental changes between timing stages, enabling faster save/restore operations and reduced storage requirements. The system will capture and compress OpenSTA timing analysis results including path data, slack values, and timing constraints.

## High-Level Specification
- Design TimingStage data structure to capture OpenSTA timing state
- Create CompressedDelta format for storing incremental timing changes
- Implement checkpoint versioning for rollback capabilities
- Build compression pipeline using LZ4/Zstd algorithms
- Integrate with OpenSTA commands for timing data extraction
- Develop checkpoint validation and integrity checking

## Relevant Files
- `src/openroad_mcp/timing/checkpoint.py` (to be created)
- `src/openroad_mcp/timing/models.py` (to be created)
- `src/openroad_mcp/timing/compression.py` (to be created)
- `src/openroad_mcp/timing/opensta_wrapper.py` (to be created)
- `src/openroad_mcp/core/manager.py` (integration point)
- `tests/test_checkpoint.py` (existing test file)

## Acceptance Criteria
- [ ] TimingStage captures OpenSTA timing state (paths, slack, constraints)
- [ ] CompressedDelta format achieves 90% size reduction on timing data
- [ ] Checkpoint creation completes within 10 seconds for 1M instance designs
- [ ] Restore operations maintain timing accuracy with validation
- [ ] Versioning system allows rollback to previous timing states
- [ ] Integration with OpenSTA commands (report_checks, get_timing_edges)
- [ ] Support for multi-corner timing data compression
- [ ] Unit tests achieve 95% coverage
- [ ] Performance benchmarks validate size and speed requirements

## Implementation Steps
- [ ] Create timing module structure and base models
- [ ] Design TimingStage to capture OpenSTA timing data
- [ ] Implement OpenSTA command wrappers for data extraction
- [ ] Build compression algorithms optimized for timing data patterns
- [ ] Implement checkpoint creation with delta calculation
- [ ] Create restore functionality with timing state reconstruction
- [ ] Add versioning and rollback capabilities
- [ ] Integrate validation against OpenSTA report_checks output
- [ ] Connect with OpenROADManager for timing persistence
- [ ] Write comprehensive unit tests with timing data fixtures
- [ ] Perform benchmarking on reference designs

## Priority
High

## Status
Todo

## Dependencies
- OpenROAD process management (completed)
- Basic MCP server infrastructure (completed)
- OpenSTA timing engine (available in OpenROAD)

## Technical Details
### Data Structure Design
```python
class TimingStage:
    stage_id: str
    timestamp: datetime
    base_checkpoint_ref: str  # Reference to shared base state
    delta_changes: CompressedDelta  # Only incremental changes
    timing_index: SpatialIndex  # For fast path queries
    opensta_state: Dict[str, Any]  # Constraints, clocks, etc
    metadata: Dict[str, Any]
```

### OpenSTA Integration
```python
class OpenSTAExtractor:
    def extract_timing_paths(self) -> List[TimingPath]:
        # Use report_checks -format full

    def extract_timing_constraints(self) -> Dict[str, Any]:
        # Use report_clock_properties, get_clocks

    def extract_slack_histogram(self) -> Dict[str, float]:
        # Use report_timing_histogram
```

### Compression Strategy
- Use LZ4 for speed-critical timing path data
- Use Zstd for maximum compression on constraint data
- Implement domain-specific compression for timing values
- Delta encoding for slack values between stages

## Notes
- This is the foundation for all timing query operations
- Must maintain compatibility with OpenSTA data formats
- Consider memory-mapped files for large timing databases
- Implement streaming compression for memory efficiency
- Leverage OpenSTA's incremental timing update capabilities
