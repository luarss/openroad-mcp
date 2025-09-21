#!/bin/bash

# ORFS GCD Timing Debug Demo - Setup Script

set -e

echo "🚀 Setting up ORFS GCD Timing Debug Demo"

# Check FLOW_HOME environment
if [ -z "$FLOW_HOME" ]; then
    export FLOW_HOME="$HOME/OpenROAD-flow-scripts"
    echo "📌 Setting FLOW_HOME to $FLOW_HOME"
else
    echo "📌 Using FLOW_HOME: $FLOW_HOME"
fi

# Validate FLOW_HOME exists
if [ ! -d "$FLOW_HOME" ]; then
    echo "❌ Error: FLOW_HOME directory does not exist: $FLOW_HOME"
    echo "   Please install OpenROAD-flow-scripts or set FLOW_HOME correctly"
    exit 1
fi

# Validate GCD design exists
GCD_CONFIG="$FLOW_HOME/flow/designs/nangate45/gcd/config.mk"
if [ ! -f "$GCD_CONFIG" ]; then
    echo "❌ Error: GCD design not found at: $GCD_CONFIG"
    echo "   Please ensure OpenROAD-flow-scripts is properly installed"
    exit 1
fi

echo "✅ OpenROAD-flow-scripts found at: $FLOW_HOME"
echo "✅ GCD design found at: $GCD_CONFIG"

# Check Python environment
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 not found"
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PYTHON_VERSION found"

# Install demo requirements
echo "📦 Installing demo requirements..."
if [ -f "../../pyproject.toml" ]; then
    cd ../..
    pip3 install -e ".[demo]" --quiet
    cd demo/orfs-gcd-timing
    echo "✅ Demo requirements installed"
else
    echo "⚠️  pyproject.toml not found, skipping requirements installation"
fi

# Make scripts executable
chmod +x run_demo.py

echo ""
echo "🎯 Demo setup complete! Ready to run:"
echo "   python run_demo.py"
echo ""
echo "📋 Demo will:"
echo "   1. Run ORFS GCD flow (2-3 minutes)"
echo "   2. Create timing violations"
echo "   3. Demonstrate AI-guided debugging"
echo "   4. Apply fixes and verify timing closure"
echo ""
