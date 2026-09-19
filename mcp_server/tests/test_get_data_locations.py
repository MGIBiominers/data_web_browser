"""Tests for get_data_locations.py"""
from unittest.mock import patch

from get_data_locations import get_data_locations

_CATALOG = {
    "source_root": "/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS",
    "studies": [
        {
            "study_id": "Zelic2025_Immunity",
            "processed_files": [
                {"name": "study.h5ad", "bytes": 100, "category": "data"},
                {"name": "conversion_log.md", "bytes": 10, "category": "doc"},
                {"name": "bulk_counts.parquet", "bytes": 50, "category": "data"},
            ],
        },
        {"study_id": "NoDataYet", "processed_files": []},
    ],
}


class TestGetDataLocations:

    @patch('get_data_locations.get_catalog', return_value=_CATALOG)
    def test_returns_real_htcf_directory_path(self, mock_catalog):
        result = get_data_locations(["Zelic2025_Immunity"])
        study = result.structured_content["studies"][0]
        assert study["directory"] == (
            "/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS"
            "/studies/Zelic2025_Immunity/processed/"
        )

    @patch('get_data_locations.get_catalog', return_value=_CATALOG)
    def test_only_data_category_files_listed(self, mock_catalog):
        result = get_data_locations(["Zelic2025_Immunity"])
        files = result.structured_content["studies"][0]["files"]
        names = {f["filename"] for f in files}
        assert names == {"study.h5ad", "bulk_counts.parquet"}
        assert "conversion_log.md" not in names

    @patch('get_data_locations.get_catalog', return_value=_CATALOG)
    def test_no_url_or_download_field_anywhere(self, mock_catalog):
        """The core regression test for this tool's whole purpose: it must
        never hand back a URL or any other way to fetch file contents --
        only a real filesystem path."""
        result = get_data_locations(["Zelic2025_Immunity"])
        text = result.content[0].text
        assert "http://" not in text
        assert "https://" not in text
        for f in result.structured_content["studies"][0]["files"]:
            assert "url" not in f

    @patch('get_data_locations.get_catalog', return_value=_CATALOG)
    def test_format_filter_narrows_files(self, mock_catalog):
        result = get_data_locations(["Zelic2025_Immunity"], formats=["parquet"])
        files = result.structured_content["studies"][0]["files"]
        assert [f["filename"] for f in files] == ["bulk_counts.parquet"]

    @patch('get_data_locations.get_catalog', return_value=_CATALOG)
    def test_study_not_found_goes_to_excluded(self, mock_catalog):
        result = get_data_locations(["nonexistent"])
        assert result.structured_content["studies"] == []
        assert result.structured_content["excluded"] == [
            {"study_id": "nonexistent", "status": "not_found"}
        ]

    @patch('get_data_locations.get_catalog', return_value=_CATALOG)
    def test_study_with_no_processed_data_goes_to_excluded(self, mock_catalog):
        result = get_data_locations(["NoDataYet"])
        assert result.structured_content["studies"] == []
        assert result.structured_content["excluded"] == [
            {"study_id": "NoDataYet", "status": "no_processed_data"}
        ]

    @patch('get_data_locations.get_catalog', return_value=_CATALOG)
    def test_multiple_studies_mixed_results(self, mock_catalog):
        result = get_data_locations(["Zelic2025_Immunity", "NoDataYet", "nonexistent"])
        assert len(result.structured_content["studies"]) == 1
        assert len(result.structured_content["excluded"]) == 2

    @patch('get_data_locations.get_catalog', return_value=_CATALOG)
    def test_summary_reflects_counts(self, mock_catalog):
        result = get_data_locations(["Zelic2025_Immunity", "NoDataYet"])
        assert result.content[0].text.startswith(
            "HTCF processed-data location(s) for 1 of 2 requested studies."
        )

    @patch('get_data_locations.get_catalog', return_value=_CATALOG)
    def test_resource_links_attached_for_present_formats(self, mock_catalog):
        result = get_data_locations(["Zelic2025_Immunity"])
        uris = {c.uri for c in result.content[1:]}
        assert "pipeline-docs://h5ad_schema" in uris
        assert "pipeline-docs://bulk_rnaseq_schema" in uris
