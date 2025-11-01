"""Unit tests for timing parsers"""

from openroad_mcp.timing.parsers import BasicTimingParser


class TestWNSTNSParsing:
    """Test WNS/TNS value extraction"""

    def test_parse_wns_positive(self):
        output = "wns 2.45"
        result = BasicTimingParser.parse_wns_tns(output, "report_wns")
        assert result["value"] == 2.45
        assert result["type"] == "wns"

    def test_parse_wns_negative(self):
        output = "wns -1.23"
        result = BasicTimingParser.parse_wns_tns(output, "report_wns")
        assert result["value"] == -1.23

    def test_parse_tns(self):
        output = "tns -45.67"
        result = BasicTimingParser.parse_wns_tns(output, "report_tns")
        assert result["value"] == -45.67
        assert result["type"] == "tns"

    def test_parse_wns_not_found(self):
        output = "No timing data available"
        result = BasicTimingParser.parse_wns_tns(output, "report_wns")
        assert result["value"] is None
        assert "error" in result


class TestReportChecksParsing:
    """Test report_checks path extraction"""

    def test_parse_single_path(self):
        output = (
            "Startpoint: _692_ (rising edge-triggered flip-flop clocked by clk)\n"
            "Endpoint: _693_ (rising edge-triggered flip-flop clocked by clk)\n"
            "Path Group: clk\n"
            "Path Type: max\n"
            "\n"
            "            2.80   data arrival time\n"
            "            4.90   data required time\n"
            "            2.10   slack (MET)\n"
        )
        paths = BasicTimingParser.parse_report_checks(output)
        assert len(paths) == 1

        path = paths[0]
        assert path.startpoint == "_692_"
        assert path.endpoint == "_693_"
        assert path.path_group == "clk"
        assert path.slack == 2.10
        assert path.arrival == 2.80
        assert path.required == 4.90

    def test_parse_multiple_paths(self):
        output = """Startpoint: _692_
Endpoint: _693_
Path Group: clk
            2.10   slack (MET)

Startpoint: _700_
Endpoint: _701_
Path Group: clk
           -0.50   slack (VIOLATED)
"""
        paths = BasicTimingParser.parse_report_checks(output)
        assert len(paths) == 2
        assert paths[0].slack == 2.10
        assert paths[1].slack == -0.50

    def test_parse_empty_output(self):
        output = ""
        paths = BasicTimingParser.parse_report_checks(output)
        assert len(paths) == 0


class TestFaninFanoutParsing:
    """Test fanin/fanout pin extraction"""

    def test_parse_fanin_simple(self):
        output = """
inst1/pin1
inst2/pin2
inst3/pin3
"""
        pins = BasicTimingParser.parse_fanin_fanout(output)
        assert len(pins) == 3
        assert pins[0] == "inst1/pin1"
        assert pins[1] == "inst2/pin2"

    def test_parse_with_comments(self):
        output = """
# Fanin cone
inst1/pin1
inst2/pin2
"""
        pins = BasicTimingParser.parse_fanin_fanout(output)
        assert len(pins) == 2
        assert "# Fanin cone" not in pins


class TestErrorDetection:
    """Test error detection in output"""

    def test_detect_error_keyword(self):
        output = "[ERROR] File not found: design.odb"
        error = BasicTimingParser.detect_error(output)
        assert error is not None
        assert "ERROR" in error

    def test_detect_no_error(self):
        output = "wns 2.45"
        error = BasicTimingParser.detect_error(output)
        assert error is None
