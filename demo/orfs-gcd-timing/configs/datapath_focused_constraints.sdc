# Datapath Critical - Violation Injection Scenario
# Constraints that stress the computational datapath
# Target WNS: -1.50ns
# Target violations: 12
# Category: clock

# Clock Definition
create_clock -name clk -period 4.5 [get_ports clk]

# Clock Uncertainty
set_clock_uncertainty 0.1 [get_clocks clk]

# Input Constraints
set_input_delay -clock clk -max 1.0 [all_inputs]
set_input_delay -clock clk -min 0.1 [all_inputs]

# Output Constraints
set_output_delay -clock clk -max 1.0 [all_outputs]
set_output_delay -clock clk -min 0.1 [all_outputs]

# Scenario-Specific Constraints

# Load Constraints
set_load 0.05 [all_outputs]

# False Paths removed to create more violations
# set_false_path -from [get_ports reset]  # Commented for violations
# set_false_path -from [get_ports test_en]  # Commented for violations
