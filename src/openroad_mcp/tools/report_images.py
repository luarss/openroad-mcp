"""Report image reading tools for OpenROAD MCP server."""

import base64
from datetime import datetime
from pathlib import Path

from PIL import Image

from ..config.settings import settings
from ..core.models import ImageInfo, ImageMetadata, ListImagesResult, ReadImageResult
from ..utils.logging import get_logger
from .base import BaseTool

logger = get_logger("report_images")


IMAGE_TYPE_MAPPING = {
    "cts_clk": "clock_visualization",
    "cts_clk_layout": "clock_layout",
    "cts_core_clock": "core_clock_visualization",
    "cts_core_clock_layout": "core_clock_layout",
    "final_all": "complete_design",
    "final_clocks": "clock_routing",
    "final_congestion": "congestion_heatmap",
    "final_ir_drop": "ir_drop_analysis",
    "final_placement": "cell_placement",
    "final_resizer": "resizer_results",
    "final_routing": "routing_visualization",
}


def classify_image_type(filename: str) -> tuple[str, str]:
    """Classify image by stage and type based on filename.

    Args:
        filename: Image filename (e.g., "final_all.webp")

    Returns:
        Tuple of (stage, type) where stage is "cts" or "final" and type describes the image
    """
    base_name = filename.rsplit(".", 1)[0]

    stage = base_name.split("_")[0] if "_" in base_name else "unknown"

    image_type = IMAGE_TYPE_MAPPING.get(base_name, "unknown")

    return stage, image_type


class ListReportImagesTool(BaseTool):
    """Tool for listing available report images from ORFS runs."""

    async def execute(self, platform: str, design: str, run_slug: str, stage: str = "all") -> str:
        """List available report images for a specific run.

        Args:
            platform: Platform name (e.g., "nangate45")
            design: Design name (e.g., "gcd")
            run_slug: Run identifier (e.g., "5b5d17f3-a40b-4a9a-ab26-77160b16f27b-_CORE_ASPECT_RATIO_0.5")
            stage: Filter by stage ("cts", "final", or "all")

        Returns:
            JSON formatted result with list of images organized by stage
        """
        try:
            orfs_flow_path = Path(settings.ORFS_FLOW_PATH).expanduser()

            reports_base = orfs_flow_path / "reports" / platform / design
            if not reports_base.exists():
                logger.warning(f"Reports directory not found: {reports_base}")
                return self._format_result(
                    ListImagesResult(
                        error="ReportsDirectoryNotFound",
                        message=f"Reports directory not found: {reports_base}. "
                        "Check ORFS_FLOW_PATH configuration and ensure ORFS has been run.",
                    )
                )

            run_dirs = list(reports_base.glob(f"*/{run_slug}"))
            if not run_dirs:
                logger.warning(f"Run slug not found: {run_slug}")
                available_runs = [d.name for d in reports_base.rglob("*") if d.is_dir() and "-" in d.name]
                return self._format_result(
                    ListImagesResult(
                        error="RunSlugNotFound",
                        message=f"Run slug '{run_slug}' not found in {reports_base}. "
                        f"Available run slugs: {', '.join(available_runs[:5]) if available_runs else 'none'}",
                    )
                )

            run_path = run_dirs[0]

            webp_files = list(run_path.glob("*.webp"))

            if not webp_files:
                logger.warning(f"No webp images found in {run_path}")
                return self._format_result(
                    ListImagesResult(
                        run_path=str(run_path),
                        total_images=0,
                        images_by_stage={},
                        message=f"No webp images found in {run_path}",
                    )
                )

            images_by_stage: dict[str, list[ImageInfo]] = {}

            for webp_file in webp_files:
                file_stage, file_type = classify_image_type(webp_file.name)

                if stage != "all" and file_stage != stage:
                    continue

                stat = webp_file.stat()

                image_info = ImageInfo(
                    filename=webp_file.name,
                    path=str(webp_file),
                    size_bytes=stat.st_size,
                    modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    type=file_type,
                )

                if file_stage not in images_by_stage:
                    images_by_stage[file_stage] = []
                images_by_stage[file_stage].append(image_info)

            for stage_images in images_by_stage.values():
                stage_images.sort(key=lambda x: x.filename)

            total_images = sum(len(images) for images in images_by_stage.values())

            result = ListImagesResult(
                run_path=str(run_path),
                total_images=total_images,
                images_by_stage=images_by_stage,
            )

            return self._format_result(result)

        except Exception as e:
            logger.exception(f"Failed to list report images: {e}")
            return self._format_result(
                ListImagesResult(
                    error="UnexpectedError",
                    message=f"Failed to list report images: {str(e)}",
                )
            )


class ReadReportImageTool(BaseTool):
    """Tool for reading report images and returning base64-encoded data with metadata."""

    async def execute(self, platform: str, design: str, run_slug: str, image_name: str) -> str:
        """Read a specific report image and return base64-encoded data.

        Args:
            platform: Platform name (e.g., "nangate45")
            design: Design name (e.g., "gcd")
            run_slug: Run identifier
            image_name: Image filename (e.g., "final_all.webp")

        Returns:
            JSON formatted result with base64-encoded image data and metadata
        """
        try:
            orfs_flow_path = Path(settings.ORFS_FLOW_PATH).expanduser()

            reports_base = orfs_flow_path / "reports" / platform / design
            if not reports_base.exists():
                logger.warning(f"Reports directory not found: {reports_base}")
                return self._format_result(
                    ReadImageResult(
                        error="ReportsDirectoryNotFound",
                        message=f"Reports directory not found: {reports_base}. Check ORFS_FLOW_PATH configuration.",
                    )
                )

            run_dirs = list(reports_base.glob(f"*/{run_slug}"))
            if not run_dirs:
                logger.warning(f"Run slug not found: {run_slug}")
                return self._format_result(
                    ReadImageResult(
                        error="RunSlugNotFound",
                        message=f"Run slug '{run_slug}' not found in {reports_base}. "
                        "Use list_report_images to see available runs.",
                    )
                )

            run_path = run_dirs[0]
            image_path = run_path / image_name

            if not image_path.exists():
                logger.warning(f"Image not found: {image_path}")
                available_images = [f.name for f in run_path.glob("*.webp")]
                return self._format_result(
                    ReadImageResult(
                        error="ImageNotFound",
                        message=f"Image '{image_name}' not found in {run_path}. "
                        f"Available images: {', '.join(available_images) if available_images else 'none'}. "
                        "Use list_report_images to see all available images.",
                    )
                )

            with open(image_path, "rb") as f:
                image_bytes = f.read()

            image_data_b64 = base64.b64encode(image_bytes).decode("utf-8")

            stat = image_path.stat()
            file_stage, file_type = classify_image_type(image_name)

            width = None
            height = None
            try:
                with Image.open(image_path) as img:
                    width, height = img.size
            except Exception as e:
                logger.warning(f"Failed to extract image dimensions: {e}")

            metadata = ImageMetadata(
                filename=image_name,
                format="webp",
                size_bytes=stat.st_size,
                width=width,
                height=height,
                modified_time=datetime.fromtimestamp(stat.st_mtime).isoformat(),
                stage=file_stage,
                type=file_type,
            )

            result = ReadImageResult(
                image_data=image_data_b64,
                metadata=metadata,
            )

            return self._format_result(result)

        except Exception as e:
            logger.exception(f"Failed to read report image: {e}")
            return self._format_result(
                ReadImageResult(
                    error="UnexpectedError",
                    message=f"Failed to read report image: {str(e)}",
                )
            )
