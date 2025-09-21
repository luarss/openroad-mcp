# ORFS GCD Timing Debug Demo

This demo showcases AI-guided timing closure debugging using OpenROAD-MCP with the proven GCD (Greatest Common Divisor) design from OpenROAD-flow-scripts.

## Quick Start

1. **Set FLOW_HOME environment variable:**
   ```bash
   export FLOW_HOME="$HOME/OpenROAD-flow-scripts"
   ```

2. **Run the demo:**
   ```bash
   ./setup.sh
   python run_demo.py
   ```

## Demo Overview

The demo demonstrates how AI can transform timing closure from a manual, time-intensive process into an intelligent, conversational workflow:

- **Baseline**: Run ORFS GCD flow (~2-3 minutes)
- **Violations**: Inject realistic timing constraints that create violations
- **AI Debug**: Conversational analysis to identify root causes
- **Resolution**: Apply fixes and achieve timing closure
- **Validation**: Confirm positive slack

## Requirements

- OpenROAD-flow-scripts installed at `$FLOW_HOME`
- OpenROAD-MCP server running
- Python 3.8+
- 8GB RAM minimum, 16GB recommended

## File Structure

```
configs/               # SDC constraint variants
├── tight_constraints.sdc    # Over-constrained (creates violations)
└── relaxed_constraints.sdc  # Achievable targets (fixes violations)

scripts/               # Demo automation
├── mcp_timing_debug.py      # MCP timing analysis
├── conversation_flow.py     # AI conversation script
└── violation_analysis.py    # Constraint generation

expected_results/      # Reference data
├── baseline_timing.json     # Clean timing data
├── violated_timing.json     # Violation data
└── demo_transcript.md       # Expected conversation
```

## Demo Flow

1. **Initial Discovery**: AI finds timing violations in GCD design
2. **Path Analysis**: Detailed analysis of critical paths through GCD logic
3. **Cross-Domain Investigation**: Correlation of timing with physical implementation
4. **Fix Application**: Apply relaxed constraints and false paths
5. **Verification**: Confirm timing closure success

Total demo time: **4-5 minutes**

## Troubleshooting

- Ensure `FLOW_HOME` points to valid OpenROAD-flow-scripts installation
- Verify OpenROAD-MCP server is running and accessible
- Check that GCD design can be built with `make DESIGN_CONFIG=./flow/designs/nangate45/gcd/config.mk`
