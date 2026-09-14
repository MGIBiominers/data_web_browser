"""Tests for tool_response.py"""
import json

from mcp.types import CallToolResult, ResourceLink, TextContent

from tool_response import build_result

_LINK = ResourceLink(
    type="resource_link", uri="pipeline-docs://h5ad_schema",
    name="h5ad_schema", description="test", mime_type="text/markdown",
)


class TestBuildResult:

    def test_returns_call_tool_result(self):
        result = build_result("Found 1 study.", {"studies": [{"study_id": "s1"}]})
        assert isinstance(result, CallToolResult)

    def test_text_content_starts_with_summary(self):
        result = build_result("Found 3 matching studies.", {"studies": []})
        assert result.content[0].text.startswith("Found 3 matching studies.")

    def test_full_data_present_in_text_content(self):
        """The actual bug this exists to prevent: a client that only reads
        `content` (not structured_content) must still see the real data --
        not just a bare summary line."""
        data = {"studies": [{"study_id": "Zelic2025_Immunity", "available_externally": True}]}
        result = build_result("Found 1 study.", data)
        text = result.content[0].text
        assert "Zelic2025_Immunity" in text
        assert "available_externally" in text
        assert "true" in text.lower()

    def test_text_content_json_round_trips_to_same_data(self):
        data = {"studies": [{"study_id": "s1"}, {"study_id": "s2"}], "count": 2}
        result = build_result("Found 2 studies.", data)
        # The JSON portion is everything after the summary line + blank line.
        json_part = result.content[0].text.split("\n\n", 1)[1]
        assert json.loads(json_part) == data

    def test_structured_content_still_set(self):
        data = {"studies": [{"study_id": "s1"}]}
        result = build_result("Found 1 study.", data)
        assert result.structured_content == data

    def test_no_extra_content_by_default(self):
        result = build_result("summary", {})
        assert len(result.content) == 1
        assert isinstance(result.content[0], TextContent)

    def test_extra_content_appended_after_text(self):
        result = build_result("summary", {}, extra_content=[_LINK])
        assert len(result.content) == 2
        assert result.content[1] is _LINK

    def test_multiple_extra_content_blocks_appended_in_order(self):
        link2 = ResourceLink(
            type="resource_link", uri="pipeline-docs://bulk_rnaseq_schema",
            name="bulk_rnaseq_schema", description="test", mime_type="text/markdown",
        )
        result = build_result("summary", {}, extra_content=[_LINK, link2])
        assert result.content[1] is _LINK
        assert result.content[2] is link2

    def test_empty_extra_content_list_same_as_none(self):
        result = build_result("summary", {}, extra_content=[])
        assert len(result.content) == 1

    def test_nested_structures_serialize_correctly(self):
        data = {"studies": [{"study_id": "s1", "accessions": {"gse": ["GSE1", "GSE2"]}, "tags": []}]}
        result = build_result("summary", data)
        json_part = result.content[0].text.split("\n\n", 1)[1]
        assert json.loads(json_part) == data

    def test_none_values_serialize_as_null(self):
        data = {"study_id": "s1", "doi": None}
        result = build_result("summary", data)
        assert "null" in result.content[0].text

    def test_non_json_serializable_value_falls_back_to_str(self):
        """default=str is a safety net -- our tool data is always plain
        dicts/lists/strings/numbers/bools/None in practice, but this
        shouldn't crash if something unexpected slips through."""
        class Weird:
            def __str__(self):
                return "weird-object"
        result = build_result("summary", {"value": Weird()})
        assert "weird-object" in result.content[0].text
