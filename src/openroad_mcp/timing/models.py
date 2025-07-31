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

    def create_delta_from_previous(self, previous_stage: "TimingStage", timing_data: dict[str, Any]) -> None:
        """Create delta changes from previous stage."""
        changes = []

        # Compare with previous stage data (simplified example)
        # In practice, this would compare actual OpenDB timing data
        paths_data = timing_data.get("paths", timing_data)
        for path_id, path_data in paths_data.items():
            # This is a simplified example - real implementation would
            # extract timing data from OpenDB and compare
            change = TimingDataChange(path=path_id, change_type=ChangeType.MODIFY, new_value=path_data)
            changes.append(change)

        self.delta_changes = CompressedDelta(changes=changes)
        self.delta_changes.compress()
        self.base_checkpoint_ref = previous_stage.stage_id

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
