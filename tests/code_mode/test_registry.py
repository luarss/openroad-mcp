"""Tests for Code Mode command registry."""

from openroad_mcp.code_mode.models import CommandInfo
from openroad_mcp.code_mode.registry import CommandRegistry, registry


class TestCommandRegistry:
    """Tests for the CommandRegistry class."""

    def test_get_categories(self) -> None:
        """Test getting all categories."""
        categories = registry.get_categories()

        assert isinstance(categories, list)
        assert len(categories) > 0
        assert "reporting" in categories
        assert "query" in categories
        assert "timing" in categories
        assert "tcl_builtins" in categories

    def test_search_by_exact_name(self) -> None:
        """Test searching by exact command name."""
        results = registry.search("sta")

        assert len(results) >= 1
        assert any(cmd.name == "sta" for cmd in results)

        # Find the sta command
        sta_cmd = next(cmd for cmd in results if cmd.name == "sta")
        assert sta_cmd.category == "timing"
        assert "static timing analysis" in (sta_cmd.description or "").lower()

    def test_search_by_partial_name(self) -> None:
        """Test searching by partial command name."""
        results = registry.search("report_")

        assert len(results) >= 5  # Should find multiple report_* commands
        assert all(cmd.name.startswith("report_") for cmd in results)

    def test_search_by_category(self) -> None:
        """Test searching by category name."""
        results = registry.search("routing")

        assert len(results) >= 1
        # When searching by category, all results should be from that category
        # or have "routing" in the name/description

    def test_search_by_description_keyword(self) -> None:
        """Test searching by keyword in description."""
        results = registry.search("clock")

        assert len(results) >= 1
        # Should find clock-related commands
        names = [cmd.name for cmd in results]
        assert any("clock" in name.lower() for name in names)

    def test_search_empty_query(self) -> None:
        """Test search with empty query returns empty results."""
        results = registry.search("")

        assert results == []

    def test_search_no_match(self) -> None:
        """Test search with no matches."""
        results = registry.search("xyznonexistentcommand123")

        assert results == []

    def test_get_by_category_valid(self) -> None:
        """Test getting commands by valid category."""
        commands = registry.get_by_category("timing")

        assert len(commands) >= 1
        assert all(cmd.category == "timing" for cmd in commands)

    def test_get_by_category_invalid(self) -> None:
        """Test getting commands by invalid category."""
        commands = registry.get_by_category("nonexistent_category")

        assert commands == []

    def test_get_command_exists(self) -> None:
        """Test getting a specific existing command."""
        cmd = registry.get_command("global_placement")

        assert cmd is not None
        assert cmd.name == "global_placement"
        assert cmd.category == "placement"

    def test_get_command_not_exists(self) -> None:
        """Test getting a non-existent command."""
        cmd = registry.get_command("nonexistent_command_xyz")

        assert cmd is None

    def test_command_info_model(self) -> None:
        """Test CommandInfo model creation."""
        cmd = CommandInfo(
            name="test_command",
            category="test_category",
            description="Test description",
            arguments=["arg1", "arg2"],
            is_safe=True,
        )

        assert cmd.name == "test_command"
        assert cmd.category == "test_category"
        assert cmd.description == "Test description"
        assert cmd.arguments == ["arg1", "arg2"]
        assert cmd.is_safe is True

    def test_max_results_limit(self) -> None:
        """Test that search respects max_results parameter."""
        results = registry.search("report_", max_results=3)

        assert len(results) <= 3

    def test_tcl_builtins_are_safe(self) -> None:
        """Test that all Tcl builtins are marked as safe."""
        commands = registry.get_by_category("tcl_builtins")

        for cmd in commands:
            assert cmd.is_safe is True


class TestGlobalRegistry:
    """Tests for the global registry instance."""

    def test_global_registry_exists(self) -> None:
        """Test that the global registry instance exists."""
        assert registry is not None
        assert isinstance(registry, CommandRegistry)

    def test_global_registry_has_all_categories(self) -> None:
        """Test that global registry has all expected categories."""
        categories = registry.get_categories()

        expected_categories = [
            "reporting",
            "query",
            "constraints",
            "io",
            "floorplan",
            "placement",
            "routing",
            "cts",
            "timing",
            "verification",
            "utility",
            "tcl_builtins",
        ]

        for expected in expected_categories:
            assert expected in categories, f"Missing category: {expected}"
