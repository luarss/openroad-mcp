"""Delta-compressed checkpoint system implementation."""

import base64
import json
from pathlib import Path
from typing import Any

from ..core.manager import OpenROADManager
from ..utils.logging import get_logger
from .models import ChangeType, CheckpointManager, CompressedDelta, TimingDataChange, TimingStage


class TimingCheckpointSystem:
    """Manages delta-compressed timing checkpoints."""

    def __init__(self, manager: OpenROADManager, checkpoint_dir: str = "./timing_checkpoints"):
        self.manager = manager
        self.checkpoint_dir = Path(checkpoint_dir)
        self.checkpoint_dir.mkdir(exist_ok=True)
        self.checkpoint_manager = CheckpointManager()
        self.logger = get_logger("checkpoint_system")

    async def create_checkpoint(self, stage_name: str, force_base: bool = False) -> TimingStage:
        """Create a new timing checkpoint."""
        try:
            # Get current timing data from OpenROAD
            timing_data = await self._extract_timing_data()

            # Determine if this should be a base checkpoint
            is_base = force_base or len(self.checkpoint_manager.checkpoints) == 0

            # Create new stage
            stage = TimingStage(
                stage_name=stage_name,
                is_base_checkpoint=is_base,
                path_count=len(timing_data.get("paths", {})),
                wns=timing_data.get("wns"),
                tns=timing_data.get("tns"),
            )

            if not is_base and self.checkpoint_manager.checkpoints:
                # Create delta from most recent checkpoint
                latest_stage = max(self.checkpoint_manager.checkpoints.values(), key=lambda s: s.timestamp)
                stage.create_delta_from_previous(latest_stage, timing_data, self.checkpoint_manager)
            else:
                # Create base checkpoint with full data
                changes = [
                    TimingDataChange(path=path_id, change_type=ChangeType.ADD, new_value=path_data)
                    for path_id, path_data in timing_data.get("paths", {}).items()
                ]
                stage.delta_changes = CompressedDelta(changes=changes)
                stage.delta_changes.compress()

            # Add to manager and persist
            self.checkpoint_manager.add_checkpoint(stage)
            await self._persist_checkpoint(stage)

            self.logger.info(f"Created checkpoint '{stage_name}' (ID: {stage.stage_id})")
            storage_stats = stage.estimate_storage_size()
            self.logger.info(
                f"Storage: {storage_stats['compressed_bytes']} bytes compressed "
                f"({storage_stats['uncompressed_bytes']} uncompressed)"
            )

            return stage

        except Exception as e:
            self.logger.error(f"Failed to create checkpoint: {e}")
            raise

    async def restore_checkpoint(self, stage_id: str) -> dict[str, Any]:
        """Restore timing state from checkpoint."""
        try:
            # Get checkpoint chain
            chain = self.checkpoint_manager.get_checkpoint_chain(stage_id)
            self.logger.info(f"Restoring checkpoint chain of {len(chain)} stages")

            # Reconstruct timing data by applying deltas
            timing_data = {}

            for stage in chain:
                deltas = stage.delta_changes.decompress()

                for change in deltas:
                    if change.change_type == ChangeType.ADD:
                        timing_data[change.path] = change.new_value
                    elif change.change_type == ChangeType.MODIFY:
                        timing_data[change.path] = change.new_value
                    elif change.change_type == ChangeType.DELETE:
                        timing_data.pop(change.path, None)

            # Apply timing data to OpenROAD (simplified - would use actual OpenDB APIs)
            await self._apply_timing_data(timing_data)

            # Get the restored stage for metrics
            restored_stage = self.checkpoint_manager.checkpoints[stage_id]

            self.logger.info(f"Successfully restored checkpoint {stage_id}")
            return {
                "paths": timing_data,
                "wns": restored_stage.wns,
                "tns": restored_stage.tns,
            }

        except Exception as e:
            self.logger.error(f"Failed to restore checkpoint {stage_id}: {e}")
            raise

    async def _extract_timing_data(self) -> dict[str, Any]:
        """Extract timing data from OpenROAD."""
        # This is a simplified example - real implementation would use OpenDB APIs
        # and OpenSTA commands to extract actual timing data

        try:
            # Execute timing analysis commands
            result = await self.manager.execute_command("report_checks -format json")

            # Parse timing data (simplified)
            timing_data: dict[str, Any] = {"paths": {}, "wns": None, "tns": None}

            # In practice, this would parse actual OpenSTA output
            if result.stdout:
                # Simulate parsing timing paths
                for i, _line in enumerate(result.stdout[:10]):  # First 10 lines as example
                    timing_data["paths"][f"path_{i}"] = {
                        "slack": -0.1 * i,
                        "delay": 1.0 + 0.1 * i,
                        "startpoint": f"reg_{i}",
                        "endpoint": f"reg_{i + 1}",
                    }

                # Extract WNS/TNS from output
                timing_data["wns"] = -0.5  # Example value
                timing_data["tns"] = -2.1  # Example value

            return timing_data

        except Exception as e:
            self.logger.error(f"Failed to extract timing data: {e}")
            return {"paths": {}, "wns": None, "tns": None}

    async def _apply_timing_data(self, timing_data: dict[str, Any]) -> None:
        """Apply timing data to OpenROAD."""
        # This would use OpenDB APIs to restore timing state
        # For now, just log the restoration
        self.logger.info(f"Applying timing data with {len(timing_data.get('paths', {}))} paths")

    async def _persist_checkpoint(self, stage: TimingStage) -> None:
        """Persist checkpoint to disk."""
        checkpoint_file = self.checkpoint_dir / f"{stage.stage_id}.json"

        with open(checkpoint_file, "w") as f:
            # Convert bytes to base64 for JSON serialization
            stage_dict = stage.model_dump()
            if stage.delta_changes.compressed_data:
                stage_dict["delta_changes"]["compressed_data"] = base64.b64encode(
                    stage.delta_changes.compressed_data
                ).decode("utf-8")

            json.dump(stage_dict, f, indent=2, default=str)

    async def load_checkpoint(self, stage_id: str) -> TimingStage:
        """Load checkpoint from disk."""
        checkpoint_file = self.checkpoint_dir / f"{stage_id}.json"

        if not checkpoint_file.exists():
            raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_file}")

        with open(checkpoint_file) as f:
            stage_dict = json.load(f)
            if stage_dict.get("delta_changes", {}).get("compressed_data"):
                stage_dict["delta_changes"]["compressed_data"] = base64.b64decode(
                    stage_dict["delta_changes"]["compressed_data"]
                )

            stage = TimingStage.model_validate(stage_dict)
            return stage

    def get_storage_statistics(self) -> dict[str, Any]:
        """Get comprehensive storage statistics."""
        stats = self.checkpoint_manager.get_storage_stats()

        # Add file system stats
        total_disk_size = sum(f.stat().st_size for f in self.checkpoint_dir.glob("*.json") if f.is_file())

        stats.update(
            {
                "disk_storage_bytes": total_disk_size,
                "checkpoint_directory": str(self.checkpoint_dir),
                "files_on_disk": len(list(self.checkpoint_dir.glob("*.json"))),
            }
        )

        return stats

    async def cleanup_old_checkpoints(self, keep_count: int = 10) -> None:
        """Clean up old checkpoints to save storage."""
        if len(self.checkpoint_manager.checkpoints) <= keep_count:
            return

        # Sort by timestamp, keep most recent
        sorted_checkpoints = sorted(
            self.checkpoint_manager.checkpoints.items(), key=lambda x: x[1].timestamp, reverse=True
        )

        to_remove = sorted_checkpoints[keep_count:]

        for stage_id, stage in to_remove:
            # Don't remove base checkpoints
            if not stage.is_base_checkpoint:
                # Remove from memory
                del self.checkpoint_manager.checkpoints[stage_id]

                # Remove from disk
                checkpoint_file = self.checkpoint_dir / f"{stage_id}.json"
                if checkpoint_file.exists():
                    checkpoint_file.unlink()

                self.logger.info(f"Cleaned up checkpoint {stage_id}")
