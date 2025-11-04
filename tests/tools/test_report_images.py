"""Tests for Report Images MCP Tools implementation."""

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from openroad_mcp.tools.report_images import (
    ListReportImagesTool,
    ReadReportImageTool,
    classify_image_type,
)


class TestClassifyImageType:
    """Test suite for classify_image_type helper function."""

    def test_classify_cts_images(self):
        """Test classification of CTS stage images."""
        assert classify_image_type("cts_clk.webp") == ("cts", "clock_visualization")
        assert classify_image_type("cts_clk_layout.webp") == ("cts", "clock_layout")
        assert classify_image_type("cts_core_clock.webp") == ("cts", "core_clock_visualization")
        assert classify_image_type("cts_core_clock_layout.webp") == ("cts", "core_clock_layout")

    def test_classify_final_images(self):
        """Test classification of final stage images."""
        assert classify_image_type("final_all.webp") == ("final", "complete_design")
        assert classify_image_type("final_clocks.webp") == ("final", "clock_routing")
        assert classify_image_type("final_congestion.webp") == ("final", "congestion_heatmap")
        assert classify_image_type("final_ir_drop.webp") == ("final", "ir_drop_analysis")
        assert classify_image_type("final_placement.webp") == ("final", "cell_placement")
        assert classify_image_type("final_resizer.webp") == ("final", "resizer_results")
        assert classify_image_type("final_routing.webp") == ("final", "routing_visualization")

    def test_classify_unknown_images(self):
        """Test classification of unknown image types."""
        assert classify_image_type("unknown_image.webp") == ("unknown", "unknown")
        assert classify_image_type("no_underscore.webp") == ("no", "unknown")


@pytest.mark.asyncio
class TestListReportImagesTool:
    """Test suite for ListReportImagesTool."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock OpenROADManager."""
        return AsyncMock()

    @pytest.fixture
    def tool(self, mock_manager):
        """Create ListReportImagesTool with mock manager."""
        return ListReportImagesTool(mock_manager)

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with test ORFS path."""
        with patch("openroad_mcp.tools.report_images.settings") as mock:
            mock.ORFS_FLOW_PATH = "/test/orfs/flow"
            yield mock

    async def test_list_images_reports_directory_not_found(self, tool, mock_settings):
        """Test error when reports directory doesn't exist."""
        result_json = await tool.execute("nangate45", "gcd", "run-123")
        result = json.loads(result_json)

        assert result["error"] == "ReportsDirectoryNotFound"
        assert "Reports directory not found" in result["message"]

    async def test_list_images_run_slug_not_found(self, tool, mock_settings, tmp_path):
        """Test error when run slug doesn't exist."""
        reports_dir = tmp_path / "reports" / "nangate45" / "gcd"
        reports_dir.mkdir(parents=True)

        mock_settings.ORFS_FLOW_PATH = str(tmp_path)

        result_json = await tool.execute("nangate45", "gcd", "nonexistent-run")
        result = json.loads(result_json)

        assert result["error"] == "RunSlugNotFound"
        assert "Run slug 'nonexistent-run' not found" in result["message"]

    async def test_list_images_no_webp_files(self, tool, mock_settings, tmp_path):
        """Test listing when no webp images exist."""
        run_path = tmp_path / "reports" / "nangate45" / "gcd" / "sweep-2025" / "run-123"
        run_path.mkdir(parents=True)

        mock_settings.ORFS_FLOW_PATH = str(tmp_path)

        result_json = await tool.execute("nangate45", "gcd", "run-123")
        result = json.loads(result_json)

        assert result["total_images"] == 0
        assert result["images_by_stage"] == {}
        assert "No webp images found" in result["message"]

    async def test_list_images_success_all_stages(self, tool, mock_settings, tmp_path):
        """Test successful listing of all images."""
        run_path = tmp_path / "reports" / "nangate45" / "gcd" / "sweep-2025" / "run-123"
        run_path.mkdir(parents=True)

        (run_path / "cts_clk.webp").write_bytes(b"fake cts image")
        (run_path / "final_all.webp").write_bytes(b"fake final image")
        (run_path / "final_routing.webp").write_bytes(b"fake routing image")

        mock_settings.ORFS_FLOW_PATH = str(tmp_path)

        result_json = await tool.execute("nangate45", "gcd", "run-123", "all")
        result = json.loads(result_json)

        assert result["error"] is None
        assert result["total_images"] == 3
        assert "cts" in result["images_by_stage"]
        assert "final" in result["images_by_stage"]
        assert len(result["images_by_stage"]["cts"]) == 1
        assert len(result["images_by_stage"]["final"]) == 2

        cts_image = result["images_by_stage"]["cts"][0]
        assert cts_image["filename"] == "cts_clk.webp"
        assert cts_image["type"] == "clock_visualization"
        assert cts_image["size_bytes"] == 14

    async def test_list_images_filter_by_stage(self, tool, mock_settings, tmp_path):
        """Test filtering images by stage."""
        run_path = tmp_path / "reports" / "nangate45" / "gcd" / "sweep-2025" / "run-123"
        run_path.mkdir(parents=True)

        (run_path / "cts_clk.webp").write_bytes(b"fake cts image")
        (run_path / "final_all.webp").write_bytes(b"fake final image")

        mock_settings.ORFS_FLOW_PATH = str(tmp_path)

        result_json = await tool.execute("nangate45", "gcd", "run-123", "cts")
        result = json.loads(result_json)

        assert result["total_images"] == 1
        assert "cts" in result["images_by_stage"]
        assert "final" not in result["images_by_stage"]

    async def test_list_images_unexpected_error(self, tool, mock_settings):
        """Test handling of unexpected errors."""
        with patch("openroad_mcp.tools.report_images.Path") as mock_path:
            mock_path.side_effect = Exception("Unexpected filesystem error")

            result_json = await tool.execute("nangate45", "gcd", "run-123")
            result = json.loads(result_json)

            assert result["error"] == "UnexpectedError"
            assert "Unexpected filesystem error" in result["message"]


@pytest.mark.asyncio
class TestReadReportImageTool:
    """Test suite for ReadReportImageTool."""

    @pytest.fixture
    def mock_manager(self):
        """Create a mock OpenROADManager."""
        return AsyncMock()

    @pytest.fixture
    def tool(self, mock_manager):
        """Create ReadReportImageTool with mock manager."""
        return ReadReportImageTool(mock_manager)

    @pytest.fixture
    def mock_settings(self):
        """Mock settings with test ORFS path."""
        with patch("openroad_mcp.tools.report_images.settings") as mock:
            mock.ORFS_FLOW_PATH = "/test/orfs/flow"
            yield mock

    async def test_read_image_reports_directory_not_found(self, tool, mock_settings):
        """Test error when reports directory doesn't exist."""
        result_json = await tool.execute("nangate45", "gcd", "run-123", "final_all.webp")
        result = json.loads(result_json)

        assert result["error"] == "ReportsDirectoryNotFound"
        assert "Reports directory not found" in result["message"]

    async def test_read_image_run_slug_not_found(self, tool, mock_settings, tmp_path):
        """Test error when run slug doesn't exist."""
        reports_dir = tmp_path / "reports" / "nangate45" / "gcd"
        reports_dir.mkdir(parents=True)

        mock_settings.ORFS_FLOW_PATH = str(tmp_path)

        result_json = await tool.execute("nangate45", "gcd", "nonexistent-run", "final_all.webp")
        result = json.loads(result_json)

        assert result["error"] == "RunSlugNotFound"
        assert "Run slug 'nonexistent-run' not found" in result["message"]

    async def test_read_image_not_found(self, tool, mock_settings, tmp_path):
        """Test error when image doesn't exist."""
        run_path = tmp_path / "reports" / "nangate45" / "gcd" / "sweep-2025" / "run-123"
        run_path.mkdir(parents=True)

        (run_path / "existing.webp").write_bytes(b"fake image")

        mock_settings.ORFS_FLOW_PATH = str(tmp_path)

        result_json = await tool.execute("nangate45", "gcd", "run-123", "missing.webp")
        result = json.loads(result_json)

        assert result["error"] == "ImageNotFound"
        assert "Image 'missing.webp' not found" in result["message"]
        assert "existing.webp" in result["message"]

    async def test_read_image_success(self, tool, mock_settings, tmp_path):
        """Test successful image reading."""
        run_path = tmp_path / "reports" / "nangate45" / "gcd" / "sweep-2025" / "run-123"
        run_path.mkdir(parents=True)

        test_image_data = b"fake webp image data"
        image_file = run_path / "final_all.webp"
        image_file.write_bytes(test_image_data)

        mock_settings.ORFS_FLOW_PATH = str(tmp_path)

        with patch("openroad_mcp.tools.report_images.Image") as mock_image:
            mock_img = MagicMock()
            mock_img.size = (1920, 1080)
            mock_image.open.return_value.__enter__.return_value = mock_img

            result_json = await tool.execute("nangate45", "gcd", "run-123", "final_all.webp")
            result = json.loads(result_json)

            assert result["error"] is None
            assert result["image_data"] is not None

            decoded_data = base64.b64decode(result["image_data"])
            assert decoded_data == test_image_data

            metadata = result["metadata"]
            assert metadata["filename"] == "final_all.webp"
            assert metadata["format"] == "webp"
            assert metadata["size_bytes"] == len(test_image_data)
            assert metadata["width"] == 1920
            assert metadata["height"] == 1080
            assert metadata["stage"] == "final"
            assert metadata["type"] == "complete_design"

    async def test_read_image_dimensions_extraction_failure(self, tool, mock_settings, tmp_path):
        """Test handling when image dimensions cannot be extracted."""
        run_path = tmp_path / "reports" / "nangate45" / "gcd" / "sweep-2025" / "run-123"
        run_path.mkdir(parents=True)

        test_image_data = b"fake webp image data"
        image_file = run_path / "final_all.webp"
        image_file.write_bytes(test_image_data)

        mock_settings.ORFS_FLOW_PATH = str(tmp_path)

        with patch("openroad_mcp.tools.report_images.Image") as mock_image:
            mock_image.open.side_effect = Exception("Cannot read image")

            result_json = await tool.execute("nangate45", "gcd", "run-123", "final_all.webp")
            result = json.loads(result_json)

            assert result["error"] is None
            metadata = result["metadata"]
            assert metadata["width"] is None
            assert metadata["height"] is None

    async def test_read_image_unexpected_error(self, tool, mock_settings):
        """Test handling of unexpected errors."""
        with patch("openroad_mcp.tools.report_images.Path") as mock_path:
            mock_path.side_effect = Exception("Unexpected filesystem error")

            result_json = await tool.execute("nangate45", "gcd", "run-123", "final_all.webp")
            result = json.loads(result_json)

            assert result["error"] == "UnexpectedError"
            assert "Unexpected filesystem error" in result["message"]
