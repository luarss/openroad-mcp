"""Benchmark fixture: scripted OpenROAD command sequence with mock outputs."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# System prompt (~1500 tokens) — shared by both benchmark conditions.
# Must be ≥1024 tokens alone so baseline can also hit Gemini's caching minimum.
# ---------------------------------------------------------------------------

SYSTEM_INSTRUCTION = """\
You are an expert OpenROAD EDA automation assistant helping chip designers run
timing analysis, fix violations, and navigate the RTL-to-GDS VLSI design flow
using OpenROAD and OpenROAD-flow-scripts (ORFS).

When responding, reference specific numbers from tool outputs (slack values,
instance counts, utilization percentages). Keep answers concise and actionable.

## OpenROAD Overview

OpenROAD is an open-source RTL-to-GDS EDA tool suite covering synthesis through
detailed routing. The typical flow is:
  synthesis → floorplanning → placement → CTS → routing → finishing

Design state is maintained in a shared in-memory database (odb). All commands
operate on this database unless otherwise noted.

## Timing Analysis Commands

report_wns
    Report worst negative slack (WNS) across all timing paths.
    Negative value means the design has timing violations.

report_tns
    Report total negative slack (TNS): sum of all negative path slacks.
    A proxy for the overall severity of timing closure work remaining.

report_slack_histogram [-num_bins N]
    Print a histogram of path slacks to show the distribution of timing.

report_checks [-path_delay max|min] [-format full_clock_expanded]
              [-fields {input_pin slew capacitance}] [-digits N]
              [-no_line_splits] [-endpoint_count N] [-group_count N]
    Report timing paths in detail. Use -format full_clock_expanded to see
    clock network contributions. -path_delay max reports setup paths;
    min reports hold paths.

report_design
    Print design area, instance count, net count, and utilization.

report_cell_usage
    Print a breakdown of standard cell usage by cell type.

estimate_parasitics -global_routing
    Estimate wire RC parasitics from global routing results.
    Required before accurate timing analysis post-route.

## Design Loading Commands

read_lef <path>
    Load a LEF technology or cell library. Load technology LEF first,
    then cell LEF. Multiple LEF files can be loaded.

read_def <path>
    Load a DEF design file (netlist + placement). Replaces the current
    design in memory.

read_verilog <path>
    Load a synthesized Verilog gate-level netlist.

read_liberty <path>
    Load a Liberty (.lib) timing library for a process corner.
    Load all corners (best, typical, worst) for full analysis.

read_sdc <path>
    Load Synopsys Design Constraints (SDC) — clocks, input/output delays,
    false paths, multicycle paths.

## Constraint Commands

create_clock -name <name> -period <ns> [<port_or_pin>]
    Define a clock. Period is in nanoseconds.

set_input_delay -clock <clk> [-max|-min] <delay_ns> <ports>
set_output_delay -clock <clk> [-max|-min] <delay_ns> <ports>
    Set I/O timing constraints relative to a clock.

set_clock_uncertainty [-setup|-hold] <value> <clocks>
    Add uncertainty (jitter, skew margin) to clock timing.

set_false_path [-from <start>] [-to <end>]
    Mark paths as non-timing-critical (no violation reported).

set_multicycle_path -setup <N> [-from <start>] [-to <end>]
    Allow N cycles for a path (relaxes setup requirement).

## Placement Commands

global_placement [-density <0.0-1.0>] [-pad_left N] [-pad_right N]
    Run global placement. Density controls target utilization.

detailed_placement
    Legalize placement (resolve overlaps, align to grid).

improve_placement
    Run incremental placement improvement for better timing.

## Clock Tree Synthesis

clock_tree_synthesis [-root_buf <cell>] [-buf_list <cells>]
                     [-clk_nets <nets>]
    Build the clock tree. Specify buffer cells from your library.

repair_clock_nets
    Repair maximum transition/capacitance violations on clock nets.

## Repair and Optimization

repair_design [-max_wire_length <um>]
    Fix max slew and max capacitance violations by buffering.

repair_timing [-setup] [-hold] [-slack_margin <ns>]
              [-max_buffer_percent <pct>]
    Fix setup and/or hold timing violations by buffering, resizing,
    or adding delay cells.

buffer_ports [-inputs] [-outputs] [-buffer_cell <cell>]
    Add buffers to primary I/O ports.

## Routing Commands

global_route [-guide_file <path>] [-congestion_iterations N]
    Run global routing (maze routing).

detailed_route [-output_maze <path>] [-output_drc <path>]
               [-droute_end_iter N]
    Run detailed routing (track assignment + DRC clean-up).

## Verification

check_placement [-verbose]
    Check for placement DRC violations.

check_antennas [-report_violating_nets]
    Check for antenna rule violations.

report_drc
    Print design rule check summary after detailed routing.

## Common Workflows

### Timing Closure Loop
1. read_lef + read_def + read_liberty + read_sdc   (load design)
2. report_wns / report_tns                          (baseline timing)
3. estimate_parasitics -global_routing              (update parasitics)
4. repair_timing -setup -slack_margin 0.1           (fix setup violations)
5. report_wns / report_tns                          (verify improvement)
6. Repeat until WNS ≥ 0 and TNS = 0

### Full RTL-to-GDS via ORFS
Use make targets: make synth, make floorplan, make place, make cts,
make route, make finish. Each stage writes its output DEF for the next.
"""

# ---------------------------------------------------------------------------
# Mock outputs — realistic OpenROAD stdout for each command
# ---------------------------------------------------------------------------

MOCK_VERSION_OUTPUT = """\
OpenROAD v2.0-16027-g3a8b7e9d1 2024-12-10 23:15 +0000 (…)
This program is licensed under the BSD-3 clause license. See the LICENSE
file for details.
Components of this program may be licensed under more restrictive licenses
which must be honored.
"""

MOCK_READ_LEF_OUTPUT = """\
[INFO LEF-0009] Successfully parsed file \
/openroad/platforms/nangate45/lef/NangateOpenCellLibrary.mod.lef
  Sites  : CORE (width: 0.190, height: 1.400)
  Layers : 10 routing layers, 3 cut layers
  Macros : 135 cell macros
[INFO ODB-0227] LEF file /openroad/platforms/nangate45/lef/NangateOpenCellLibrary.mod.lef, \
created 8 layers, 4 vias
"""

MOCK_READ_DEF_OUTPUT = """\
[INFO ODB-0129] Successfully parsed file \
/openroad/designs/nangate45/gcd/floorplan.def
[INFO ODB-0130] Design: gcd
[INFO IFP-0020] Defining core area: (0, 0) to (2770, 2770) dbu
[INFO IFP-0021] Fill area: 2.77 x 2.77 = 7.67 sq um
[INFO IFP-0001] Design area: 7.66 sq um (63.76% utilization)
  Components : 524 instances
  Pins       : 52 I/O pins
  Nets       : 594 nets
  Rows       : 20 rows
"""

MOCK_REPORT_WNS_OUTPUT = """\
wns -0.031
"""

MOCK_REPORT_TNS_OUTPUT = """\
tns -0.156
"""

MOCK_REPORT_CHECKS_OUTPUT = """\
Startpoint: _319_ (rising edge-triggered flip-flop clocked by clk)
Endpoint: _330_ (rising edge-triggered flip-flop clocked by clk)
Path Group: clk
Path Type: max

  Delay    Time   Description
---------------------------------------------------------
   0.000    0.000   clock clk (rise edge)
   0.000    0.000   clock network delay (propagated)
   0.000    0.000 ^ _319_/CK (DFF_X1)
   0.184    0.184 ^ _319_/Q (DFF_X1)
     slew: 0.057  cap: 0.012
   0.083    0.267 v _263_/ZN (INV_X1)
     slew: 0.041  cap: 0.008
   0.091    0.358 ^ _267_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.044    0.402 v _265_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.062    0.464 ^ _269_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    0.497 v _271_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.060    0.557 ^ _273_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.031    0.588 v _275_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.054    0.642 ^ _277_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    0.673 v _279_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.062    0.735 ^ _281_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    0.768 v _283_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.055    0.823 ^ _285_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    0.854 v _287_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.060    0.914 ^ _289_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    0.947 v _291_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.053    1.000 ^ _293_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.031 v _295_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.055    1.086 ^ _297_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.117 v _299_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.054    1.171 ^ _301_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.202 v _303_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.055    1.257 ^ _305_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.288 v _307_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.053    1.341 ^ _309_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.372 v _311_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.060    1.432 ^ _313_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    1.465 v _315_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.062    1.527 ^ _317_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    1.530 ^ _330_/D (DFF_X1)
     slew: 0.029  cap: 0.004
   0.000    1.530   data arrival time

   1.500    1.500   clock clk (rise edge)
   0.000    1.500   clock network delay (propagated)
   0.000    1.500 ^ _330_/CK (DFF_X1)
  -0.044    1.456   library setup time
   1.456    1.456   data required time
---------------------------------------------------------
   1.456    1.456   data required time
  -1.530   -1.530   data arrival time
---------------------------------------------------------
          -0.031   slack (VIOLATED)

Startpoint: _318_ (rising edge-triggered flip-flop clocked by clk)
Endpoint: _329_ (rising edge-triggered flip-flop clocked by clk)
Path Group: clk
Path Type: max

  Delay    Time   Description
---------------------------------------------------------
   0.000    0.000   clock clk (rise edge)
   0.000    0.000   clock network delay (propagated)
   0.000    0.000 ^ _318_/CK (DFF_X1)
   0.184    0.184 ^ _318_/Q (DFF_X1)
     slew: 0.057  cap: 0.012
   0.083    0.267 v _262_/ZN (INV_X1)
     slew: 0.041  cap: 0.008
   0.091    0.358 ^ _266_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.044    0.402 v _264_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.062    0.464 ^ _268_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    0.497 v _270_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.060    0.557 ^ _272_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.031    0.588 v _274_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.054    0.642 ^ _276_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    0.673 v _278_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.062    0.735 ^ _280_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    0.768 v _282_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.055    0.823 ^ _284_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    0.854 v _286_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.060    0.914 ^ _288_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    0.947 v _290_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.053    1.000 ^ _292_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.031 v _294_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.055    1.086 ^ _296_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.117 v _298_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.054    1.171 ^ _300_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.202 v _302_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.055    1.257 ^ _304_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.288 v _306_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.053    1.341 ^ _308_/ZN (NOR2_X1)
     slew: 0.034  cap: 0.006
   0.031    1.372 v _310_/ZN (NAND2_X1)
     slew: 0.028  cap: 0.005
   0.060    1.432 ^ _312_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    1.465 v _314_/ZN (NAND2_X1)
     slew: 0.029  cap: 0.005
   0.062    1.527 ^ _316_/ZN (NOR2_X1)
     slew: 0.035  cap: 0.006
   0.033    1.530 ^ _329_/D (DFF_X1)
     slew: 0.029  cap: 0.004
   0.000    1.530   data arrival time

   1.500    1.500   clock clk (rise edge)
   0.000    1.500   clock network delay (propagated)
   0.000    1.500 ^ _329_/CK (DFF_X1)
  -0.044    1.456   library setup time
   1.456    1.456   data required time
---------------------------------------------------------
   1.456    1.456   data required time
  -1.530   -1.530   data arrival time
---------------------------------------------------------
          -0.031   slack (VIOLATED)
"""


# ---------------------------------------------------------------------------
# Fixture definition
# ---------------------------------------------------------------------------


@dataclass
class TurnSpec:
    turn_index: int
    tool_name: str
    arguments: dict  # type: ignore[type-arg]  # session_id injected at runtime
    mock_output: str
    user_prompt: str


@dataclass
class FixtureSpec:
    dry_run: bool
    api_turns: list[TurnSpec]


FIXTURE_TURNS: list[TurnSpec] = [
    TurnSpec(
        turn_index=1,
        tool_name="interactive_openroad_query",
        arguments={"command": "version"},
        mock_output=MOCK_VERSION_OUTPUT,
        user_prompt="What version of OpenROAD is running?",
    ),
    TurnSpec(
        turn_index=2,
        tool_name="interactive_openroad_exec",
        arguments={"command": "read_lef /openroad/platforms/nangate45/lef/NangateOpenCellLibrary.mod.lef"},
        mock_output=MOCK_READ_LEF_OUTPUT,
        user_prompt="Load the NangateOpenCellLibrary LEF file.",
    ),
    TurnSpec(
        turn_index=3,
        tool_name="interactive_openroad_exec",
        arguments={"command": "read_def /openroad/designs/nangate45/gcd/floorplan.def"},
        mock_output=MOCK_READ_DEF_OUTPUT,
        user_prompt="Load the GCD design DEF file and report its area utilization.",
    ),
    TurnSpec(
        turn_index=4,
        tool_name="interactive_openroad_query",
        arguments={"command": "report_wns"},
        mock_output=MOCK_REPORT_WNS_OUTPUT,
        user_prompt="Check the worst negative slack of the design.",
    ),
    TurnSpec(
        turn_index=5,
        tool_name="interactive_openroad_query",
        arguments={"command": "report_tns"},
        mock_output=MOCK_REPORT_TNS_OUTPUT,
        user_prompt="Check the total negative slack of the design.",
    ),
    TurnSpec(
        turn_index=6,
        tool_name="interactive_openroad_query",
        arguments={
            "command": (
                "report_checks -path_delay max -format full_clock_expanded"
                " -fields {input_pin slew} -digits 3 -no_line_splits"
            )
        },
        mock_output=MOCK_REPORT_CHECKS_OUTPUT,
        user_prompt="Run a full timing check with expanded clock paths and report all violations.",
    ),
]


def build_fixture(*, dry_run: bool) -> FixtureSpec:
    return FixtureSpec(dry_run=dry_run, api_turns=FIXTURE_TURNS)


def run_real_command(command: str) -> str:
    """Execute an OpenROAD Tcl command via the binary in OPENROAD_BIN env var."""
    binary = os.environ.get("OPENROAD_BIN", "openroad")
    result = subprocess.run(
        [binary, "-exit", "-no_splash"],
        input=command,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.stdout + result.stderr
