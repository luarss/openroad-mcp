# Demo Transcript Plan: OpenROAD MCP Integration with ORFS GCD Design

## Demo Overview

A 10-15 minute live demonstration showing AI-guided timing closure debugging using OpenROAD MCP server integrated with OpenROAD-flow-scripts (ORFS) on the GCD/nangate45 design.

**Key Value**: Transform timing closure from manual, time-intensive process into intelligent, conversational workflow using actual production databases.

## Critical Setup Requirements

### Pre-Demo Checklist
1. **ORFS Flow Completion**: Ensure `make DESIGN_CONFIG=flow/designs/nangate45/gcd/config.mk` has been run
2. **MCP Server Running**: Verify OpenROAD MCP server is operational
3. **Constraint Files**: Validate SDC files have correct port mappings (see Section 2.3)

### Known Issues & Solutions
- **SDC Constraint Warning**: Original constraint files use `[all_inputs]` which includes clock port
- **Solution**: Use specific port lists excluding clock: `{req_msg req_val reset resp_rdy}` for inputs
- **Port Mapping**: Verify GCD design ports before demo:
  - **Inputs**: `clk, req_msg[31:0], req_val, reset, resp_rdy`
  - **Outputs**: `req_rdy, resp_msg[15:0], resp_val`

## Demo Flow Structure

### Phase 1: ORFS Integration (2-3 minutes)

**Narrator:** "First, let's verify our OpenROAD-flow-scripts GCD design artifacts"

**Actions:**
- Show pre-generated ORFS artifacts:
  ```bash
  ls -la /home/luars/OpenROAD-flow-scripts/flow/results/nangate45/gcd/base/
  ```
- Highlight key files:
  - `1_synth.v` (56KB) - Synthesized netlist for timing analysis
  - `6_final.odb` (1.2MB) - Final routed design
  - `6_final.spef` (492KB) - Extracted parasitics
  - `6_final.sdc` (5.7KB) - Final timing constraints

**Talking Points:**
- "These are real production databases from complete RTL-to-GDS flow"
- "We'll use the synthesized netlist for timing analysis due to schema compatibility"
- "ORFS provides industrial-strength nangate45 technology integration"

### Phase 2: MCP Server Database Loading (3-4 minutes)

**Narrator:** "Now let's load the ORFS-generated design into OpenROAD via MCP"

**Demo Commands (Verified Working):**
```tcl
# Create interactive session
# Session created via MCP: demo-session

# Technology setup (required first)
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef
read_liberty /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib

# Design import
read_verilog /home/luars/OpenROAD-flow-scripts/flow/results/nangate45/gcd/base/1_synth.v
link_design gcd

# Load baseline timing constraints
read_sdc /home/luars/OpenROAD-flow-scripts/flow/results/nangate45/gcd/base/6_final.sdc

# Initial timing check
report_checks -digits 3
```

**Expected Output (Verified):**
```
Startpoint: dpath.a_reg.out[10]$_DFFE_PP_
            (rising edge-triggered flip-flop clocked by core_clock)
Endpoint: dpath.b_reg.out[10]$_DFFE_PP_
          (rising edge-triggered flip-flop clocked by core_clock)
Path Group: core_clock
Path Type: max

   Delay     Time   Description
-----------------------------------------------------------
   0.000    0.000   clock core_clock (rise edge)
   0.000    0.000   clock network delay (propagated)
   0.000    0.000 ^ dpath.a_reg.out[10]$_DFFE_PP_/CK (DFF_X1)
   0.094    0.094 ^ dpath.a_reg.out[10]$_DFFE_PP_/Q (DFF_X1)
   ...
   0.000    0.381 v dpath.b_reg.out[10]$_DFFE_PP_/D (DFF_X1)
            0.381   data arrival time

   0.460    0.460   clock core_clock (rise edge)
   0.000    0.460   clock network delay (propagated)
  -0.040    0.420   library setup time
            0.420   data required time
-----------------------------------------------------------
            0.420   data required time
           -0.381   data arrival time
-----------------------------------------------------------
            0.039   slack (MET)
```

**Key Achievements:**
- Clean technology library loading
- Successful netlist import and linking
- Baseline timing: **+39ps slack** (design meets timing)

### Phase 3: Violation Injection & AI Analysis (4-5 minutes)

**Narrator:** "Let's create timing violations using corrected aggressive constraints"

**Critical Fix Applied:**
Instead of using problematic constraint files, apply constraints manually to avoid warnings:

```tcl
# Create aggressive clock constraints (corrected approach)
create_clock -name core_clock -period 4.0 [get_ports clk]
set_clock_uncertainty 0.2 [get_clocks core_clock]

# Apply I/O constraints with correct port mapping
set_input_delay -clock core_clock -max 3.5 [get_ports {req_msg req_val reset resp_rdy}]
set_output_delay -clock core_clock -max 3.5 [get_ports {req_rdy resp_msg resp_val}]

# Check for violations
report_checks -path_delay max -slack_max 0.0
```

**Expected Violation (Verified):**
```
Startpoint: dpath.a_reg.out[10]$_DFFE_PP_
            (rising edge-triggered flip-flop clocked by core_clock)
Endpoint: resp_msg[15] (output port clocked by core_clock)
Path Group: core_clock
Path Type: max

  Delay    Time   Description
---------------------------------------------------------
   0.00    0.00   clock core_clock (rise edge)
   0.00    0.00   clock network delay (ideal)
   ...
   0.00    0.32 ^ resp_msg[15] (out)
           0.32   data arrival time

   4.00    4.00   clock core_clock (rise edge)
   0.00    4.00   clock network delay (ideal)
  -0.20    3.80   clock uncertainty
  -3.50    0.30   output external delay
           0.30   data required time
---------------------------------------------------------
           0.30   data required time
          -0.32   data arrival time
---------------------------------------------------------
          -0.02   slack (VIOLATED)
```

**AI Analysis Script:**

**👤 User:** "Analyze the timing violations in this GCD design"

**🤖 AI:** "I found timing violations with worst slack **-0.02ns**. Analysis shows:

- **Critical Path**: `dpath.a_reg.out[10]` → `resp_msg[15]` (output port)
- **Path Delay**: 0.32ns through combinational logic
- **Available Time**: 0.30ns (4.0ns clock - 3.5ns output delay - 0.2ns uncertainty)
- **Root Cause**: Aggressive I/O timing constraints (3.5ns output delay = 87.5% of clock period)"

**👤 User:** "What fixes do you recommend?"

**🤖 AI:** "Recommended fixes:
1. **Increase clock period**: 4.0ns → 5.0ns (250MHz → 200MHz)
2. **Relax output delay**: 3.5ns → 1.0ns (realistic I/O timing)
3. **Reduce clock uncertainty**: 0.2ns → 0.1ns

Would you like me to apply these fixes?"

### Phase 4: AI-Guided Timing Closure (3-4 minutes)

**Narrator:** "Watch AI apply intelligent fixes and achieve timing closure"

**🤖 AI Actions (Verified Working):**
```tcl
# Apply AI-recommended fixes
create_clock -name core_clock -period 5.0 [get_ports clk]
set_clock_uncertainty 0.1 [get_clocks core_clock]
set_output_delay -clock core_clock -max 1.0 [get_ports {req_rdy resp_msg resp_val}]

# Verify timing closure
report_checks -digits 3
report_checks -path_delay max -slack_max 0.0
```

**✅ Verified Results:**
```
# No violations found - all paths meet timing
Startpoint: req_msg[0] (input port clocked by core_clock)
Endpoint: dpath.b_reg.out[0]$_DFFE_PP_
          (rising edge-triggered flip-flop clocked by core_clock)
...
            1.269   slack (MET)
```

**🤖 AI:** "**Timing Closure Achieved!**

**Results:**
- All setup violations cleared
- Worst slack: **+1.27ns** (positive margin)
- Clock frequency: 200MHz operation verified
- Design ready for integration"

### Phase 5: Cross-Domain Analysis (2-3 minutes)

**Narrator:** "Demonstrate comprehensive design analysis capabilities"

**Advanced Commands:**
```tcl
# Path group analysis
report_checks -group_count 10

# Detailed timing with physical metrics
report_checks -path_delay max -fields {slew cap fanout}

# Design utilization
report_design_area
```
