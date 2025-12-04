# AI-Driven Timing Optimization Flow

## Quick Start

This demo demonstrates **AI-driven discovery** of optimal timing constraints through iterative analysis with OpenROAD-MCP. No Python required - just pure OpenROAD TCL commands.

**IMPORTANT:** Use OpenROAD MCP interactive sessions for this demo, not bash scripts. The MCP approach is 30-60x faster and enables natural exploration instead of pre-planned scripts. GCD design used in this document is just to serve as a reference. Do your own optimisation.

**Design:** AES (Advanced Encryption Standard) - Cipher Top Module
**Platform:** Nangate45 (45nm)

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

**Note:** The example scripts below use `gcd` (a simple design) as reference material to demonstrate the workflow. When running the actual AES demo, replace:
- `DESIGN="gcd"` → `DESIGN="aes"`
- `gcd.v` → `aes.v`
- `link_design gcd` → `link_design aes_cipher_top`
- `synth -top gcd` → `synth -top aes_cipher_top`
- `gcd_synth.v` → `aes_synth.v`

The AI should adapt these paths when switching from the GCD example to the AES demo.

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

## Important: Synthesis Strategy

**CRITICAL:** For AES design, use `make synth` instead of manual Yosys/OpenROAD synthesis scripts. The AES verilog has complex dependencies and the ORFS Makefile handles them correctly.

### Recommended Synthesis Approach

```bash
# Copy your constraint to the design directory
cp ${DEMO_DIR}/config/constraint_starter.sdc \
   ${ORFS_ROOT}/designs/nangate45/aes/constraint.sdc

# Use make synth - it handles all dependencies
cd ${ORFS_ROOT}
make DESIGN_CONFIG=designs/nangate45/aes/config.mk clean_synth
make DESIGN_CONFIG=designs/nangate45/aes/config.mk synth

# Synthesized netlist will be at:
# ${ORFS_ROOT}/results/nangate45/aes/base/1_synth.v
```

**Why this matters:**
- AES has multiple verilog files with dependencies
- Manual `read_verilog` attempts may hit syntax errors
- ORFS Makefile uses Yosys correctly for complex designs
- ABC technology mapping takes ~25-30 seconds (be patient!)

**Time expectations:**
- First synthesis: ~35 seconds (includes ABC mapping)
- Each subsequent synthesis: ~35 seconds
- This is why MCP interactive sessions are recommended - you can test constraint changes without full re-synthesis

## Step 1: Synthesize the Netlist

Before analyzing timing, we need to synthesize the RTL into a gate-level netlist using the starter constraints.

Create synthesis script:
```bash
cat > ${DEMO_DIR}/results/synthesize.tcl << 'EOF'
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef
read_liberty /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib

# Read RTL source
read_verilog /home/luars/OpenROAD-flow-scripts/flow/designs/src/gcd/gcd.v
link_design gcd

# Read constraints before synthesis
read_sdc /home/luars/openroad-mcp/demo/optimisation-flow/config/constraint_starter.sdc

# Synthesize
puts "→ Synthesizing netlist..."
synth -top gcd

# Write synthesized netlist
write_verilog ${DEMO_DIR}/results/gcd_synth.v

puts "✓ Synthesis complete: ${DEMO_DIR}/results/gcd_synth.v"

exit
EOF
```

Run synthesis:
```bash
openroad ${DEMO_DIR}/results/synthesize.tcl
```

**What happens:**
- Reads RTL source (`gcd.v` - for AES demo, use `aes.v` and `aes_cipher_top`)
- Applies timing constraints (`constraint_starter.sdc`)
- Synthesizes logic to standard cells
- Outputs gate-level netlist (`gcd_synth.v` - for AES demo, use `aes_synth.v`)

**Why synthesize first?**
- Timing analysis on RTL is inaccurate (no real gates)
- Synthesis maps to actual library cells with real delays
- Gives realistic critical path information
- Same netlist used throughout iteration (consistency)

## Step 2: Analyze Baseline (Intentionally Bad Constraint)

We start with 0.20ns (5.0 GHz) - this is aggressive and **will fail**.

Create analysis script:
```bash
cat > ${DEMO_DIR}/results/analyze_baseline.tcl << 'EOF'
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef
read_liberty /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib

# Read synthesized netlist (not RTL source)
read_verilog /home/luars/openroad-mcp/demo/optimisation-flow/results/gcd_synth.v
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

## Step 3: AI Analyzes and Decides Next Steps

Based on the baseline analysis, answer these questions:
1. What is the actual critical path delay?
2. How much slack do we need to add?
3. What clock period should we try next?

**Example reasoning:**
- If critical path is 0.434ns and current constraint is 0.20ns
- We need at least 0.434ns clock period
- Add margin for safety: try 0.45ns or 0.48ns

## Step 4: Create New Constraint and Re-synthesize

**Don't hardcode this!** The AI should decide based on Step 3 analysis.

When you change constraints, you need to re-synthesize to get an accurate netlist for the new timing target.

Example approach (AI discovers this value):
```bash
# AI discovers the appropriate period based on critical path analysis
cat > ${DEMO_DIR}/config/constraint_iteration_1.sdc << 'EOF'
current_design aes_cipher_top
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

Then re-synthesize with the new constraint:
```bash
cat > ${DEMO_DIR}/results/synthesize_iteration_1.tcl << 'EOF'
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef
read_liberty /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib

# Read RTL source
read_verilog /home/luars/OpenROAD-flow-scripts/flow/designs/src/gcd/gcd.v
link_design gcd

# Read new constraints before synthesis
read_sdc /home/luars/openroad-mcp/demo/optimisation-flow/config/constraint_iteration_1.sdc

# Synthesize with new constraints
puts "→ Re-synthesizing with iteration 1 constraints..."
synth -top gcd

# Write synthesized netlist
write_verilog ${DEMO_DIR}/results/gcd_synth_iteration_1.v

puts "✓ Synthesis complete: ${DEMO_DIR}/results/gcd_synth_iteration_1.v"

exit
EOF

openroad ${DEMO_DIR}/results/synthesize_iteration_1.tcl
```

## Step 5: Test New Constraint

```bash
cat > ${DEMO_DIR}/results/analyze_iteration_1.tcl << 'EOF'
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.tech.lef
read_lef /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lef/NangateOpenCellLibrary.macro.lef
read_liberty /home/luars/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib

# Read re-synthesized netlist
read_verilog /home/luars/openroad-mcp/demo/optimisation-flow/results/gcd_synth_iteration_1.v
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

## Step 6: Iterate Until Timing Closure

Repeat Steps 3-5 until:
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

**IMPORTANT:** The values below are for GCD (simple design) as examples ONLY. AES will have DIFFERENT timing characteristics. DO NOT copy these values - discover them through analysis!

### Iteration 0: Baseline (Intentionally Bad)
```
Constraint: 0.20ns (starter file - same for all designs)
Result: Will fail with negative WNS and TNS
Analysis: Extract the "data arrival time" from critical path report
Reasoning: Need at least [data arrival time] + safety margin (5-15%)
Decision: Calculate next constraint = [data arrival time] × (1 + margin%)
```

### Iteration 1: First Discovery
```
Constraint: [AI calculated based on iteration 0 analysis]
Result: Check if WNS >= 0 and TNS = 0
Analysis: If still failing, path delay > constraint
         If passing but WNS very small, might need more margin
Decision: If failing: increase constraint by remaining slack
         If passing: timing closure achieved or can fine-tune
```

### Iteration 2: Fine-Tuning (If Needed)
```
Constraint: [AI adjusted if iteration 1 was close but not quite]
Result: Should achieve WNS > 0 and TNS = 0
Analysis: Verify positive slack with adequate margin
Decision: Timing closure achieved!
```

**Key principle:** Each iteration should be based on MEASURED data from timing reports, not predetermined values. AES timing will be different from GCD - let the analysis guide you!

## Practical Iteration Strategy

### When to Stop Iterating

You've achieved timing closure when:
1. **WNS > 0** (even 0.01ns is technically passing)
2. **TNS = 0** (no paths violating timing)
3. Have reasonable margin (0.02-0.05ns slack recommended)

### Common Iteration Patterns

**If first iteration still fails slightly (WNS < 0 but close):**
- Look at the new critical path data arrival time
- Add small increment (data_arrival - current_constraint + small_margin)
- This usually closes timing on second iteration

**If first iteration passes with large margin (WNS >> 0.1ns):**
- Could tighten constraint for better performance
- But remember: tool may optimize differently with tighter constraint
- Sometimes "good enough" is better than "perfect"

### Debugging Tips

**If synthesis takes very long (>2 minutes):**
- ABC technology mapping is working - be patient
- Normal for complex designs like AES
- First synthesis includes library characterization

**If timing gets worse after tightening constraint:**
- Synthesis tools make different trade-offs with different constraints
- Not always monotonic improvement
- Stick with a constraint that achieves closure with margin

**If you can't achieve closure after 3-4 iterations:**
- Check if you're reading the correct data from timing reports
- Verify you're looking at "data arrival time" not "slack"
- Make sure setup time is accounted for in required time
- Consider that design might need architectural changes for that frequency

## Two Workflow Options

### Option 1: Fast MCP Interactive Workflow (RECOMMENDED)

**Pros:** 30-60x faster iteration, ideal for exploration
**Cons:** Netlist doesn't change between iterations (uses same synthesis)

```
1. Synthesize ONCE with make synth (using starter constraint)
2. Create MCP interactive session
3. Load synthesized netlist into session
4. For each iteration:
   - Create new SDC file with updated constraint
   - Run: read_sdc <new_constraint_file>
   - Run: report_worst_slack -max
   - Run: report_tns
   - Run: report_checks (to get critical path data)
   - Analyze and decide next iteration
5. FAST: Each check takes ~5-10 seconds
```

**Key insight:** For pure timing constraint discovery, you don't need to re-synthesize. The synthesized netlist has delays; you're just checking if those delays meet different timing requirements.

### Option 2: Full Re-synthesis Workflow (THOROUGH)

**Pros:** Most accurate, synthesis optimizes for each constraint
**Cons:** 35+ seconds per iteration due to ABC technology mapping

```
1. For each iteration:
   - Update constraint SDC file
   - Copy to designs/nangate45/aes/constraint.sdc
   - Run: make clean_synth && make synth
   - Wait ~35 seconds for ABC to complete
   - Load new netlist and analyze timing
2. SLOW: Each iteration takes 35-40 seconds
```

**When to use full re-synthesis:**
- Final verification before tapeout
- When synthesis optimizations matter (different constraints = different netlists)
- When you have time and want maximum accuracy


## Key Insights

### Discovery Process
1. **Measure actual delay** - Don't guess, measure the critical path
2. **Calculate margin** - Add headroom for PVT variation
3. **Test hypothesis** - Try the new constraint
4. **Verify closure** - Check WNS/TNS

### Common Patterns
- Moderate designs (like AES): Timing will differ from simple designs like GCD
- Complex designs: May need significantly longer clock periods
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
Experiment with different complexity levels:
```bash
DESIGN="gcd"      # GCD - very simple (use top module: gcd)
DESIGN="uart"     # UART - simple serial interface
DESIGN="aes"      # AES encryption - moderate complexity (use top module: aes_cipher_top)
DESIGN="jpeg"     # JPEG encoder - high complexity
DESIGN="ibex"     # RISC-V core - very high complexity
```

**Remember:** When changing designs, update both `DESIGN` and `TOP_MODULE` variables, and re-synthesize with the new design before analyzing timing.

More complex designs = more iterations needed.

## Common Pitfalls and Solutions

### Pitfall 1: Copying Example Values
**Problem:** Using GCD timing values (from examples) for AES design
**Why it fails:** Different designs have completely different critical paths
**Solution:** ALWAYS extract actual data from YOUR timing reports for YOUR design

### Pitfall 2: Reading Slack Instead of Data Arrival Time
**Problem:** Using "slack" value to calculate next constraint
**Why it fails:** Slack is relative to current constraint, not absolute path delay
**Solution:** Look for "data arrival time" in the critical path report - this is the actual path delay

### Pitfall 3: Not Accounting for Setup Time
**Problem:** Setting constraint = data arrival time exactly
**Why it fails:** Flip-flops need setup time (~0.04ns), so required time = constraint - setup
**Solution:** Add margin: next_constraint = data_arrival_time × 1.05 to 1.15

### Pitfall 4: Impatience with ABC
**Problem:** Killing synthesis because it seems stuck
**Why it fails:** ABC technology mapping takes 25-30 seconds for AES - this is normal
**Solution:** Wait patiently. If >2 minutes with no output, then investigate

### Pitfall 5: Not Using Make for AES
**Problem:** Trying to manually read_verilog all AES files in OpenROAD
**Why it fails:** File dependencies and syntax issues with direct verilog reading
**Solution:** Use `make synth` - it handles all dependencies correctly

### Pitfall 6: Expecting Monotonic Improvement
**Problem:** Assuming tighter constraint always gives better results
**Why it fails:** Synthesis makes different trade-offs; sometimes optimizes differently
**Solution:** Once you achieve closure with margin, that's success - don't over-optimize

### Pitfall 7: Forgetting the Design Name
**Problem:** Using `link_design aes` instead of `link_design aes_cipher_top`
**Why it fails:** The actual module name in verilog is aes_cipher_top
**Solution:** Check the verilog file for the actual module name: `module aes_cipher_top`

### Pitfall 8: Mixing Up WNS Units
**Problem:** Seeing "wns -0.02" and thinking "that's -20ps, not bad"
**Why it fails:** OpenROAD reports in nanoseconds, so -0.02 = -20ps which violates timing
**Solution:** Any negative WNS = timing violation. Need WNS >= 0 for closure

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
