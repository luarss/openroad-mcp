# OpenROAD MCP Timing Debug Demo Script

**Purpose**: This script guides an AI assistant through a realistic timing debug session using the OpenROAD MCP server.

**Target Audience**: Chip designers, EDA tool users, timing closure engineers

**Duration**: 5-10 minutes

**Prerequisites**:
- OpenROAD MCP server running
- ORFS nangate45/gcd design available
- Constraint files: `tight_constraints.sdc` and `relaxed_constraints.sdc`

---

## Demo Flow Overview

1. **Initial Discovery** - Load design and discover violations
2. **Path Analysis** - Examine critical paths
3. **Root Cause Investigation** - Understand delay sources
4. **Fix Application** - Apply constraint changes
5. **Verification** - Confirm timing closure

---

## Phase 1: Initial Discovery

### User Request:
> "Can you analyze the timing for my GCD design? I'm using a 0.46ns clock period."

### AI Actions:

1. **Use MCP tool**: `mcp__openroad-mcp__create_interactive_session`
   - Note the session_id returned

2. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `read_liberty /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib`
   - session_id: (use session from step 1)

3. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef`

4. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef`

5. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `read_verilog /home/luars/OpenROAD-flow-scripts/flow/results/nangate45/gcd/base/1_synth.v`

6. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `link_design gcd`

7. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `read_sdc /home/luars/openroad-mcp/demo/orfs-gcd-timing/configs/tight_constraints.sdc`

8. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `report_wns`

9. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `report_tns`

### AI Response Template:
```
I've analyzed the timing for your GCD design with a 0.46ns clock period. Here are the results:

🔴 TIMING VIOLATIONS DETECTED

Worst Negative Slack (WNS): [extract from report_wns]
Total Negative Slack (TNS): [extract from report_tns]

The design has significant setup violations. This aggressive clock period
(0.46ns = 2.17 GHz) is too fast for the current implementation.

Would you like me to examine the critical paths to understand what's causing
these violations?
```

---

## Phase 2: Path Analysis

### User Request:
> "Yes, show me the worst timing paths."

### AI Actions:

1. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `report_checks -path_delay max -format full_clock_expanded -fields {capacitance slew input_pins nets fanout} -digits 3`
   - Timeout: 10000ms

### AI Response Template:
```
I found several critical paths. Here are the top violators:

📊 CRITICAL PATH ANALYSIS

Path 1: [extract startpoint] → [extract endpoint]
  Slack: [extract slack]
  Path Group: [extract path_group]

Path 2: [next path info]
  Slack: [slack]
  ...

PATTERN DETECTED:
All failing paths go through the GCD subtraction datapath. These are
combinational paths with [X] logic levels that exceed the 0.46ns constraint.

The paths involve:
- Multi-bit subtraction operations
- Comparison logic
- State machine control

Would you like me to analyze what's contributing to the delay?
```

---

## Phase 3: Root Cause Investigation

### User Request:
> "What's causing these delays? Can you break down the timing?"

### AI Actions:

1. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `report_checks -path_delay max -format full_clock_expanded -path_count 1`

2. Analyze the output for:
   - Number of logic levels
   - Cell delays
   - Wire delays (net delays)
   - Setup time

### AI Response Template:
```
Looking at the critical path in detail:

🔬 DELAY BREAKDOWN

Total path delay: [calculate from data arrival time]
Clock period: 0.46ns
Required slack: [show setup requirement]

Components:
├─ Logic delay: [sum cell delays] ([percentage]%)
│  └─ [X] logic levels through:
│     - Adder/subtractor cells
│     - Comparators
│     - Multiplexers
│
└─ Wire delay: [sum net delays] ([percentage]%)
   └─ Routing through datapath

ROOT CAUSE:
The GCD algorithm requires multi-bit subtraction and comparison in a single
cycle. With [X] logic levels, the combinational delay is ~[Y]ns, which
exceeds the 0.46ns clock constraint by [Z]ns.

OPTIONS:
1. Relax the clock period (easier, slight performance impact)
2. Pipeline the datapath (harder, requires RTL changes)

Would you like me to try fixing this by adjusting the clock period?
```

---

## Phase 4: Fix Application

### User Request:
> "Yes, please adjust the clock period to meet timing."

### AI Actions:

1. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `read_sdc /home/luars/openroad-mcp/demo/orfs-gcd-timing/configs/relaxed_constraints.sdc`
   - Note: This loads the 0.60ns clock constraint

2. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `report_wns`

3. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `report_tns`

### AI Response Template:
```
I'll apply a more realistic clock period. Let me reload with relaxed constraints...

⚙️ APPLYING FIX

Previous constraint: 0.46ns (2.17 GHz)
Updated constraint: 0.60ns (1.67 GHz)
Performance impact: ~23% frequency reduction

Re-running timing analysis...

New results:
WNS: [extract from report_wns]
TNS: [extract from report_tns]

Let me verify this achieved timing closure...
```

---

## Phase 5: Verification

### User Request:
(Continues from Phase 4, or explicitly: "Did we achieve timing closure?")

### AI Actions:

1. **Use MCP tool**: `mcp__openroad-mcp__interactive_openroad`
   - Command: `report_checks -path_delay max -slack_max 0.0`
   - This shows only violations (if any remain)

### AI Response Template:
```
✅ TIMING CLOSURE ACHIEVED!

BEFORE:
  WNS: -1.23ns (12 violations)
  TNS: -8.45ns
  Status: FAILING ❌

AFTER:
  WNS: +0.14ns (0 violations)
  TNS: 0.00ns
  Status: PASSING ✓

SUMMARY:
Your GCD design now meets all timing constraints at 1.67 GHz (0.60ns period).
All setup paths have positive slack. The design is ready for physical
implementation!

The 23% frequency reduction is a reasonable trade-off to achieve timing
closure without RTL changes. If you need higher performance, consider:
- Pipelining the datapath
- Optimizing the critical subtraction logic
- Using faster standard cells
```

---

## Cleanup

### AI Actions:

1. **Use MCP tool**: `mcp__openroad-mcp__terminate_interactive_session`
   - session_id: (session from Phase 1)

---

## Key Points for AI to Emphasize

1. **Educational Value**: Explain *why* violations occur (combinational depth, clock period)
2. **Trade-offs**: Clock period vs. performance, ease vs. effectiveness
3. **Real Data**: Use actual numbers from OpenROAD reports
4. **Professional Tone**: Sound like an experienced timing engineer
5. **Practical Advice**: Suggest realistic solutions

---

## Expected Output Samples

The AI should see outputs like:

**report_wns (with tight constraints):**
```
wns max -1.23
```

**report_tns (with tight constraints):**
```
tns max -8.45
```

**report_wns (with relaxed constraints):**
```
wns max 0.14
```

**report_checks (sample critical path):**
```
Startpoint: dpath.a_reg[15]$_DFFE_PP_
Endpoint: dpath.b_reg[15]$_DFFE_PP_
Path Group: core_clock
Path Type: max

   0.00    0.00   clock core_clock (rise edge)
   ...
   1.69    1.69   data arrival time

   0.46    0.46   clock core_clock (rise edge)
  -0.04    0.42   library setup time
   0.42           data required time
---------
  -1.27           slack (VIOLATED)
```

---

## Notes for AI Assistant

- Be conversational but professional
- Explain technical terms briefly
- Show enthusiasm when timing closes
- Acknowledge trade-offs honestly
- Use bullet points and formatting for clarity
- Extract actual numbers from MCP tool outputs
- Don't make up data - use what OpenROAD reports
