# ORFS GCD Demo - Tight Constraints (Creates Violations for Demo)
# This file contains aggressive timing constraints that create
# realistic violations for the timing debug demonstration.
#
# Clock period: 0.46ns (2.17 GHz) - Too aggressive for GCD datapath
# Expected violations: ~10-15 setup violations
# Worst slack: ~-1.2ns

current_design gcd

set clk_name core_clock
set clk_port_name clk
set clk_period 0.46
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]

create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [lsearch -inline -all -not -exact [all_inputs] $clk_port]

set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]

# Aggressive I/O constraints
set_input_delay -clock $clk_name -max 0.05 [get_ports {req_msg* req_val}]
set_output_delay -clock $clk_name -max 0.05 [get_ports {resp_msg* resp_val}]

# Minimal clock uncertainty (makes violations worse)
set_clock_uncertainty 0.02 [get_clocks $clk_name]
set_clock_transition 0.02 [get_clocks $clk_name]

# Reasonable load requirements
set_load 0.1 [all_outputs]

# Note: False paths intentionally NOT declared to expose violations
# This simulates an under-constrained design
