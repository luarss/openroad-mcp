"""Tests for delta-compressed checkpoint system."""

import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.openroad_mcp.timing.checkpoint import TimingCheckpointSystem
from src.openroad_mcp.timing.models import ChangeType, TimingDataChange, TimingStage


@pytest.fixture
def mock_manager():
    """Mock OpenROAD manager."""
    manager = MagicMock()
    manager.execute_command = AsyncMock()
    return manager


@pytest.fixture
def checkpoint_system(mock_manager):
    """Create checkpoint system with temporary directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        system = TimingCheckpointSystem(mock_manager, temp_dir)
        yield system


@pytest.mark.asyncio
async def test_create_base_checkpoint(checkpoint_system, mock_manager):
    """Test creating a base checkpoint."""
    # Mock timing data extraction
    mock_manager.execute_command.return_value = MagicMock(stdout=["Path 1: slack=-0.1", "Path 2: slack=-0.2"])

    # Create checkpoint
    stage = await checkpoint_system.create_checkpoint("synthesis", force_base=True)

    assert stage.stage_name == "synthesis"
    assert stage.is_base_checkpoint is True
    assert stage.path_count == 2  # Based on mock data
    assert len(stage.delta_changes.changes) > 0


@pytest.mark.asyncio
async def test_create_delta_checkpoint(checkpoint_system, mock_manager):
    """Test creating a delta checkpoint."""
    # Mock timing data
    mock_manager.execute_command.return_value = MagicMock(stdout=["Path 1: slack=-0.1", "Path 2: slack=-0.2"])

    # Create base checkpoint first
    base_stage = await checkpoint_system.create_checkpoint("synthesis", force_base=True)

    # Create delta checkpoint
    delta_stage = await checkpoint_system.create_checkpoint("placement")

    assert delta_stage.is_base_checkpoint is False
    assert delta_stage.base_checkpoint_ref == base_stage.stage_id


@pytest.mark.asyncio
async def test_checkpoint_compression(checkpoint_system):
    """Test that checkpoints are properly compressed."""
    # Create a stage with test data
    stage = TimingStage(stage_name="test", is_base_checkpoint=True)

    # Add changes
    changes = [
        TimingDataChange(
            path=f"path_{i}", change_type=ChangeType.ADD, new_value={"slack": -0.1 * i, "delay": 1.0 + 0.1 * i}
        )
        for i in range(100)  # Create substantial data
    ]

    stage.delta_changes.changes = changes
    stage.delta_changes.compress()

    # Verify compression occurred
    assert stage.delta_changes.compressed_data is not None
    assert stage.delta_changes.compressed_size > 0
    assert stage.delta_changes.compression_ratio < 1.0  # Should be compressed
    assert stage.delta_changes.checksum != ""


@pytest.mark.asyncio
async def test_checkpoint_restoration(checkpoint_system, mock_manager):
    """Test checkpoint restoration."""
    # Mock timing data
    mock_manager.execute_command.return_value = MagicMock(stdout=["Path 1: slack=-0.1"])

    # Create checkpoint
    stage = await checkpoint_system.create_checkpoint("test_stage")

    # Restore checkpoint
    restored_data = await checkpoint_system.restore_checkpoint(stage.stage_id)

    assert "paths" in restored_data
    assert restored_data["wns"] is not None


def test_storage_statistics(checkpoint_system):
    """Test storage statistics calculation."""
    # Add some mock checkpoints
    for i in range(3):
        stage = TimingStage(stage_name=f"stage_{i}")
        checkpoint_system.checkpoint_manager.add_checkpoint(stage)

    stats = checkpoint_system.get_storage_statistics()

    assert "checkpoint_count" in stats
    assert "total_storage_bytes" in stats
    assert "compression_ratio" in stats
    assert stats["checkpoint_count"] == 3


@pytest.mark.asyncio
async def test_checkpoint_persistence(checkpoint_system):
    """Test checkpoint persistence to disk."""
    stage = TimingStage(stage_name="persist_test", is_base_checkpoint=True)

    # Persist checkpoint
    await checkpoint_system._persist_checkpoint(stage)

    # Verify file exists
    checkpoint_file = checkpoint_system.checkpoint_dir / f"{stage.stage_id}.json"
    assert checkpoint_file.exists()

    # Load and verify
    loaded_stage = await checkpoint_system.load_checkpoint(stage.stage_id)
    assert loaded_stage.stage_name == stage.stage_name
    assert loaded_stage.stage_id == stage.stage_id


def test_compression_decompression_integrity():
    """Test that compression/decompression maintains data integrity."""
    changes = [
        TimingDataChange(
            path=f"critical_path_{i}",
            change_type=ChangeType.MODIFY,
            old_value={"slack": -0.2 * i},
            new_value={"slack": -0.1 * i, "improved": True},
        )
        for i in range(50)
    ]

    from src.openroad_mcp.timing.models import CompressedDelta

    delta = CompressedDelta(changes=changes)

    # Compress
    delta.compress()

    # Decompress and verify
    decompressed_changes = delta.decompress()

    assert len(decompressed_changes) == len(changes)
    for orig, decomp in zip(changes, decompressed_changes, strict=False):
        assert orig.path == decomp.path
        assert orig.change_type == decomp.change_type
        assert orig.new_value == decomp.new_value


@pytest.mark.asyncio
async def test_cleanup_old_checkpoints(checkpoint_system):
    """Test cleanup of old checkpoints."""
    # Create multiple checkpoints
    stages = []
    for i in range(15):
        stage = TimingStage(stage_name=f"stage_{i}")
        checkpoint_system.checkpoint_manager.add_checkpoint(stage)
        await checkpoint_system._persist_checkpoint(stage)
        stages.append(stage)

    initial_count = len(checkpoint_system.checkpoint_manager.checkpoints)
    assert initial_count == 15

    # Cleanup, keeping only 10
    await checkpoint_system.cleanup_old_checkpoints(keep_count=10)

    # Verify cleanup
    remaining_count = len(checkpoint_system.checkpoint_manager.checkpoints)
    assert remaining_count <= 10
