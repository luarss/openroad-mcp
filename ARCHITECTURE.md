# OpenROAD MCP Architecture

## Overview

OpenROAD MCP is a Model Context Protocol (MCP) server that provides AI assistants with access to OpenROAD chip design and timing analysis tools through a structured, async API. The system manages multiple concurrent interactive sessions with PTY (pseudo-terminal) support for true terminal emulation.

## Data Flow Diagram

```mermaid
sequenceDiagram
    participant Client as AI Client
    participant MCP as FastMCP Server
    participant Tool as Interactive Tool
    participant Manager as OpenROADManager
    participant SessionMgr as SessionManager
    participant Session as InteractiveSession
    participant PTY as PTY Handler
    participant OR as OpenROAD Process

    Client->>MCP: interactive_openroad(command)
    MCP->>Tool: execute(command, session_id, timeout)

    alt session_id is None
        Tool->>SessionMgr: create_session()
        SessionMgr->>Session: new Session()
        Session->>PTY: create_pty()
        PTY->>OR: spawn openroad process
        PTY-->>Session: process started
        Session-->>SessionMgr: session_id
        SessionMgr-->>Tool: session_id
    end

    Tool->>SessionMgr: execute_command(session_id, command, timeout)
    SessionMgr->>Session: send_command(command)
    Session->>PTY: write(command)
    PTY->>OR: send to stdin

    loop Read output with timeout
        OR->>PTY: output on stdout
        PTY->>Session: buffer output
        Session->>Session: accumulate in buffer
    end

    Session-->>SessionMgr: InteractiveExecResult
    SessionMgr-->>Tool: result
    Tool->>Tool: format_result()
    Tool-->>MCP: formatted JSON
    MCP-->>Client: response
```

## Key Design Patterns

### 1. Singleton Pattern
**OpenROADManager** uses singleton pattern to ensure single subprocess management instance across the application.

### 2. Factory Pattern
**OpenROADManager** acts as a factory for creating and managing InteractiveSession instances.

### 3. Strategy Pattern
**PTYHandler** encapsulates the PTY management strategy, allowing different terminal handling approaches.

### 4. Observer Pattern
Background threads in PTYHandler observe stdout/stderr and notify the session through queues.

### 5. Template Method Pattern
**BaseTool** provides template for tool execution with `_format_result()` and `execute()` methods.

### 6. Lazy Initialization
Interactive session manager is only created when first accessed through the property.
