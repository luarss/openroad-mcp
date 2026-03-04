# OpenROAD MCP: Let AI Close Your Timing

## Abstract

Timing closure remains one of the most time-consuming aspects of digital design, often requiring engineers to manually analyze critical paths, iterate on SDC constraints, and repeatedly run the implementation flow. This talk introduces OpenROAD MCP, a Model Context Protocol server that enables AI assistants to interact directly with OpenROAD through natural language.

OpenROAD MCP bridges large language models with the OpenROAD RTL-to-GDS flow using Linux pseudo-terminals (PTY) for authentic terminal emulation. The server exposes tools for session management, Tcl command execution, and design visualization, allowing engineers to query timing reports, analyze violations, and iterate on constraints conversationally.

A key design feature is the permission-ask security model: safe commands execute immediately while potentially destructive operations require explicit user approval. This approach balances AI-assisted productivity with user control.

This presentation demonstrates OpenROAD MCP through a practical timing closure workflow and discusses its applicability for engineers learning EDA tools, senior designers debugging complex designs, and researchers exploring AI-assisted hardware design.

---

**Format:** 10 minutes (including questions)

**Presenter:** Jack Luar

**Keywords:** OpenROAD, MCP, AI, EDA, chip design, open source
