# ORFS GCD Demo - Tight Constraints (Creates Violations)
# This file contains over-aggressive timing constraints that will
# create realistic timing violations for demonstration purposes.

current_design gcd

set clk_name core_clock
set clk_port_name clk
set clk_period 5.0
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]

create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [all_inputs -no_clocks]

set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]


# Aggressive I/O constraints for demo violations
set_input_delay -clock clk -max 4.0 [all_inputs]
set_output_delay -clock clk -max 4.0 [all_outputs]

# Remove false paths that should exist (creates more violations)
# set_false_path -from [get_ports reset] (commented out for violations)
# set_false_path -from [get_ports test_en] (commented out for violations)

# Tight load requirements
set_load 0.05 [all_outputs]
