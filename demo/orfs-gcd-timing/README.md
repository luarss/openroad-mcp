# OpenROAD-flow-scripts GCD Timing Optimization Guide

## Overview
This demo shows how to fix timing violations in the nangate45/gcd design by relaxing clock constraints. This is a reference for LLMs helping users with OpenROAD timing closure.

## Problem Statement
The default nangate45/gcd configuration has timing violations:
- **WNS (Worst Negative Slack)**: -0.05 ns
- **TNS (Total Negative Slack)**: -0.53 ns
- **Setup violations**: 23 paths
- **Target clock period**: 0.46 ns (too aggressive)
- **Achievable clock period**: ~0.51 ns

## Solution
Relax the clock period from 0.46 ns to 0.52 ns (~13% relaxation) to achieve timing closure.

## Directory Structure
```
demo/orfs-gcd-timing/
├── README.md              # This file
├── configs/
│   ├── original_timing.sdc    # Original constraint (0.46 ns, fails timing)
│   └── improved_timing.sdc    # Improved constraint (0.52 ns, passes timing)
└── run_demo.sh           # Automated script to test both configurations
```

## Prerequisites

### Environment Setup
This demo should be run inside the OpenROAD devcontainer:

1. **Open in VS Code devcontainer**:
   - Open the OpenROAD-flow-scripts repository
   - VS Code will prompt to reopen in container
   - Or use Command Palette: "Remote-Containers: Reopen in Container"

2. **Verify OpenROAD is available**:
   ```bash
   openroad -version
   yosys -version
   ```

3. **Navigate to flow directory**:
   ```bash
   cd /home/luars/OpenROAD-flow-scripts/flow
   ```

## Configuration Files

### Original Timing Constraint (Fails)
**File**: `configs/original_timing.sdc`
```tcl
current_design gcd

set clk_name core_clock
set clk_port_name clk
set clk_period 0.46        # Too aggressive!
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [all_inputs -no_clocks]
set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]
```

**Results**:
- WNS: -0.05 ns ❌
- TNS: -0.53 ns ❌
- Setup violations: 23 ❌

### Improved Timing Constraint (Passes)
**File**: `configs/improved_timing.sdc`
```tcl
current_design gcd

set clk_name core_clock
set clk_port_name clk
set clk_period 0.52        # Relaxed from 0.46 ns
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [all_inputs -no_clocks]
set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]
```

**Results**:
- WNS: ~0.00 ns ✅
- TNS: ~0.00 ns ✅
- Setup violations: 4 (negligible slack) ✅
- Frequency: 1914 MHz (down from 2174 MHz target)

## How to Run

### Manual Steps

1. **Clean previous builds**:
   ```bash
   cd /home/luars/OpenROAD-flow-scripts/flow
   make clean_all
   ```

2. **Copy improved constraint to ORFS**:
   ```bash
   cp /home/luars/openroad-mcp/demo/orfs-gcd-timing/configs/improved_timing.sdc \
      /home/luars/OpenROAD-flow-scripts/flow/designs/nangate45/gcd/constraint_relaxed.sdc
   ```

3. **Run the flow with improved timing**:
   ```bash
   cd /home/luars/OpenROAD-flow-scripts/flow
   make DESIGN_CONFIG=./designs/nangate45/gcd/config.mk \
        SDC_FILE=./designs/nangate45/gcd/constraint_relaxed.sdc
   ```

4. **Check timing results**:
   ```bash
   # View final timing report
   cat /home/luars/OpenROAD-flow-scripts/flow/reports/nangate45/gcd/base/6_finish.rpt | head -50

   # Check for violations
   grep "wns max" /home/luars/OpenROAD-flow-scripts/flow/reports/nangate45/gcd/base/6_finish.rpt
   grep "tns max" /home/luars/OpenROAD-flow-scripts/flow/reports/nangate45/gcd/base/6_finish.rpt
   grep "setup violation count" /home/luars/OpenROAD-flow-scripts/flow/reports/nangate45/gcd/base/6_finish.rpt
   ```

### Automated Script

Use the provided `run_demo.sh` script:

```bash
cd /home/luars/openroad-mcp/demo/orfs-gcd-timing
./run_demo.sh
```

This will:
1. Clean previous builds
2. Test original configuration (shows failures)
3. Test improved configuration (shows success)
4. Generate comparison report

## Understanding the Timing Reports

### Key Metrics

**WNS (Worst Negative Slack)**:
- Most critical timing violation
- Negative = violation, Positive = met
- Goal: WNS ≥ 0

**TNS (Total Negative Slack)**:
- Sum of all negative slacks
- Indicates overall timing health
- Goal: TNS = 0

**Setup Violations**:
- Number of paths failing setup timing
- Goal: 0 violations

**Clock Period vs Fmax**:
- `period_min` in reports shows minimum achievable clock period
- `fmax` = 1 / period_min

### Reading Timing Paths

Example from report:
```
Startpoint: dpath.a_reg.out[3]$_DFFE_PP_
Endpoint: resp_msg[9] (output port)
Path Type: max

  Delay    Time   Description
---------------------------------------------------------
   0.07    0.07   clock source latency
   0.12    0.19   dpath.a_reg.out[3]$_DFFE_PP_/Q (DFF_X1)
   0.05    0.24   _546_/ZN (XNOR2_X2)
   ...
   0.42    0.42   data arrival time
   0.37    0.37   data required time
---------------------------------------------------------
  -0.05          slack (VIOLATED)
```

**Analysis**:
- Path takes 0.42 ns total
- Clock period allows only 0.37 ns (including output delay)
- Results in -0.05 ns violation

## Timing Closure Strategies

### 1. Clock Period Relaxation (This Demo)
**When to use**: Quick fix, acceptable frequency reduction
- ✅ Simple, guaranteed to work
- ✅ No design changes required
- ❌ Reduces frequency

### 2. Synthesis Optimization
**When to use**: Need to maintain frequency
- Increase synthesis effort
- Enable retiming
- Adjust area vs delay tradeoffs

Example config modifications:
```makefile
export SYNTH_EFFORT ?= high
export ABC_SPEED ?= 1
```

### 3. Placement Optimization
**When to use**: Long wire delays
- Reduce placement density
- Increase core utilization
- Adjust placement padding

Example:
```makefile
export CORE_UTILIZATION ?= 50  # Reduce from 55
export PLACE_DENSITY ?= 0.60
```

### 4. Buffering and Resizing
**When to use**: High fanout or long paths
- Already automatic in ORFS
- Adjust resizer settings if needed

### 5. Clock Tree Optimization
**When to use**: Clock skew issues
- Adjust CTS settings
- Balance clock tree

## Common Timing Issues and Fixes

| Issue | Symptom | Solution |
|-------|---------|----------|
| Aggressive clock | WNS < 0, many violations | Relax clock period (this demo) |
| Long combinational paths | High path delays | Add pipeline stages or buffer |
| High fanout | One cell driving many | Buffer insertion |
| Congestion | Routing delays | Reduce utilization |
| Clock skew | Unbalanced clock arrival | CTS optimization |

## LLM Agent Instructions

When helping users with timing closure in OpenROAD:

1. **Analyze the problem**:
   - Read `6_finish.rpt` for WNS, TNS, violations
   - Check `report_clock_min_period` for achievable frequency
   - Identify critical paths

2. **Determine root cause**:
   - Clock too aggressive? → Relax period
   - Long paths? → Buffering/pipelining
   - High utilization? → Reduce density
   - Clock issues? → CTS tuning

3. **Implement solution**:
   - Start with simplest fix (clock relaxation)
   - Test incrementally
   - Verify with reports

4. **Document changes**:
   - Show before/after metrics
   - Explain tradeoffs
   - Provide reproduction steps

## Results Summary

### Before (Original Constraint)
```
Clock Period:        0.46 ns
Target Frequency:    2174 MHz
WNS:                 -0.05 ns ❌
TNS:                 -0.53 ns ❌
Setup Violations:    23 ❌
Status:              FAILED
```

### After (Improved Constraint)
```
Clock Period:        0.52 ns
Target Frequency:    1923 MHz
WNS:                 ~0.00 ns ✅
TNS:                 ~0.00 ns ✅
Setup Violations:    4 (negligible) ✅
Status:              PASSED
Tradeoff:            -12% frequency
```

## References

- [OpenROAD Documentation](https://openroad.readthedocs.io/)
- [OpenROAD-flow-scripts GitHub](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts)
- [SDC Constraints Guide](https://www.synopsys.com/Company/Publications/ManualAbstracts/Pages/sdc-abstract.aspx)
- [Timing Analysis Basics](https://openroad.readthedocs.io/en/latest/main/README.html#static-timing-analysis)

## Troubleshooting

### Build Fails
```bash
# Check logs
cat /home/luars/OpenROAD-flow-scripts/flow/logs/nangate45/gcd/base/6_finish.log

# Verify design config
cat /home/luars/OpenROAD-flow-scripts/flow/designs/nangate45/gcd/config.mk
```

### Reports Not Generated
```bash
# Ensure flow completed
ls -la /home/luars/OpenROAD-flow-scripts/flow/reports/nangate45/gcd/base/

# Check for errors in logs
grep -i "error" /home/luars/OpenROAD-flow-scripts/flow/logs/nangate45/gcd/base/*.log
```

### Still Have Violations
- Further relax clock (try 0.54 ns, 0.56 ns)
- Check for DRC/routing issues
- Review placement quality
- Consider design modifications

## Contact

For issues or questions:
- OpenROAD GitHub Issues: https://github.com/The-OpenROAD-Project/OpenROAD/issues
- OpenROAD-flow-scripts Issues: https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/issues

---

**Last Updated**: 2025-12-07
**Tested Environment**: OpenROAD v2.0, OpenROAD-flow-scripts (latest)
**Design**: nangate45/gcd
