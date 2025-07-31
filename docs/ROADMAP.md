# ROADMAP

## Overview

OpenROAD MCP Server is a Model Context Protocol implementation that provides AI assistants with access to OpenROAD's chip design and timing analysis tools. The server enables efficient timing queries, checkpoint/restore functionality, and comprehensive metrics extraction across all OpenROAD flow stages.

### Key Features
- MCP interface to OpenROAD commands with async execution
- Delta-compressed checkpoint/restore for timing data
- Spatial indexing for sub-100ms timing queries on large designs
- Multi-tier caching for performance optimization
- Concurrent query support without blocking main flow

## Development Workflow

1. **Task Planning**
   - Study the existing codebase and understand the current state
   - Use the **planner** agent to break down complex problems and create implementation roadmaps
   - Create a plan document in the `/plans` directory for complex features
   - Update `ROADMAP.md` to include the new task under Development
   - Priority tasks should be inserted after the last completed task

2. **Ticket Creation**
   - Study the existing codebase and understand the current state
   - Create a new ticket file in the `/tickets` directory
   - Name format: `TICKET-XXX-description.md` (e.g., `TICKET-001-user-auth.md`)
   - Include high-level specifications, relevant files, acceptance criteria, and implementation steps
   - Refer to last completed ticket in the `/tickets` directory for examples
   - Note that completed tickets show checked boxes and summary of changes
   - For new tickets, use empty checkboxes and no summary section

3. **Task Implementation**
   - Use the **coder** agent for implementing features, fixing bugs, and optimizing code
   - Follow the specifications in the ticket file
   - Implement features and functionality following project conventions
   - Update step progress within the ticket file after each step
   - Stop after completing each step and wait for further instructions

4. **Quality Assurance**
   - Use the **checker** agent for testing, security analysis, and code review
   - Verify all acceptance criteria are met
   - Run tests and ensure code quality standards
   - Document any issues found and their resolutions

5. **Roadmap Updates**
   - Mark completed tasks with ✅ in the roadmap
   - Add reference to the ticket file (e.g., `See: /tickets/TICKET-001-user-auth.md`)
   - Update related plan documents if applicable

## Development

### Project Setup and Boilerplate ✅
- [x] Create Claude Code boilerplate structure ✅
  - Set up CLAUDE.md with project instructions
  - Create agents directory with planner, coder, and checker agents
  - Establish docs, plans, and tickets directories
  - Add README files to all directories

### Core MCP Server Implementation ✅
- [x] Implement FastMCP server structure ✅
  - Set up FastMCP integration with tool registration
  - Create OpenROADManager for process lifecycle
  - Implement async architecture with proper cleanup
  - Add Pydantic models for data structures
- [x] Add CLI interface ✅
  - Implement argument parsing with transport options
  - Add verbose and log-level configuration
  - Create validation for transport-specific options
  - Add comprehensive CLI tests
- [x] Create MCP tools ✅
  - execute_openroad_command: Execute commands with timeout
  - get_openroad_status: Get process status
  - restart_openroad: Restart the process
  - get_command_history: View command history
  - get_openroad_context: Get comprehensive context
- [x] Add integration tests ✅
  - Test execute_command functionality
  - Add pytest fixtures for async testing
  - Implement MCP integration tests

### Phase 1: Core Timing Query Infrastructure (IN PROGRESS)
- [ ] Task 1-3: Core MCP Server Implementation ✅ (Completed above)
- [ ] Task 4: Delta-Compressed Checkpoint System Architecture
  - Design TimingStage data structure
  - Implement CompressedDelta format
  - Create checkpoint versioning system
  - See: PHASE1_TODO.md for detailed breakdown
- [ ] Task 5: Spatial Indexing Implementation
  - Research and select indexing algorithm
  - Implement SpatialIndex class
  - Optimize for sub-100ms queries
- [ ] Task 6: Streaming Query Engine
  - Design streaming architecture
  - Implement result streaming
  - Create pagination system
- [ ] Task 7: Multi-Tier Caching System
  - Implement L1 LRUCache
  - Create L2 DiskCache
  - Design cache coherency strategy

### Phase 2: Advanced Timing Analysis (PLANNED)
- [ ] Multi-Stage Path Tracking with OpenSTA Integration
- [ ] Enhanced Query Capabilities
- [ ] Hierarchical path queries
- [ ] Multi-corner analysis integration
- [ ] What-if analysis capabilities

### Phase 3: Comprehensive Metrics System (PLANNED)
- [ ] Automated Metrics Collection
- [ ] Timing metrics: WNS, TNS, critical paths
- [ ] Clock analysis: skew and jitter
- [ ] Physical metrics: area, congestion
- [ ] Optimized Metrics Storage & Export

### Phase 4: Integration & Optimization (PLANNED)
- [ ] GUI Integration with OpenROAD
- [ ] External Tool Integration APIs
- [ ] Performance Optimization
- [ ] Documentation and Examples

## Current Status

**Active Development**: Phase 1 - Core Timing Query Infrastructure
- Basic MCP server is operational with 5 core tools
- CLI interface implemented with full test coverage
- Working on timing checkpoint and spatial indexing features
- See TIMING_TODO.md and PHASE1_TODO.md for detailed requirements

## Technical Stack

- **Language**: Python 3.13+
- **MCP Framework**: FastMCP 2.10.6+
- **Type Checking**: mypy with strict settings
- **Linting**: ruff
- **Testing**: pytest with async support
- **Process Management**: asyncio subprocess

## Testing Strategy

- Unit tests for all components
- Integration tests for MCP functionality
- CLI tests for command-line interface
- Performance benchmarks for timing queries
- Stress tests for concurrent access

## Next Steps

1. Implement timing checkpoint system (Task 4)
2. Add spatial indexing for fast queries (Task 5)
3. Create streaming query engine (Task 6)
4. Build multi-tier caching (Task 7)
5. Integrate OpenSTA timing commands (Tasks 8-14)

## Future Enhancements

- HTTP transport support for remote access
- WebSocket support for real-time updates
- Plugin system for custom timing analysis
- Machine learning integration for optimization
- Cloud deployment support

## Completed Tasks Archive

### Initial Development (January 2025)
- Created project structure and boilerplate
- Implemented core MCP server with FastMCP
- Added CLI interface with transport options
- Created 5 core MCP tools for OpenROAD interaction
- Added comprehensive test suite
- Set up development tooling (make, uv, ruff, mypy)
