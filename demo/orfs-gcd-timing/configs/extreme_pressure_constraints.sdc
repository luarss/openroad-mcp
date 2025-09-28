# Extreme Timing Pressure - Violation Injection Scenario
# Very aggressive constraints creating many violations
# Target WNS: -2.00ns
# Target violations: 15
# Category: extreme

# Clock Definition
create_clock -name clk -period 4.0 [get_ports clk]

# Clock Uncertainty
set_clock_uncertainty 0.2 [get_clocks clk]

# Input Constraints
set_input_delay -clock clk -max 3.5 [get_ports {a b req}]
set_input_delay -clock clk -min 0.35000000000000003 [get_ports {a b req}]

# Output Constraints
set_output_delay -clock clk -max 3.5 [get_ports {z ack}]
set_output_delay -clock clk -min 0.35000000000000003 [get_ports {z ack}]

# Transition Constraints
set_max_transition 0.05 [all_inputs]
set_max_transition 0.05 [all_outputs]

# Scenario-Specific Constraints
# Extreme constraints for maximum violations
set_max_fanout 4 [all_inputs]
set_max_capacitance 0.02 [all_outputs]

# Load Constraints
set_load 0.05 [all_outputs]

# False Paths removed to create more violations
# set_false_path -from [get_ports reset]  # Commented for violations
# set_false_path -from [get_ports test_en]  # Commented for violations
