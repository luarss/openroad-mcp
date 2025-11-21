# AI-Driven Timing Optimization Flow

## Quick Start

This demo demonstrates **AI-driven discovery** of optimal timing constraints through iterative analysis with OpenROAD-MCP. No Python required - just pure OpenROAD TCL commands.

**Design:** GCD (Greatest Common Divisor)
**Platform:** Nangate45 (45nm)
**Total Time:** ~30-60 seconds

### What You'll Do

1. Start with an aggressive constraint (0.20ns / 5.0 GHz) that **will fail**
2. Analyze timing violations to understand the design
3. Let AI discover better constraints through reasoning
4. Iterate until timing closure with WNS > 0, TNS = 0

## Philosophy: Discovery, Not Scripting

### Traditional Demo ❌
```
- Pre-write 3 SDC files (0.25ns, 0.35ns, 0.46ns)
- Run all 3 in predetermined sequence
- Show expected pass/fail progression
- AI learns nothing about optimization
```

### This Demo ✅
```
- Start with 1 intentionally bad SDC (0.20ns)
- AI analyzes violations and extracts critical path data
- AI discovers better values through reasoning
- AI creates new SDC files based on analysis
- AI learns optimization methodology
```

## Files

```
optimisation-flow/
├── README.md                    📖 This file - complete guide
├── config/
│   └── constraint_starter.sdc   # Initial bad constraint (0.20ns)
└── results/                     # Generated during optimization
    ├── baseline_0.20ns.txt
    ├── iteration_*.txt
    └── *.tcl scripts
```

AI will create additional constraint files during discovery:
- `constraint_iteration_1.sdc` - Generated based on baseline analysis
- `constraint_iteration_2.sdc` - Generated if needed
- etc.

## Setup

Define paths:
```bash
ORFS_ROOT="/home/luars/OpenROAD-flow-scripts/flow"
PLATFORM="nangate45"
DESIGN="gcd"
DEMO_DIR="/home/luars/openroad-mcp/demo/optimisation-flow"

TECH_LEF="${ORFS_ROOT}/platforms/${PLATFORM}/lef/NangateOpenCellLibrary.tech.lef"
MACRO_LEF="${ORFS_ROOT}/platforms/${PLATFORM}/lef/NangateOpenCellLibrary.macro.lef"
LIBERTY="${ORFS_ROOT}/platforms/${PLATFORM}/lib/NangateOpenCellLibrary_typical.lib"
VERILOG="${ORFS_ROOT}/designs/src/${DESIGN}/${DESIGN}.v"

mkdir -p ${DEMO_DIR}/results
```

## Step 1: Analyze Baseline (Intentionally Bad Constraint)

We start with 0.20ns (5.0 GHz) - this is aggressive and **will fail**.

Create analysis script:
```bash
cat > ${DEMO_DIR}/results/analyze_baseline.tcl << 'EOF'
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef
read_liberty /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib
read_verilog /home/luars/OpenROAD-flow-scripts/flow/designs/src/gcd/gcd.v
link_design gcd

read_sdc /home/luars/openroad-mcp/demo/optimisation-flow/config/constraint_starter.sdc

puts "\n========================================="
puts "BASELINE: 0.20ns (5.0 GHz)"
puts "=========================================\n"

puts "→ Worst Negative Slack (WNS):"
report_worst_slack -max

puts "\n→ Total Negative Slack (TNS):"
report_tns

puts "\n→ Critical Path Analysis:"
report_checks -path_delay max -format full_clock_expanded -digits 3

exit
EOF
```

Run analysis:
```bash
openroad ${DEMO_DIR}/results/analyze_baseline.tcl | tee ${DEMO_DIR}/results/baseline_0.20ns.txt
```

**Expected output:**
```
WNS Report:
wns -0.234

TNS Report:
tns -1.567

❌ Results: WNS = -0.234ns, TNS = -1.567ns - FAIL
```

This tells us we're failing by ~0.234ns on the worst path.

## Step 2: AI Analyzes and Decides Next Steps

Based on the baseline analysis, answer these questions:
1. What is the actual critical path delay?
2. How much slack do we need to add?
3. What clock period should we try next?

**Example reasoning:**
- If critical path is 0.434ns and current constraint is 0.20ns
- We need at least 0.434ns clock period
- Add margin for safety: try 0.45ns or 0.48ns

## Step 3: Create New Constraint Based on Analysis

**Don't hardcode this!** The AI should decide based on Step 2 analysis.

Example approach (AI discovers this value):
```bash
# AI discovers that 0.45ns might work based on critical path analysis
cat > ${DEMO_DIR}/config/constraint_iteration_1.sdc << 'EOF'
current_design gcd
set clk_name core_clock
set clk_port_name clk
set clk_period 0.45
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]
create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [all_inputs -no_clocks]
set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]
EOF
```

## Step 4: Test New Constraint

```bash
cat > ${DEMO_DIR}/results/analyze_iteration_1.tcl << 'EOF'
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef
read_liberty /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib
read_verilog /home/luars/OpenROAD-flow-scripts/flow/designs/src/gcd/gcd.v
link_design gcd

read_sdc /home/luars/openroad-mcp/demo/optimisation-flow/config/constraint_iteration_1.sdc

puts "\n========================================="
puts "ITERATION 1: [determined by AI]"
puts "=========================================\n"

puts "→ WNS:"
report_worst_slack -max

puts "\n→ TNS:"
report_tns

puts "\n→ Critical Path:"
report_checks -path_delay max -format full_clock_expanded -digits 3

exit
EOF

openroad ${DEMO_DIR}/results/analyze_iteration_1.tcl | tee ${DEMO_DIR}/results/iteration_1.txt
```

**Possible result:**
```
WNS Report:
wns 0.016

TNS Report:
tns 0.000

✅ Results: WNS = 0.016ns, TNS = 0.000ns - PASS
```

## Step 5: Iterate Until Timing Closure

Repeat Steps 2-4 until:
- WNS >= 0 (positive slack)
- TNS = 0 (no violations)

Each iteration should be based on **analysis**, not guessing.

## Understanding the Metrics

### Worst Negative Slack (WNS)
- **Negative**: Design fails timing by this amount
- **Zero**: Design barely meets timing (risky!)
- **Positive**: Design meets timing with margin (good!)

### Total Negative Slack (TNS)
- Sum of all path violations
- Zero means all paths meet timing
- Higher value = more paths failing

### Critical Path
Shows the bottleneck path:
```
Startpoint: req_msg[0] (input port)
Endpoint: _135_ (flip-flop)
Path Delay: 0.434ns        ← This is the actual constraint needed
Required Time: 0.200ns     ← What we asked for
Slack: -0.234ns (VIOLATED) ← How much we missed by
```

This tells you:
- The path takes 0.434ns
- We required it to be 0.200ns
- We're short by 0.234ns

## Expected Discovery Flow

### Iteration 0: Baseline (Intentionally Bad)
```
Constraint: 0.20ns (starter file)
Result: WNS = -0.234ns, TNS = -1.567ns
Analysis: Critical path is 0.434ns
Reasoning: Need at least 0.434ns + margin
Decision: Try 0.48ns
```

### Iteration 1: First Discovery
```
Constraint: 0.48ns (AI generated based on analysis)
Result: WNS = 0.046ns, TNS = 0.000ns
Analysis: Passing with good margin
Decision: Could tighten to 0.45ns for performance
```

### Iteration 2: Fine-Tuning (Optional)
```
Constraint: 0.45ns (AI explores tighter timing)
Result: WNS = 0.016ns, TNS = 0.000ns
Analysis: Passing with acceptable margin
Decision: Optimal found!
```

Your actual iterations may differ based on the design and your analysis!

## Using OpenROAD MCP for This Demo

The interactive MCP tools are perfect for this workflow:

```python
# Start session
create_interactive_session(session_id="timing_opt")

# Run baseline analysis
interactive_openroad(
    command="read_lef ...; read_liberty ...; ...; report_worst_slack",
    session_id="timing_opt"
)

# AI analyzes output, creates new SDC

# Test new constraint
interactive_openroad(
    command="read_sdc new_constraint.sdc; report_worst_slack",
    session_id="timing_opt"
)

# Iterate until closure
```

The MCP session keeps the design loaded, making iterations fast.

### MCP Tools Used
1. `create_interactive_session` - Start persistent OpenROAD session
2. `interactive_openroad` - Execute analysis commands
3. `get_session_history` - Track optimization progress
4. `inspect_interactive_session` - Monitor session health

### OpenROAD Commands
```tcl
read_lef <tech_file>              # Load technology (once)
read_liberty <lib_file>           # Load timing library (once)
read_verilog <design_file>        # Load netlist (once)
link_design <design_name>         # Link design (once)

read_sdc <constraint_file>        # Load constraints (each iteration)
report_worst_slack -max           # Check WNS
report_tns                        # Check TNS
report_checks -path_delay max     # Analyze critical path
```

## Why This Approach is Better

### Traditional Flow (without MCP)
```
For each iteration:
  1. Update SDC file
  2. Run full synthesis      (1-2 min)
  3. Run placement/routing   (3-5 min)
  4. Check timing           (10 sec)

Total per iteration: 5-10 minutes
Discovery with 3 iterations: 15-30 minutes
```

### MCP Flow
```
Once:
  1. Load design        (10 sec)

For each iteration:
  1. Create new SDC     (1 sec - AI generates)
  2. Reload constraints (1 sec)
  3. Check timing       (5 sec)

Discovery with 3 iterations: 10 + (3 × 7) = ~30 sec
```

**Result: 30-60x faster!** Fast iteration enables natural exploration instead of pre-planning.

## Key Insights

### Discovery Process
1. **Measure actual delay** - Don't guess, measure the critical path
2. **Calculate margin** - Add headroom for PVT variation
3. **Test hypothesis** - Try the new constraint
4. **Verify closure** - Check WNS/TNS

### Common Patterns
- Simple designs (like GCD): May close at 0.40-0.50ns
- Complex designs: May need 1.0ns or more
- First iteration improvement: Usually 50-80% of needed slack
- Final iterations: Small tweaks (0.05-0.10ns steps)

### What NOT to Do
- Don't hardcode "good" constraints in advance
- Don't create multiple SDC files before testing
- Don't script the final answer
- Don't skip analysis steps

### Optimization is Discovery
You don't know the optimal constraint until you measure the design. Pre-scripting defeats the purpose.

### Methodology Transfers
Process works for:
- Any design (simple to complex)
- Any technology node
- Any timing corner
- Any optimization parameter

## Success Criteria

You've successfully completed this demo when you can:
1. Explain why the starting constraint fails
2. Calculate the minimum constraint from critical path analysis
3. Justify each iteration's constraint value
4. Understand why the final value achieves timing closure
5. Apply the same methodology to a different design

## What You'll Learn

This demo teaches:
1. **Methodology over memorization** - Process applies to any design
2. **Analysis-driven decisions** - Don't guess, measure
3. **Iterative refinement** - Converge on optimal solution
4. **AI reasoning** - How to think about timing optimization

Not just "run these 3 commands and get these 3 results".

## Next Steps

### Try Different Starting Points
Edit `config/constraint_starter.sdc`:
```tcl
set clk_period 0.15  # Even more aggressive failure
set clk_period 0.10  # Extreme failure for testing
```

### Try Different Designs
Replace GCD with more complex designs:
```bash
DESIGN="aes"      # AES encryption - moderate complexity
DESIGN="jpeg"     # JPEG encoder - high complexity
DESIGN="ibex"     # RISC-V core - very high complexity
```

More complex designs = more iterations needed.

### Analyze Path Composition
Look at the detailed path report to understand:
- Where is delay coming from? (logic vs. wire)
- Which cells are slowest?
- Are there obvious bottlenecks?

### Automate the Discovery
Build a script that:
- Runs timing analysis
- Extracts critical path delay
- Calculates next constraint value
- Iterates until WNS > 0
- Reports optimal value

### Multi-Corner Optimization
Extend to multiple PVT corners:
- Typical corner (TT, 25°C, 1.0V)
- Fast corner (FF, 0°C, 1.1V)
- Slow corner (SS, 125°C, 0.9V)

Discover optimal constraint for worst corner.

### Try Optimization Techniques
Once you understand the baseline:
- Adjust synthesis settings
- Change cell library
- Modify floorplan
- Add pipeline stages

## Troubleshooting

**"Timing passes at 0.20ns"**
```bash
# GCD is very simple - try more aggressive:
set clk_period 0.10  # in constraint_starter.sdc
# Or use a more complex design
```

**"Can't get timing to close"**
```bash
# Design might be complex - AI should discover larger value
# Let it iterate naturally, don't force predetermined values
# Check if you're using the right liberty file
# Verify LEF files are loaded correctly
```

**"Can't find critical path delay in report"**
```bash
# Look for "Data Arrival Time" in report_checks output
# This is the actual path delay
# Use this + margin for next constraint
```

**"AI keeps trying same values"**
```bash
# Make sure to extract data from timing reports
# Don't guess - measure the critical path
# Use structured parsing of OpenROAD output
```

**"AI not discovering better values"**
```bash
# Make sure AI reads the critical path delay from timing report
# AI should extract actual path delay and use it to calculate next try
```

**OpenROAD errors?**
```bash
which openroad
# Should show: /home/luars/OpenROAD-flow-scripts/tools/install/OpenROAD/bin/openroad
```

## Questions?

**Q: Why start with 0.20ns when we know it will fail?**
A: To demonstrate discovery! Real usage would start near expected target, but AI still iterates to find optimal.

**Q: What if AI guesses wrong?**
A: That's the point! It analyzes the result, learns, and tries again. Real optimization is iterative.

**Q: Can I automate this completely?**
A: Yes! Build a loop that reads timing reports and generates new constraints until WNS > 0.

**Q: How does this compare to binary search?**
A: Binary search is one strategy. AI might use gradient descent, learned heuristics, or hybrid approaches.

**Q: What about PVT corners?**
A: After finding optimal at typical corner, repeat for fast/slow corners. Same discovery process.

## References

- [OpenROAD Documentation](https://openroad.readthedocs.io/)
- [OpenSTA Timing Analysis](https://github.com/The-OpenROAD-Project/OpenSTA)
- [SDC Constraints Guide](https://www.synopsys.com/community/interoperability/tap-in/sdc.html)
- [MCP Protocol](https://modelcontextprotocol.io/)

## Contributing

Want to improve this demo?
- Add more design examples
- Show different optimization strategies
- Add automated discovery scripts
- Improve analysis extraction

Submit PRs with your enhancements!

---

**Remember:** The goal is to teach how to fish, not to provide fish. Happy Discovering!
