# TICKET-002: Spatial Indexing for OpenSTA Timing Paths

## Description
Implement a spatial indexing system for OpenSTA timing path queries to achieve sub-100ms query performance on designs with 1M+ instances. This will enable fast lookups of timing paths based on physical location, critical path regions, and geometric constraints. The system will index timing paths extracted from OpenSTA's `report_checks` and correlate them with physical placement data from OpenDB.

## High-Level Specification
- Research and select optimal spatial indexing algorithm (R-tree for timing path bounding boxes)
- Implement SpatialIndex class for geometric timing path queries
- Extract path geometry from OpenDB placement data
- Correlate OpenSTA timing paths with physical locations
- Design indexing strategy for timing endpoints and critical paths
- Create index maintenance during incremental timing updates
- Build spatial query interfaces for region-based timing analysis

## Relevant Files
- `src/openroad_mcp/timing/spatial_index.py` (to be created)
- `src/openroad_mcp/timing/query_engine.py` (to be created)
- `src/openroad_mcp/timing/opensta_spatial.py` (to be created)
- `src/openroad_mcp/tools/timing_query.py` (to be created)
- `src/openroad_mcp/timing/models.py` (extend with spatial data)
- `tests/test_spatial_index.py` (to be created)

## Acceptance Criteria
- [ ] Spatial index achieves <100ms query latency on 1M+ instance designs
- [ ] Integration with OpenSTA path extraction (report_checks -format full)
- [ ] Correlation of timing paths with OpenDB placement coordinates
- [ ] Support for point, range, and region-based queries
- [ ] Index updates complete incrementally without full rebuild
- [ ] Memory usage for index stays within reasonable bounds
- [ ] Support for multi-dimensional queries (slack + physical location)
- [ ] Concurrent read access without blocking write operations
- [ ] Performance benchmarks validate query speed

## Implementation Steps
- [ ] Research spatial indexing algorithms and select R-tree for path regions
- [ ] Design SpatialIndex base class with OpenSTA integration
- [ ] Implement OpenSTA path geometry extraction
- [ ] Create mapping between timing endpoints and physical locations
- [ ] Build R-tree index construction from timing paths
- [ ] Implement query interfaces (point, range, nearest-neighbor, slack-based)
- [ ] Add incremental update on OpenSTA timing updates
- [ ] Optimize memory layout for cache efficiency
- [ ] Create test suite with OpenSTA timing data
- [ ] Benchmark against performance targets on real designs

## Priority
High

## Status
Todo

## Dependencies
- TICKET-001: Delta-Compressed Checkpoint System (for timing data storage)
- OpenSTA timing engine (available in OpenROAD)
- OpenDB placement database

## Technical Details
### OpenSTA Integration
```python
class OpenSTASpatialIndexer:
    def extract_path_geometry(self, path_data: str) -> PathGeometry:
        # Parse report_checks output
        # Extract startpoint/endpoint instances
        # Query OpenDB for placement coordinates
        # Create bounding box for path

    def index_timing_paths(self, slack_threshold: float = None):
        # Run report_checks -endpoints -all
        # Extract paths meeting slack criteria
        # Build spatial index with path geometries
```

### Query Types with OpenSTA Context
```python
# Find critical paths in region
paths = spatial_index.query_critical_paths_in_region(
    x_min=0, y_min=0, x_max=1000, y_max=1000,
    slack_threshold=-0.1  # Critical paths only
)

# Find paths by endpoint location
paths = spatial_index.query_paths_by_endpoint(
    x=100.5, y=200.3, radius=10.0
)

# Find worst paths in each region
worst_paths = spatial_index.query_worst_slack_per_region(
    grid_size=100  # 100x100 grid
)

# Query paths between physical regions
paths = spatial_index.query_inter_region_paths(
    region1_bbox, region2_bbox
)
```

### Performance Targets
- Point queries: <10ms
- Range queries: <50ms
- Critical path queries: <100ms
- Index build from OpenSTA: <30s for 1M instances
- Incremental update after ECO: <1s

### Data Structure
```python
class TimingPathSpatialEntry:
    path_id: str
    startpoint: str  # From OpenSTA
    endpoint: str    # From OpenSTA
    slack: float     # From report_checks
    bbox: BoundingBox  # From OpenDB placement
    path_type: str   # setup/hold
    clock_domain: str  # From OpenSTA
```

## Notes
- Use rtree Python library for R-tree implementation
- Index should be serializable for checkpoint integration
- Consider hierarchical indexing for large designs
- Leverage OpenSTA's incremental timing for efficient updates
- May need separate indices for setup/hold paths
