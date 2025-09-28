# I/O Constrained Design - Violation Injection Scenario
# Aggressive I/O timing constraints with reasonable clock
# Target WNS: -0.80ns
# Target violations: 6
# Category: io

# Clock Definition
create_clock -name clk -period 8.0 [get_ports clk]

# Clock Uncertainty
set_clock_uncertainty 0.1 [get_clocks clk]

# Input Constraints
set_input_delay -clock clk -max 6.0 [get_ports {a b req}]
set_input_delay -clock clk -min 0.6000000000000001 [get_ports {a b req}]

# Output Constraints
set_output_delay -clock clk -max 6.0 [get_ports {z ack}]
set_output_delay -clock clk -min 0.6000000000000001 [get_ports {z ack}]

# Scenario-Specific Constraints

# Load Constraints
set_load 0.05 [all_outputs]

# False Paths removed to create more violations
# set_false_path -from [get_ports reset]  # Commented for violations
# set_false_path -from [get_ports test_en]  # Commented for violations
