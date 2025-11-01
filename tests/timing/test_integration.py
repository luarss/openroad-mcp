"""Integration tests for timing analysis with real ORFS designs"""

from pathlib import Path

import pytest

from openroad_mcp.core.manager import OpenROADManager
from openroad_mcp.timing.session import TimingSession

ORFS_BASE = Path("/home/luars/OpenROAD-flow-scripts/flow")
NANGATE45_PLATFORM = ORFS_BASE / "platforms/nangate45"
GCD_DESIGN = ORFS_BASE / "designs/nangate45/gcd"
GCD_RESULTS = ORFS_BASE / "results/nangate45/gcd/tune-2025-09-16_15-25-30/variant-AutoTunerBase-9ea812a2-or-0"

LIBERTY_FILE = NANGATE45_PLATFORM / "lib/NangateOpenCellLibrary_typical.lib"
TECH_LEF = NANGATE45_PLATFORM / "lef/NangateOpenCellLibrary.tech.lef"
MACRO_LEF = NANGATE45_PLATFORM / "lef/NangateOpenCellLibrary.macro.lef"
VERILOG_FILE = GCD_RESULTS / "1_synth.v"
SDC_FILE = GCD_DESIGN / "constraint.sdc"


@pytest.fixture
def skip_if_orfs_missing():
    """Skip test if ORFS files are not available"""
    if not LIBERTY_FILE.exists():
        pytest.skip("ORFS nangate45 platform not found")


@pytest.mark.asyncio
async def test_complete_timing_flow(skip_if_orfs_missing):
    """Test complete timing analysis flow with real ORFS files"""
    manager = OpenROADManager()

    session_id = await manager.create_session()
    interactive_session = manager._sessions[session_id]

    timing_session = TimingSession(session_id, interactive_session)

    await interactive_session.send_command(f"read_liberty {LIBERTY_FILE}")
    await interactive_session.read_output(timeout_ms=10000)

    await interactive_session.send_command(f"read_lef {TECH_LEF}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command(f"read_lef {MACRO_LEF}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command(f"read_verilog {VERILOG_FILE}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command("link_design gcd")
    await interactive_session.read_output(timeout_ms=3000)

    await interactive_session.send_command(f"read_sdc {SDC_FILE}")
    await interactive_session.read_output(timeout_ms=3000)

    timing_session.design_name = "gcd"

    wns_result = await timing_session.execute_sta_command("report_wns", use_cache=True)

    assert wns_result.command == "report_wns"
    assert wns_result.cached is False
    assert wns_result.error is None
    assert "value" in wns_result.data
    assert isinstance(wns_result.data["value"], float)

    wns_cached = await timing_session.execute_sta_command("report_wns", use_cache=True)
    assert wns_cached.cached is True
    assert wns_cached.data == wns_result.data

    tns_result = await timing_session.execute_sta_command("report_tns", use_cache=True)
    assert tns_result.error is None
    assert "value" in tns_result.data

    summary = await timing_session.get_summary()
    assert summary.design_name == "gcd"
    assert summary.wns is not None
    assert summary.tns is not None

    await manager.cleanup_all()


@pytest.mark.asyncio
async def test_cache_invalidation(skip_if_orfs_missing):
    """Test that cache is cleared when loading new design"""
    manager = OpenROADManager()

    session_id = await manager.create_session()
    interactive_session = manager._sessions[session_id]

    timing_session = TimingSession(session_id, interactive_session)

    await interactive_session.send_command(f"read_liberty {LIBERTY_FILE}")
    await interactive_session.read_output(timeout_ms=10000)

    await interactive_session.send_command(f"read_lef {TECH_LEF}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command(f"read_lef {MACRO_LEF}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command(f"read_verilog {VERILOG_FILE}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command("link_design gcd")
    await interactive_session.read_output(timeout_ms=3000)

    await interactive_session.send_command(f"read_sdc {SDC_FILE}")
    await interactive_session.read_output(timeout_ms=3000)

    timing_session.design_name = "gcd"

    result1 = await timing_session.execute_sta_command("report_wns", use_cache=True)
    assert not result1.cached

    result2 = await timing_session.execute_sta_command("report_wns", use_cache=True)
    assert result2.cached

    timing_session._cache.clear()

    result3 = await timing_session.execute_sta_command("report_wns", use_cache=True)
    assert not result3.cached

    await manager.cleanup_all()


@pytest.mark.asyncio
async def test_no_cache_mode(skip_if_orfs_missing):
    """Test that use_cache=False bypasses cache"""
    manager = OpenROADManager()

    session_id = await manager.create_session()
    interactive_session = manager._sessions[session_id]

    timing_session = TimingSession(session_id, interactive_session)

    await interactive_session.send_command(f"read_liberty {LIBERTY_FILE}")
    await interactive_session.read_output(timeout_ms=10000)

    await interactive_session.send_command(f"read_lef {TECH_LEF}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command(f"read_lef {MACRO_LEF}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command(f"read_verilog {VERILOG_FILE}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command("link_design gcd")
    await interactive_session.read_output(timeout_ms=3000)

    await interactive_session.send_command(f"read_sdc {SDC_FILE}")
    await interactive_session.read_output(timeout_ms=3000)

    timing_session.design_name = "gcd"

    result1 = await timing_session.execute_sta_command("report_wns", use_cache=False)
    assert not result1.cached

    result2 = await timing_session.execute_sta_command("report_wns", use_cache=False)
    assert not result2.cached

    await manager.cleanup_all()


@pytest.mark.asyncio
async def test_report_checks_parsing(skip_if_orfs_missing):
    """Test parsing of report_checks output"""
    manager = OpenROADManager()

    session_id = await manager.create_session()
    interactive_session = manager._sessions[session_id]

    timing_session = TimingSession(session_id, interactive_session)

    await interactive_session.send_command(f"read_liberty {LIBERTY_FILE}")
    await interactive_session.read_output(timeout_ms=10000)

    await interactive_session.send_command(f"read_lef {TECH_LEF}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command(f"read_lef {MACRO_LEF}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command(f"read_verilog {VERILOG_FILE}")
    await interactive_session.read_output(timeout_ms=5000)

    await interactive_session.send_command("link_design gcd")
    await interactive_session.read_output(timeout_ms=3000)

    await interactive_session.send_command(f"read_sdc {SDC_FILE}")
    await interactive_session.read_output(timeout_ms=3000)

    timing_session.design_name = "gcd"

    result = await timing_session.execute_sta_command(
        "report_checks -path_delay max -format full_clock_expanded", use_cache=True
    )

    assert result.error is None
    assert "paths" in result.data
    assert len(result.data["paths"]) > 0

    path = result.data["paths"][0]
    assert "startpoint" in path
    assert "endpoint" in path
    assert "slack" in path

    await manager.cleanup_all()
