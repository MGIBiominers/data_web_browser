"""Tests for search_studies.py"""
from unittest.mock import patch

from mcp.types import ResourceLink

from search_studies import search_studies

_LINK = ResourceLink(
    type="resource_link", uri="pipeline-docs://h5ad_schema",
    name="h5ad_schema", description="test", mime_type="text/markdown",
)

_PUBLISHED_STUDY = {
    "study_id": "published_study",
    "title": "A published study",
    "summary": "summary",
    "journal": "Nature",
    "year": "2026",
    "gse": ["GSE1"],
    "bioproject": None,
    "cellxgene_collection": None,
    "synapse": None,
    "n_samples": 10,
    "organisms": ["Homo sapiens"],
    "disease_statuses": ["ALS"],
    "tissues": ["spinal cord"],
    "assay_types": ["snRNA-seq"],
    "notes": None,
    "doi": None,
    "pmid": None,
    "access_restricted": False,
    "available_externally": True,
    "processed_files": [
        {"name": "study.h5ad", "category": "data", "bytes": 100, "s3_key": "processed/published_study/study.h5ad"},
    ],
}

_UNPUBLISHED_STUDY = {
    **_PUBLISHED_STUDY,
    "study_id": "unpublished_study",
    "gse": ["GSE2"],
    "available_externally": False,
    # Real bug this guards against: processed_files existing on HTCF (so
    # data_formats is non-empty) does NOT mean the study was ever synced to
    # S3 -- s3_key is only set once build_catalog.py's live S3 check
    # actually finds it there. A study can have real local processed files
    # and still be entirely unavailable through get_download_links.
    "processed_files": [
        {"name": "study.h5ad", "category": "data", "bytes": 100, "s3_key": None},
    ],
}


class TestSearchStudies:

    @patch('search_studies.rl.for_formats', return_value=[_LINK])
    @patch('search_studies.get_catalog')
    def test_no_filters_returns_all(self, mock_get_catalog, mock_for_formats):
        mock_get_catalog.return_value = {"studies": [_PUBLISHED_STUDY, _UNPUBLISHED_STUDY]}
        result = search_studies()
        assert len(result.structured_content["studies"]) == 2

    @patch('search_studies.rl.for_formats', return_value=[])
    @patch('search_studies.get_catalog')
    def test_available_externally_reflects_real_publish_state(self, mock_get_catalog, mock_for_formats):
        """The actual bug: a study with real local h5ad/parquet files but
        never synced to S3 must report available_externally=False even
        though data_formats is non-empty."""
        mock_get_catalog.return_value = {"studies": [_PUBLISHED_STUDY, _UNPUBLISHED_STUDY]}
        result = search_studies()
        by_id = {s["study_id"]: s for s in result.structured_content["studies"]}

        assert by_id["published_study"]["data_formats"] == ["h5ad"]
        assert by_id["published_study"]["available_externally"] is True

        assert by_id["unpublished_study"]["data_formats"] == ["h5ad"]
        assert by_id["unpublished_study"]["available_externally"] is False

    @patch('search_studies.rl.for_formats', return_value=[])
    @patch('search_studies.get_catalog')
    def test_organism_filter(self, mock_get_catalog, mock_for_formats):
        other = {**_PUBLISHED_STUDY, "study_id": "mouse_study", "organisms": ["Mus musculus"]}
        mock_get_catalog.return_value = {"studies": [_PUBLISHED_STUDY, other]}
        result = search_studies(organism="Mus musculus")
        assert [s["study_id"] for s in result.structured_content["studies"]] == ["mouse_study"]

    @patch('search_studies.rl.for_formats', return_value=[])
    @patch('search_studies.get_catalog')
    def test_query_matches_summary(self, mock_get_catalog, mock_for_formats):
        mock_get_catalog.return_value = {"studies": [_PUBLISHED_STUDY]}
        result = search_studies(query="summary")
        assert len(result.structured_content["studies"]) == 1
        result_none = search_studies(query="nonexistent phrase xyz")
        assert len(result_none.structured_content["studies"]) == 0

    @patch('search_studies.rl.for_formats', return_value=[])
    @patch('search_studies.get_catalog')
    def test_access_restricted_field_passed_through(self, mock_get_catalog, mock_for_formats):
        restricted = {**_PUBLISHED_STUDY, "study_id": "restricted", "access_restricted": True}
        mock_get_catalog.return_value = {"studies": [restricted]}
        result = search_studies()
        assert result.structured_content["studies"][0]["access_restricted"] is True

    @patch('search_studies.rl.for_formats', return_value=[_LINK])
    @patch('search_studies.get_catalog')
    def test_resource_link_attached_for_seen_formats(self, mock_get_catalog, mock_for_formats):
        mock_get_catalog.return_value = {"studies": [_PUBLISHED_STUDY]}
        result = search_studies()
        mock_for_formats.assert_called_once_with({"h5ad"})
        assert _LINK in result.content
