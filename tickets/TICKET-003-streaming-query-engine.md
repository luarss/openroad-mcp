# TICKET-003: Streaming Query Engine for OpenSTA Commands

## Description
Implement a streaming query engine for memory-efficient processing of large OpenSTA command outputs. This engine will enable real-time streaming and parsing of massive timing analysis results without memory overflow, supporting commands like `report_checks`, `report_timing_histogram`, and `get_fanin/fanout` on designs with millions of paths.

## High-Level Specification
- Design streaming architecture for OpenSTA command execution
- Implement real-time parsing of OpenSTA text output formats
- Create pagination system for MCP client-controlled data flow
- Build streaming parsers for various OpenSTA report formats
- Implement backpressure handling for slow consumers
- Support async iteration patterns for Python integration
- Enable progressive filtering during streaming

## Relevant Files
- `src/openroad_mcp/timing/stream_engine.py` (to be created)
- `src/openroad_mcp/timing/opensta_stream_parser.py` (to be created)
- `src/openroad_mcp/timing/pagination.py` (to be created)
- `src/openroad_mcp/tools/timing_stream.py` (new MCP tool)
- `src/openroad_mcp/core/manager.py` (integrate streaming)
- `tests/test_streaming.py` (to be created)

## Acceptance Criteria
- [ ] Stream processing handles 1M+ timing paths without memory overflow
- [ ] Memory usage stays under 500MB regardless of result size
- [ ] Real-time parsing of OpenSTA report_checks output
- [ ] Pagination provides smooth navigation through large datasets
- [ ] Backpressure prevents buffer overflow with slow MCP clients
- [ ] Support for all major OpenSTA report formats
- [ ] Progressive filtering reduces transmitted data volume
- [ ] Cancellation support for long-running OpenSTA commands
- [ ] Error recovery without losing streamed data

## Implementation Steps
- [ ] Design streaming architecture for OpenSTA integration
- [ ] Implement OpenSTAStreamExecutor with subprocess pipes
- [ ] Create parsers for report_checks, timing_histogram formats
- [ ] Build StreamBuffer with ring buffer implementation
- [ ] Implement pagination with cursor-based navigation
- [ ] Add progressive filtering (slack, path_group, clock)
- [ ] Create backpressure handling with asyncio.Queue
- [ ] Implement stream transformation operators
- [ ] Add cancellation and cleanup for OpenSTA processes
- [ ] Write stress tests with large timing reports

## Priority
High

## Status
Todo

## Dependencies
- Basic MCP server infrastructure (completed)
- OpenSTA command knowledge (completed research)
- TICKET-002: Spatial indexing (for filtered streaming)

## Technical Details
### OpenSTA Streaming Architecture
```python
class OpenSTAStreamExecutor:
    async def stream_command(self, command: str) -> TimingStream:
        # Execute OpenSTA command with subprocess
        # Return stream that parses output in real-time

    async def stream_report_checks(
        self,
        endpoints: int = None,
        path_delay: str = "max",
        slack_threshold: float = None
    ) -> TimingPathStream:
        # Stream report_checks with filters
```

### Parser Implementation
```python
class OpenSTAStreamParser:
    async def parse_report_checks(self, stream: AsyncIterator[str]):
        # Parse report_checks line by line
        # Yield TimingPath objects as completed

    async def parse_timing_histogram(self, stream: AsyncIterator[str]):
        # Parse histogram data progressively

    async def parse_fanin_fanout(self, stream: AsyncIterator[str]):
        # Parse get_fanin/get_fanout results
```

### Memory Management
- Fixed 10MB buffer per stream
- Ring buffer with 1000-path chunks
- Automatic garbage collection of processed chunks
- Memory-mapped files for extremely large results

### Progressive Filtering
```python
class FilteredTimingStream:
    def __init__(self, base_stream, filters):
        self.filters = filters  # slack, region, clock_domain

    async def __anext__(self):
        while True:
            path = await self.base_stream.__anext__()
            if self.matches_filters(path):
                return path
```

### MCP Tool Interface
```python
@mcp_tool
async def stream_timing_analysis(
    command: str,
    page_size: int = 1000,
    filters: Dict[str, Any] = None
) -> AsyncIterator[List[TimingPath]]:
    # Execute OpenSTA command with streaming
    # Apply filters progressively
    # Return paginated results
```

### Backpressure Strategy
- asyncio.Queue with maxsize=100 chunks
- Pause OpenSTA process when queue full
- Resume when queue drops below 50%
- Configurable high/low watermarks

## Notes
- Consider subprocess.PIPE for real-time OpenSTA output
- Support TCL list format parsing for structured data
- May need custom protocol for binary OpenDB data
- Consider compression for network transport
- Implement retry logic for transient parse errors
