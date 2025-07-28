#!/usr/bin/env openroad
# GCD Timing Checkpoint Test Script
# Tests timing checkpoint system using the GCD design from OpenROAD test suite

# Set up environment
set script_dir [file dirname [file normalize [info script]]]
set openroad_dir "/home/luars/OpenROAD"

# Design files
set gcd_verilog "$openroad_dir/src/gpl/test/design/nangate45/gcd/gcd.v"
set gcd_sdc "$openroad_dir/src/par/test/gcd_nangate45.sdc"
set nangate_lef "$openroad_dir/test/Nangate45/Nangate45.lef"
set nangate_lib "$openroad_dir/test/Nangate45/Nangate45_typ.lib"

# Output directory for checkpoints
set checkpoint_dir "./gcd_timing_checkpoints"
file mkdir $checkpoint_dir

puts "=========================================="
puts "GCD Timing Checkpoint Test"
puts "=========================================="

# Check if design files exist
foreach {var file} [list gcd_verilog $gcd_verilog gcd_sdc $gcd_sdc nangate_lef $nangate_lef nangate_lib $nangate_lib] {
    if {![file exists $file]} {
        puts "ERROR: File not found: $file"
        puts "Please ensure OpenROAD is installed with test files"
        exit 1
    } else {
        puts "Found: $file"
    }
}

puts "\n=== Design Setup ==="

# Read technology files
puts "Reading LEF file..."
read_lef $nangate_lef

puts "Reading liberty file..."
read_liberty $nangate_lib

# Read design
puts "Reading GCD verilog..."
read_verilog $gcd_verilog

puts "Linking design..."
link_design "gcd"

puts "Reading SDC constraints..."
read_sdc $gcd_sdc

puts "\n=== Initial Timing Analysis ==="

# Initial timing report
puts "Running initial timing analysis..."
report_checks -format summary -nworst 5

# Create checkpoint data file
set checkpoint_file [open "$checkpoint_dir/timing_checkpoints.json" w]
puts $checkpoint_file "\{"
puts $checkpoint_file "  \"checkpoints\": \["

# Function to create timing checkpoint
proc create_timing_checkpoint {stage_name checkpoint_file} {
    global checkpoint_dir

    puts "\n=== Creating Checkpoint: $stage_name ==="

    # Get current timestamp
    set timestamp [clock format [clock seconds] -format "%Y-%m-%d %H:%M:%S"]

    # Capture timing data
    puts "Capturing timing data for $stage_name..."

    # Report worst paths
    set wns_output [report_wns]
    set tns_output [report_tns]

    # Detailed timing report
    report_checks -format full_clock_expanded -nworst 10 > "$checkpoint_dir/${stage_name}_timing.rpt"

    # Path histogram
    report_timing_histogram -bins 20 > "$checkpoint_dir/${stage_name}_histogram.rpt"

    # Get path count estimate
    set path_count 0
    catch {
        set timing_paths [report_checks -format summary -nworst 1000 -return_string]
        set path_count [regexp -all "Path Group:" $timing_paths]
    }

    # Write checkpoint JSON entry
    puts $checkpoint_file "    \{"
    puts $checkpoint_file "      \"stage_name\": \"$stage_name\","
    puts $checkpoint_file "      \"timestamp\": \"$timestamp\","
    puts $checkpoint_file "      \"path_count\": $path_count,"
    puts $checkpoint_file "      \"wns\": \"[string trim $wns_output]\","
    puts $checkpoint_file "      \"tns\": \"[string trim $tns_output]\","
    puts $checkpoint_file "      \"reports\": \{"
    puts $checkpoint_file "        \"timing\": \"${stage_name}_timing.rpt\","
    puts $checkpoint_file "        \"histogram\": \"${stage_name}_histogram.rpt\""
    puts $checkpoint_file "      \}"
    puts $checkpoint_file "    \},"

    puts "Checkpoint created: $stage_name"
    puts "  Path count: $path_count"
    puts "  WNS: [string trim $wns_output]"
    puts "  TNS: [string trim $tns_output]"
}

# Stage 1: Initial synthesis checkpoint
create_timing_checkpoint "gcd_initial" $checkpoint_file

puts "\n=== Running Flow Stages ==="

# Initialize floorplan
puts "Initializing floorplan..."
initialize_floorplan \
    -utilization 40 \
    -aspect_ratio 1 \
    -core_space 2 \
    -die_area "0 0 150 150"

# Post-floorplan checkpoint
create_timing_checkpoint "gcd_floorplan" $checkpoint_file

# Global placement
puts "Running global placement..."
global_placement

# Post-placement checkpoint
create_timing_checkpoint "gcd_placement" $checkpoint_file

# Detailed placement
puts "Running detailed placement..."
detailed_placement

# Post-detailed placement checkpoint
create_timing_checkpoint "gcd_detailed_placement" $checkpoint_file

# Clock tree synthesis
puts "Running clock tree synthesis..."
clock_tree_synthesis \
    -root_buffer "BUF_X4" \
    -clk_buffer "BUF_X4"

# Post-CTS checkpoint
create_timing_checkpoint "gcd_cts" $checkpoint_file

# Global routing
puts "Running global routing..."
set_global_routing_layer_adjustment "M1-M10" 0.5
global_route

# Post-routing checkpoint
create_timing_checkpoint "gcd_routing" $checkpoint_file

# Close checkpoint file
puts $checkpoint_file "    \{\}"
puts $checkpoint_file "  \]"
puts $checkpoint_file "\}"
close $checkpoint_file

puts "\n=== Final Timing Analysis ==="

# Comprehensive final timing report
puts "Generating final timing reports..."

# Multi-corner analysis if available
catch {
    report_checks -corner slow -format summary > "$checkpoint_dir/final_timing_slow.rpt"
    report_checks -corner fast -format summary > "$checkpoint_dir/final_timing_fast.rpt"
}

# Final timing summary
report_checks -format full_clock_expanded -nworst 20 > "$checkpoint_dir/final_timing_detailed.rpt"
report_timing_histogram -bins 50 > "$checkpoint_dir/final_histogram.rpt"

# Clock analysis
report_clock_properties [get_clocks] > "$checkpoint_dir/clock_properties.rpt"

# Path analysis
puts "Analyzing critical paths..."
set critical_paths [get_timing_paths -nworst 10 -max_paths 10]
puts "Found [llength $critical_paths] critical paths"

# Fanin/fanout analysis for key registers
puts "Analyzing register connectivity..."
set gcd_regs [get_cells -hierarchical "dpath.*_reg*"]
puts "Found [llength $gcd_regs] registers in datapath"

foreach reg [lrange $gcd_regs 0 4] {
    set reg_name [get_property $reg name]
    puts "Register: $reg_name"

    # Get fanin
    set fanin_cells [get_fanin $reg -only_cells -levels 2]
    puts "  Fanin depth 2: [llength $fanin_cells] cells"

    # Get fanout
    set fanout_cells [get_fanout $reg -only_cells -levels 2]
    puts "  Fanout depth 2: [llength $fanout_cells] cells"
}

puts "\n=== Checkpoint Validation ==="

# Validate checkpoint files
set checkpoint_files [glob -nocomplain "$checkpoint_dir/*.rpt"]
puts "Generated [llength $checkpoint_files] timing report files:"
foreach file $checkpoint_files {
    set filesize [file size $file]
    puts "  [file tail $file]: $filesize bytes"
}

# Summary statistics
puts "\n=== Test Summary ==="
puts "Checkpoint directory: $checkpoint_dir"
puts "JSON checkpoint data: $checkpoint_dir/timing_checkpoints.json"
puts "Timing reports: [llength $checkpoint_files] files"

# Calculate storage efficiency simulation
set total_report_size 0
foreach file $checkpoint_files {
    incr total_report_size [file size $file]
}

set estimated_compressed_size [expr {$total_report_size * 0.3}]
set compression_ratio [expr {$estimated_compressed_size / double($total_report_size)}]
set storage_reduction [expr {(1.0 - $compression_ratio) * 100}]

puts "Storage analysis:"
puts "  Total reports size: [expr {$total_report_size / 1024}] KB"
puts "  Estimated compressed: [expr {$estimated_compressed_size / 1024}] KB"
puts "  Compression ratio: [format %.3f $compression_ratio]"
puts "  Storage reduction: [format %.1f $storage_reduction]%"

puts "\n=========================================="
puts "GCD Timing Checkpoint Test COMPLETED"
puts "=========================================="

# Optional: Exit after completion
# exit 0
