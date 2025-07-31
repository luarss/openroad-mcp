"""Data models for timing analysis and checkpointing."""

import base64
import hashlib
import zlib
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field, field_serializer, field_validator


class CompressionType(str, Enum):
    """Supported compression algorithms."""

    ZLIB = "zlib"
    LZ4 = "lz4"  # Future: requires lz4 package
    ZSTD = "zstd"  # Future: requires zstandard package


class ChangeType(str, Enum):
    """Types of changes in delta compression."""

    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"


class TimingDataChange(BaseModel):
    """Represents a single timing data change."""

    path: str = Field(..., description="Path identifier (e.g., 'clk_to_q.data')")
    change_type: ChangeType
    old_value: dict[str, Any] | None = None
    new_value: dict[str, Any] | None = None
    timestamp: datetime = Field(default_factory=datetime.now)


class CompressedDelta(BaseModel):
    """Delta-compressed timing changes."""

    changes: list[TimingDataChange]
    compression_type: CompressionType = CompressionType.ZLIB
    compressed_data: bytes | None = None
    uncompressed_size: int = 0
    compressed_size: int = 0
    compression_ratio: float = 0.0
    checksum: str = Field(default="", description="SHA256 checksum for integrity")

    @field_serializer("compressed_data")
    def serialize_compressed_data(self, value: bytes | None) -> str | None:
        """Serialize bytes to base64 string for JSON compatibility."""
        if value is None:
            return None
        return base64.b64encode(value).decode("utf-8")

    @field_validator("compressed_data", mode="before")
    @classmethod
    def validate_compressed_data(cls, value: Any) -> bytes | None:
        """Validate and convert base64 string back to bytes."""
        if value is None:
            return None
        if isinstance(value, bytes):
            return value
        if isinstance(value, str):
            return base64.b64decode(value)
        raise ValueError(f"compressed_data must be bytes, str, or None, got {type(value)}")

    def compress(self) -> None:
        """Compress the changes data."""
        # Serialize changes to JSON bytes
        import json

        json_data = json.dumps([change.model_dump() for change in self.changes], default=str)
        raw_bytes = json_data.encode("utf-8")
        self.uncompressed_size = len(raw_bytes)

        # Apply compression
        if self.compression_type == CompressionType.ZLIB:
            self.compressed_data = zlib.compress(raw_bytes, level=6)
        else:
            # Fallback to zlib for unsupported types
            self.compressed_data = zlib.compress(raw_bytes, level=6)

        self.compressed_size = len(self.compressed_data)
        self.compression_ratio = self.compressed_size / self.uncompressed_size if self.uncompressed_size > 0 else 0.0

        # Generate checksum
        self.checksum = hashlib.sha256(self.compressed_data).hexdigest()

    def decompress(self) -> list[TimingDataChange]:
        """Decompress and return the changes."""
        if not self.compressed_data:
            return self.changes

        # Verify checksum
        actual_checksum = hashlib.sha256(self.compressed_data).hexdigest()
        if actual_checksum != self.checksum:
            raise ValueError(f"Checksum mismatch: expected {self.checksum}, got {actual_checksum}")

        # Decompress
        if self.compression_type == CompressionType.ZLIB:
            raw_bytes = zlib.decompress(self.compressed_data)
        else:
            # Fallback
            raw_bytes = zlib.decompress(self.compressed_data)

        # Deserialize
        import json

        json_data = json.loads(raw_bytes.decode("utf-8"))
        return [TimingDataChange.model_validate(change) for change in json_data]


class CacheIndex(BaseModel):
    """Cache metadata for multi-tier caching."""

    l1_keys: list[str] = Field(default_factory=list, description="L1 cache keys")
    l2_keys: list[str] = Field(default_factory=list, description="L2 cache keys")
    last_access: datetime = Field(default_factory=datetime.now)
    hit_count: int = 0
    miss_count: int = 0


class SpatialIndex(BaseModel):
    """Spatial indexing metadata for timing queries."""

    index_type: str = Field(default="kdtree", description="Type of spatial index")
    dimensions: int = Field(default=2, description="Number of dimensions")
    node_count: int = 0
    max_depth: int = 0
    build_time: float = 0.0
    last_rebuild: datetime = Field(default_factory=datetime.now)


class TimingStage(BaseModel):
    """Represents a timing analysis stage with delta compression."""

    stage_id: str = Field(default_factory=lambda: str(uuid4()))
    stage_name: str = Field(..., description="Human-readable stage name")
    timestamp: datetime = Field(default_factory=datetime.now)

    # Delta compression
    base_checkpoint_ref: str | None = None
    delta_changes: CompressedDelta = Field(default_factory=lambda: CompressedDelta(changes=[]))
    is_base_checkpoint: bool = False

    # Performance optimization
    timing_index: SpatialIndex = Field(default_factory=SpatialIndex)
    cache_metadata: CacheIndex = Field(default_factory=CacheIndex)

    # Metrics
    path_count: int = 0
    critical_path_count: int = 0
    wns: float | None = None  # Worst Negative Slack
    tns: float | None = None  # Total Negative Slack

    def create_delta_from_previous(
        self,
        previous_stage: "TimingStage",
        timing_data: dict[str, Any],
        checkpoint_manager: "CheckpointManager | None" = None,
    ) -> None:
        """Create delta changes from previous stage by comparing timing data."""
        changes = []

        # First, reconstruct the previous stage's timing data for comparison
        previous_timing_data = self._reconstruct_timing_data(previous_stage, checkpoint_manager)
        current_paths = timing_data.get("paths", {})
        previous_paths = previous_timing_data.get("paths", {})

        # Find all unique path IDs from both datasets
        all_paths = set(current_paths.keys()) | set(previous_paths.keys())

        for path_id in all_paths:
            current_path = current_paths.get(path_id)
            previous_path = previous_paths.get(path_id)

            if previous_path is None and current_path is not None:
                # New path added
                changes.append(
                    TimingDataChange(path=path_id, change_type=ChangeType.ADD, old_value=None, new_value=current_path)
                )

            elif previous_path is not None and current_path is None:
                # Path deleted
                changes.append(
                    TimingDataChange(
                        path=path_id, change_type=ChangeType.DELETE, old_value=previous_path, new_value=None
                    )
                )

            elif previous_path is not None and current_path is not None:
                # Path exists in both - check if modified
                if self._timing_data_differs(previous_path, current_path):
                    changes.append(
                        TimingDataChange(
                            path=path_id, change_type=ChangeType.MODIFY, old_value=previous_path, new_value=current_path
                        )
                    )

        # Set up delta compression
        self.delta_changes = CompressedDelta(changes=changes)
        self.delta_changes.compress()
        self.base_checkpoint_ref = previous_stage.stage_id

    def _reconstruct_timing_data(
        self, stage: "TimingStage", checkpoint_manager: "CheckpointManager | None" = None
    ) -> dict[str, Any]:
        """Reconstruct timing data from a stage and its delta chain."""
        timing_data: dict[str, Any] = {"paths": {}}

        # Build the reconstruction chain - we need to get all stages back to base
        reconstruction_chain: list[TimingStage] = []
        current_stage: TimingStage | None = stage

        while current_stage is not None:
            reconstruction_chain.insert(0, current_stage)  # Insert at beginning for correct order

            if current_stage.is_base_checkpoint or not current_stage.base_checkpoint_ref:
                break

            # If we have access to checkpoint manager, follow the chain
            if checkpoint_manager and current_stage.base_checkpoint_ref:
                current_stage = checkpoint_manager.checkpoints.get(current_stage.base_checkpoint_ref)
            else:
                # Without checkpoint manager, we can only work with the current stage
                break

        # Apply deltas in order to reconstruct the timing data
        for stage_in_chain in reconstruction_chain:
            deltas = stage_in_chain.delta_changes.decompress()

            for change in deltas:
                if change.change_type == ChangeType.ADD and change.new_value is not None:
                    timing_data["paths"][change.path] = change.new_value
                elif change.change_type == ChangeType.MODIFY and change.new_value is not None:
                    timing_data["paths"][change.path] = change.new_value
                elif change.change_type == ChangeType.DELETE:
                    timing_data["paths"].pop(change.path, None)

        return timing_data

    def _timing_data_differs(self, data1: dict[str, Any], data2: dict[str, Any]) -> bool:
        """Compare two timing data dictionaries to detect changes."""
        # Define comparison tolerance for floating point values
        TOLERANCE = 1e-9

        # Check if keys are different
        if set(data1.keys()) != set(data2.keys()):
            return True

        # Compare each field
        for key in data1.keys():
            val1 = data1[key]
            val2 = data2[key]

            # Handle numeric comparisons with tolerance
            if isinstance(val1, (int | float)) and isinstance(val2, (int | float)):
                if abs(val1 - val2) > TOLERANCE:
                    return True
            # Handle string and other type comparisons
            elif val1 != val2:
                return True

        return False

    def estimate_storage_size(self) -> dict[str, int]:
        """Estimate storage requirements."""
        return {
            "uncompressed_bytes": self.delta_changes.uncompressed_size,
            "compressed_bytes": self.delta_changes.compressed_size,
            "metadata_bytes": len(self.model_dump_json()),
            "total_bytes": self.delta_changes.compressed_size + len(self.model_dump_json()),
        }


class CheckpointManager(BaseModel):
    """Manages timing checkpoints with delta compression."""

    checkpoints: dict[str, TimingStage] = Field(default_factory=dict)
    base_checkpoints: list[str] = Field(default_factory=list)
    max_delta_chain_length: int = Field(default=10, description="Max deltas before creating new base")
    total_storage_bytes: int = 0

    def add_checkpoint(self, stage: TimingStage) -> None:
        """Add a timing checkpoint."""
        self.checkpoints[stage.stage_id] = stage

        # Update storage tracking
        storage = stage.estimate_storage_size()
        self.total_storage_bytes += storage["total_bytes"]

        # Maintain base checkpoints
        if stage.is_base_checkpoint:
            self.base_checkpoints.append(stage.stage_id)

    def get_checkpoint_chain(self, stage_id: str) -> list[TimingStage]:
        """Get the chain of checkpoints needed to reconstruct a stage."""
        if stage_id not in self.checkpoints:
            raise ValueError(f"Checkpoint {stage_id} not found")

        chain: list[TimingStage] = []
        current_stage: TimingStage | None = self.checkpoints[stage_id]

        while current_stage:
            chain.insert(0, current_stage)

            if current_stage.is_base_checkpoint or not current_stage.base_checkpoint_ref:
                break

            current_stage = self.checkpoints.get(current_stage.base_checkpoint_ref)

        return chain

    def get_storage_stats(self) -> dict[str, Any]:
        """Get storage statistics."""
        total_uncompressed = sum(cp.delta_changes.uncompressed_size for cp in self.checkpoints.values())
        total_compressed = sum(cp.delta_changes.compressed_size for cp in self.checkpoints.values())

        return {
            "checkpoint_count": len(self.checkpoints),
            "base_checkpoint_count": len(self.base_checkpoints),
            "total_storage_bytes": self.total_storage_bytes,
            "total_uncompressed_bytes": total_uncompressed,
            "total_compressed_bytes": total_compressed,
            "compression_ratio": total_compressed / total_uncompressed if total_uncompressed > 0 else 0.0,
            "storage_reduction_percent": (1 - (total_compressed / total_uncompressed)) * 100
            if total_uncompressed > 0
            else 0.0,
        }
