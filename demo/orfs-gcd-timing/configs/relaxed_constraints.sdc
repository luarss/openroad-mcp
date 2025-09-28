# ORFS GCD Demo - Relaxed Constraints (Fixes Violations)
# This file contains realistic timing constraints that achieve
# timing closure for the GCD design.

current_design gcd

set clk_name core_clock
set clk_port_name clk
set clk_period 8.0
set clk_io_pct 0.2

set clk_port [get_ports $clk_port_name]

create_clock -name $clk_name -period $clk_period $clk_port

set non_clock_inputs [all_inputs -no_clocks]

set_input_delay [expr $clk_period * $clk_io_pct] -clock $clk_name $non_clock_inputs
set_output_delay [expr $clk_period * $clk_io_pct] -clock $clk_name [all_outputs]


# Realistic I/O constraints
set_input_delay -clock clk -max 1.0 [get_ports {a b req}]
set_output_delay -clock clk -max 1.0 [get_ports {z ack}]

# Proper false path declarations
set_false_path -from [get_ports reset]
set_false_path -to [get_ports reset]

# False paths for test signals (if they exist)
set_false_path -from [get_ports test_en] -to [all_registers]
set_false_path -from [get_ports scan_en] -to [all_registers]

# Reasonable load requirements
set_load 0.1 [all_outputs]

# Clock uncertainty and transition time
set_clock_uncertainty 0.1 [get_clocks clk]
set_clock_transition 0.1 [get_clocks clk]
