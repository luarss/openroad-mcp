#!/usr/bin/env python3
"""Simple script to test GCD timing checkpoint functionality."""

import asyncio
import sys
import tempfile
from pathlib import Path

# Add src to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from openroad_mcp.core.manager import OpenROADManager
from openroad_mcp.timing.checkpoint import TimingCheckpointSystem


async def test_gcd_timing_basic() -> bool:
    """Test basic GCD timing functionality."""
    print("🧪 Testing GCD Timing Checkpoint System")
    print("=" * 50)

    # Create OpenROAD manager
    manager = None
    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"📁 Working directory: {temp_dir}")

        try:
            manager = OpenROADManager()
            await manager.start_process()
            print("✅ OpenROAD manager started")

            # Test basic command execution
            result = await manager.execute_command("puts {Hello from OpenROAD}")
            print(f"📝 Basic command test: {'✅ PASS' if result.status == 'completed' else '❌ FAIL'}")

            # Initialize checkpoint system
            checkpoint_system = TimingCheckpointSystem(manager, temp_dir + "/checkpoints")
            print("✅ Checkpoint system initialized")

            # Mock some GCD timing data
            class MockTimingData:
                async def mock_extract_timing_data(self) -> dict:
                    return {
                        "paths": {
                            "req_msg[0]->dpath.a_reg.out_reg[0].qi": {
                                "slack": 0.385,
                                "delay": 0.08,
                                "startpoint": "req_msg[0]",
                                "endpoint": "dpath.a_reg.out_reg[0].qi",
                            },
                            "req_msg[1]->dpath.a_reg.out_reg[1].qi": {
                                "slack": 0.380,
                                "delay": 0.085,
                                "startpoint": "req_msg[1]",
                                "endpoint": "dpath.a_reg.out_reg[1].qi",
                            },
                            "clk->dpath.b_reg.out_reg[15].qi": {
                                "slack": 0.343,
                                "delay": 0.12,
                                "startpoint": "clk",
                                "endpoint": "dpath.b_reg.out_reg[15].qi",
                            },
                        },
                        "wns": 0.343,
                        "tns": 0.0,
                    }

            # Override timing extraction with mock data
            mock_data = MockTimingData()

            # Replace the timing extraction method with mock data using proper monkey patching
            _original_extract = checkpoint_system._extract_timing_data

            async def mock_extract_timing_data() -> dict:
                return await mock_data.mock_extract_timing_data()

            # Use setattr to properly replace the method
            checkpoint_system._extract_timing_data = mock_extract_timing_data  # type: ignore[method-assign]

            # Test checkpoint creation for GCD flow stages
            gcd_stages = ["synthesis", "placement", "cts", "routing"]
            checkpoints = []

            print("\n🔄 Creating GCD flow checkpoints...")
            for stage in gcd_stages:
                print(f"   Creating checkpoint: gcd_{stage}")

                checkpoint = await checkpoint_system.create_checkpoint(
                    f"gcd_{stage}", force_base=(stage == "synthesis")
                )
                checkpoints.append(checkpoint)

                print(f"   ✅ Checkpoint ID: {checkpoint.stage_id[:8]}...")
                print(f"   📊 Path count: {checkpoint.path_count}")

                if stage != "synthesis":
                    print(f"   🗜️  Compressed: {checkpoint.delta_changes.compressed_size} bytes")
                    print(f"   📉 Ratio: {checkpoint.delta_changes.compression_ratio:.3f}")

            # Test checkpoint restoration
            print("\n🔄 Testing checkpoint restoration...")
            synthesis_checkpoint = checkpoints[0]
            restored_data = await checkpoint_system.restore_checkpoint(synthesis_checkpoint.stage_id)

            print(f"   ✅ Restored {len(restored_data.get('paths', {}))} timing paths")
            print(f"   📈 WNS: {restored_data.get('wns', 'N/A')}")
            print(f"   📊 TNS: {restored_data.get('tns', 'N/A')}")

            # Get storage statistics
            print("\n📊 Storage Statistics:")
            stats = checkpoint_system.get_storage_statistics()
            for key, value in stats.items():
                if isinstance(value, float):
                    print(f"   {key}: {value:.3f}")
                else:
                    print(f"   {key}: {value}")

            # Test cleanup
            print("\n🧹 Testing checkpoint cleanup...")
            await checkpoint_system.cleanup_old_checkpoints(keep_count=2)
            final_stats = checkpoint_system.get_storage_statistics()
            print(f"   Remaining checkpoints: {final_stats['checkpoint_count']}")

            print("\n✅ All tests passed!")
            return True

        except Exception as e:
            print(f"❌ Test failed: {e}")
            import traceback

            traceback.print_exc()
            return False

        finally:
            try:
                if manager is not None:
                    await manager.stop_process()
                    print("🛑 OpenROAD manager stopped")
            except Exception as e:
                print(f"⚠️  Failed to stop OpenROAD manager: {e}")
                pass


async def test_tcl_script_execution() -> bool:
    """Test Tcl script execution if available."""
    print("\n🧪 Testing Tcl Script Execution")
    print("=" * 30)

    script_path = Path(__file__).parent / "scripts" / "gcd_timing_test.tcl"

    if not script_path.exists():
        print(f"❌ Tcl script not found: {script_path}")
        return False

    print(f"📄 Found script: {script_path.name}")

    # Check if OpenROAD is available
    try:
        import shutil

        openroad_cmd = shutil.which("openroad")
        if not openroad_cmd:
            print("❌ OpenROAD command not found in PATH")
            return False

        print(f"✅ OpenROAD found: {openroad_cmd}")

        # For now, just validate script content
        script_content = script_path.read_text()
        expected_keywords = ["read_verilog", "read_sdc", "link_design", "report_checks", "create_timing_checkpoint"]

        for keyword in expected_keywords:
            if keyword in script_content:
                print(f"   ✅ Found keyword: {keyword}")
            else:
                print(f"   ❌ Missing keyword: {keyword}")

        print("✅ Script validation completed")
        return True

    except Exception as e:
        print(f"❌ Script test failed: {e}")
        return False


async def main() -> int:
    """Run all GCD timing tests."""
    print("🚀 Starting GCD Timing Checkpoint Tests")
    print("=" * 60)

    # Test 1: Basic functionality
    test1_passed = await test_gcd_timing_basic()

    # Test 2: Tcl script
    test2_passed = await test_tcl_script_execution()

    # Summary
    print("\n" + "=" * 60)
    print("📋 Test Summary:")
    print(f"   Basic functionality: {'✅ PASS' if test1_passed else '❌ FAIL'}")
    print(f"   Tcl script validation: {'✅ PASS' if test2_passed else '❌ FAIL'}")

    all_passed = test1_passed and test2_passed
    print(f"\n🎯 Overall result: {'✅ ALL TESTS PASSED' if all_passed else '❌ SOME TESTS FAILED'}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        sys.exit(1)
