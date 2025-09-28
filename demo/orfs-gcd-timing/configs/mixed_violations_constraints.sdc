# Mixed Constraint Violations - Violation Injection Scenario
# Combination of clock and I/O constraint violations
# Target WNS: -0.90ns
# Target violations: 10
# Category: mixed

# Clock Definition
create_clock -name clk -period 6.0 [get_ports clk]

# Clock Uncertainty
set_clock_uncertainty 0.15 [get_clocks clk]

# Input Constraints
set_input_delay -clock clk -max 4.0 [get_ports {a b req}]
set_input_delay -clock clk -min 0.4 [get_ports {a b req}]

# Output Constraints
set_output_delay -clock clk -max 4.5 [get_ports {z ack}]
set_output_delay -clock clk -min 0.45 [get_ports {z ack}]

# Transition Constraints
set_max_transition 0.1 [all_inputs]
set_max_transition 0.1 [all_outputs]

# Scenario-Specific Constraints

# Load Constraints
set_load 0.05 [all_outputs]

# False Paths removed to create more violations
# set_false_path -from [get_ports reset]  # Commented for violations
# set_false_path -from [get_ports test_en]  # Commented for violations
