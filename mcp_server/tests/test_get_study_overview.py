"""Tests for get_study_overview.py"""
from unittest.mock import patch

from mcp.types import ResourceLink

from get_study_overview import get_study_overview

_LINK = ResourceLink(
    type="resource_link", uri="pipeline-docs://h5ad_schema",
    name="h5ad_schema", description="test", mime_type="text/markdown",
)

_STUDY = {
    "study_id": "study1",
    "title": "Study One",
    "journal": "Nature",
    "year": "2026",
    "doi": None,
    "pmid": None,
    "bioproject": None,
    "gse": ["GSE1"],
    "cellxgene_collection": None,
    "synapse": None,
    "summary": "summary",
    "readme_body": "full readme",
    "notes": None,
    "series_summaries": [],
    "organisms": ["Homo sapiens"],
    "disease_statuses": ["ALS"],
    "tissues": ["spinal cord"],
    "assay_types": ["snRNA-seq"],
    "n_samples": 2,
    "access_restricted": False,
    "available_externally": False,
    "processed_files": [
        {"name": "a.h5ad", "category": "data", "bytes": 100, "s3_key": "processed/study1/a.h5ad"},
        {"name": "b.h5ad", "category": "data", "bytes": 200, "s3_key": None},
    ],
}


class TestGetStudyOverview:

    @patch('get_study_overview.rl.for_formats', return_value=[])
    @patch('get_study_overview.get_samples', return_value=[])
    @patch('get_study_overview.get_catalog')
    def test_not_found(self, mock_get_catalog, mock_get_samples, mock_for_formats):
        mock_get_catalog.return_value = {"studies": []}
        result = get_study_overview(["missing"])
        assert result.structured_content["studies"][0]["status"] == "not_found"

    @patch('get_study_overview.rl.for_formats', return_value=[])
    @patch('get_study_overview.get_samples', return_value=[])
    @patch('get_study_overview.get_catalog')
    def test_per_file_downloadable_flag_reflects_real_s3_key(self, mock_get_catalog, mock_get_samples, mock_for_formats):
        """The actual bug: a file existing in processed_files (real, locally
        converted) does not mean it was ever synced to S3 -- only a real
        s3_key means it's actually downloadable. get_study_overview must
        expose this per file, not just imply availability from the file's
        mere presence."""
        mock_get_catalog.return_value = {"studies": [_STUDY]}
        result = get_study_overview(["study1"])
        entry = result.structured_content["studies"][0]
        files_by_name = {f["name"]: f for f in entry["processed_files"]}

        assert files_by_name["a.h5ad"]["downloadable"] is True
        assert files_by_name["b.h5ad"]["downloadable"] is False
        assert entry["available_externally"] is False

    @patch('get_study_overview.rl.for_formats', return_value=[])
    @patch('get_study_overview.get_samples', return_value=[])
    @patch('get_study_overview.get_catalog')
    def test_available_externally_true_when_study_flag_true(self, mock_get_catalog, mock_get_samples, mock_for_formats):
        study = {**_STUDY, "available_externally": True}
        mock_get_catalog.return_value = {"studies": [study]}
        result = get_study_overview(["study1"])
        assert result.structured_content["studies"][0]["available_externally"] is True

    @patch('get_study_overview.rl.for_formats', return_value=[])
    @patch('get_study_overview.get_samples', return_value=[])
    @patch('get_study_overview.get_catalog')
    def test_access_restricted_omits_htcf_path(self, mock_get_catalog, mock_get_samples, mock_for_formats):
        study = {**_STUDY, "access_restricted": True}
        mock_get_catalog.return_value = {"studies": [study]}
        result = get_study_overview(["study1"])
        entry = result.structured_content["studies"][0]
        assert "htcf_processed_path" not in entry

    @patch('get_study_overview.rl.for_formats', return_value=[])
    @patch('get_study_overview.get_samples', return_value=[])
    @patch('get_study_overview.get_catalog')
    def test_unrestricted_includes_htcf_path(self, mock_get_catalog, mock_get_samples, mock_for_formats):
        mock_get_catalog.return_value = {"studies": [_STUDY]}
        result = get_study_overview(["study1"])
        entry = result.structured_content["studies"][0]
        assert entry["htcf_processed_path"] == "/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS/studies/study1/processed/"

    @patch('get_study_overview.rl.for_formats', return_value=[])
    @patch('get_study_overview.rl.sample_metadata_link', return_value=_LINK)
    @patch('get_study_overview.get_samples')
    @patch('get_study_overview.get_catalog')
    def test_samples_capped_and_truncation_flagged(self, mock_get_catalog, mock_get_samples, mock_sample_link, mock_for_formats):
        mock_get_catalog.return_value = {"studies": [_STUDY]}
        mock_get_samples.return_value = [
            {"study_id": "study1", "sample_id": f"s{i}"} for i in range(150)
        ]
        result = get_study_overview(["study1"])
        entry = result.structured_content["studies"][0]
        assert len(entry["samples"]) == 100
        assert entry["samples_truncated"] is True
        assert entry["total_samples"] == 150
        assert _LINK in result.content
