# Mild Clock Pressure - Violation Injection Scenario
# Slightly aggressive clock period creating minor violations
# Target WNS: -0.30ns
# Target violations: 3
# Category: clock

# Clock Definition
create_clock -name clk -period 6.5 [get_ports clk]

# Clock Uncertainty
set_clock_uncertainty 0.05 [get_clocks clk]

# Input Constraints
set_input_delay -clock clk -max 1.0 [get_ports {a b req}]
set_input_delay -clock clk -min 0.1 [get_ports {a b req}]

# Output Constraints
set_output_delay -clock clk -max 1.0 [get_ports {z ack}]
set_output_delay -clock clk -min 0.1 [get_ports {z ack}]

# Scenario-Specific Constraints

# Load Constraints
set_load 0.05 [all_outputs]

# False Paths removed to create more violations
# set_false_path -from [get_ports reset]  # Commented for violations
# set_false_path -from [get_ports test_en]  # Commented for violations
