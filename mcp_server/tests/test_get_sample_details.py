"""Tests for get_sample_details.py"""
from unittest.mock import patch

from mcp.types import ResourceLink

from get_sample_details import get_sample_details

_LINK = ResourceLink(
    type="resource_link", uri="pipeline-docs://sample_metadata_schema",
    name="sample_metadata_schema", description="test", mime_type="text/markdown",
)


class TestGetSampleDetails:

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_find_sample_by_sample_id(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": "sample1", "accession": "ACC1", "tissue": "brain"},
        ]
        result = get_sample_details("s1", ["sample1"])
        assert result.structured_content["samples"][0]["status"] == "ok"
        assert result.structured_content["samples"][0]["sample_id"] == "sample1"
        assert result.structured_content["samples"][0]["tissue"] == "brain"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_find_sample_by_accession(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": "sample1", "accession": "ACC1"},
        ]
        result = get_sample_details("s1", ["ACC1"])
        assert result.structured_content["samples"][0]["status"] == "ok"
        assert result.structured_content["samples"][0]["sample_id"] == "sample1"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_sample_not_found(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": "sample1", "accession": "ACC1"},
        ]
        result = get_sample_details("s1", ["missing"])
        assert result.structured_content["samples"][0]["status"] == "not_found"
        assert result.structured_content["samples"][0]["sample_id"] == "missing"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_filters_wrong_study(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": "sample1", "accession": "ACC1"},
            {"study_id": "s2", "sample_id": "sample1", "accession": "ACC1"},
        ]
        result = get_sample_details("s1", ["sample1"])
        assert result.structured_content["samples"][0]["status"] == "ok"
        assert result.structured_content["samples"][0]["study_id"] == "s1"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_multiple_samples_mixed(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": "s1a", "accession": "A1"},
            {"study_id": "s1", "sample_id": "s1b", "accession": "A2"},
        ]
        result = get_sample_details("s1", ["s1a", "missing", "s1b"])
        assert len(result.structured_content["samples"]) == 3
        assert result.structured_content["samples"][0]["status"] == "ok"
        assert result.structured_content["samples"][1]["status"] == "not_found"
        assert result.structured_content["samples"][2]["status"] == "ok"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_empty_sample_ids_list(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = []
        result = get_sample_details("s1", [])
        assert result.structured_content["samples"] == []

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_empty_catalog(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = []
        result = get_sample_details("s1", ["s1a"])
        assert result.structured_content["samples"][0]["status"] == "not_found"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_summary_text_correct(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = []
        result = get_sample_details("s1", ["id1", "id2", "id3"])
        assert result.content[0].text.startswith("Retrieved detail for 3 sample id(s) in s1.")

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_resource_link_attached(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = []
        result = get_sample_details("s1", [])
        assert len(result.content) == 2
        assert result.content[1] == _LINK
        mock_link.assert_called_once()

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_preserves_all_source_fields(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {
                "study_id": "s1", "sample_id": "s1a", "accession": "A1",
                "raw": {"characteristics": {"age": 50}}, "title": "My Sample",
                "instrument_model": "Illumina NovaSeq", "library_strategy": "RNA-Seq",
                "extra_field": "extra_value",
            },
        ]
        result = get_sample_details("s1", ["s1a"])
        sample = result.structured_content["samples"][0]
        assert sample["raw"] == {"characteristics": {"age": 50}}
        assert sample["title"] == "My Sample"
        assert sample["instrument_model"] == "Illumina NovaSeq"
        assert sample["library_strategy"] == "RNA-Seq"
        assert sample["extra_field"] == "extra_value"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_sample_with_none_accession(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": "s1a", "accession": None},
        ]
        result = get_sample_details("s1", ["s1a"])
        assert result.structured_content["samples"][0]["status"] == "ok"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_sample_with_none_sample_id(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": None, "accession": "A1"},
        ]
        result = get_sample_details("s1", ["A1"])
        assert result.structured_content["samples"][0]["status"] == "ok"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_overlapping_keys_last_wins(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": "dup", "accession": "A1", "data": "first"},
            {"study_id": "s1", "sample_id": "dup", "accession": "A2", "data": "second"},
        ]
        result = get_sample_details("s1", ["dup"])
        assert result.structured_content["samples"][0]["data"] == "second"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_preserves_input_order(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": "a"},
            {"study_id": "s1", "sample_id": "b"},
            {"study_id": "s1", "sample_id": "c"},
        ]
        result = get_sample_details("s1", ["c", "a", "b"])
        samples = result.structured_content["samples"]
        assert samples[0]["sample_id"] == "c"
        assert samples[1]["sample_id"] == "a"
        assert samples[2]["sample_id"] == "b"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_get_samples_called_once(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = []
        get_sample_details("s1", ["x", "y"])
        mock_get_samples.assert_called_once()

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_study_id_case_sensitive(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "Study1", "sample_id": "s1"},
        ]
        result = get_sample_details("study1", ["s1"])
        assert result.structured_content["samples"][0]["status"] == "not_found"

    @patch('get_sample_details.get_samples')
    @patch('get_sample_details.rl.sample_metadata_link', return_value=_LINK)
    def test_single_sample_response_structure(self, mock_link, mock_get_samples):
        mock_get_samples.return_value = [
            {"study_id": "s1", "sample_id": "s1a", "field": "val"},
        ]
        result = get_sample_details("s1", ["s1a"])
        sample = result.structured_content["samples"][0]
        assert "status" in sample
        assert "sample_id" in sample
        assert "study_id" in sample
        assert "field" in sample
