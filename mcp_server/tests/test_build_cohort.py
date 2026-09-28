"""Tests for build_cohort.py"""
from unittest.mock import patch

from build_cohort import build_cohort

_SAMPLES = [
    {
        "study_id": "study1", "sample_id": "GSM1",
        "disease_status_canonical": "ALS", "sex": "female",
        "tissue": "Spinal Cord (Cervical)", "treatment": None,
        "platform": "GPL1", "genotype_canonical": "C9orf72 repeat expansion (positive)",
    },
    {
        "study_id": "study1", "sample_id": "GSM2",
        "disease_status_canonical": "Control", "sex": "male",
        "tissue": "Spinal Cord (Cervical)", "treatment": None,
        "platform": "GPL1", "genotype_canonical": None,
    },
    {
        "study_id": "study2", "sample_id": "GSM3",
        "disease_status_canonical": "ALS", "sex": "female",
        "tissue": "Motor Cortex", "treatment": None,
        "platform": "GPL2", "genotype_canonical": "TARDBP_M337V",
    },
    {
        "study_id": "NoDataYet", "sample_id": "GSM4",
        "disease_status_canonical": "ALS", "sex": "female",
        "tissue": "Spinal Cord (Cervical)", "treatment": None,
        "platform": "GPL1", "genotype_canonical": None,
    },
]

_CATALOG = {
    "source_root": "/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS",
    "studies": [
        {
            "study_id": "study1",
            "processed_files": [
                {"name": "study1.h5ad", "bytes": 100, "category": "data"},
                {"name": "conversion_log.md", "bytes": 10, "category": "doc"},
            ],
        },
        {
            "study_id": "study2",
            "processed_files": [
                {"name": "study2_counts.parquet", "bytes": 50, "category": "data"},
            ],
        },
        {"study_id": "NoDataYet", "processed_files": []},
    ],
}


def _patched(fn):
    fn = patch('build_cohort.get_samples', return_value=_SAMPLES)(fn)
    fn = patch('build_cohort.get_catalog', return_value=_CATALOG)(fn)
    return fn


class TestBuildCohort:

    @_patched
    def test_matches_on_canonical_disease_status(self, mock_catalog, mock_samples):
        result = build_cohort(disease_status="ALS")
        assert result.structured_content["total_matched_samples"] == 3

    @_patched
    def test_combining_filters_is_and(self, mock_catalog, mock_samples):
        result = build_cohort(disease_status="ALS", sex="female")
        assert result.structured_content["total_matched_samples"] == 3
        result2 = build_cohort(disease_status="ALS", sex="male")
        assert result2.structured_content["total_matched_samples"] == 0

    @_patched
    def test_genotype_filter(self, mock_catalog, mock_samples):
        result = build_cohort(genotype="TARDBP_M337V")
        assert result.structured_content["total_matched_samples"] == 1
        cohort = result.structured_content["cohort"]
        assert cohort[0]["study_id"] == "study2"
        assert cohort[0]["sample_ids"] == ["GSM3"]

    @_patched
    def test_study_id_restricts_search(self, mock_catalog, mock_samples):
        result = build_cohort(disease_status="ALS", study_id="study1")
        assert result.structured_content["total_matched_samples"] == 1

    @_patched
    def test_real_htcf_directory_resolved_per_study(self, mock_catalog, mock_samples):
        result = build_cohort(disease_status="ALS", study_id="study1")
        cohort = result.structured_content["cohort"]
        assert cohort[0]["directory"] == (
            "/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS/studies/study1/processed/"
        )

    @_patched
    def test_only_data_category_files_listed(self, mock_catalog, mock_samples):
        result = build_cohort(disease_status="ALS", study_id="study1")
        files = result.structured_content["cohort"][0]["files"]
        names = {f["filename"] for f in files}
        assert names == {"study1.h5ad"}
        assert "conversion_log.md" not in names

    @_patched
    def test_study_with_no_processed_files_goes_to_excluded(self, mock_catalog, mock_samples):
        result = build_cohort(disease_status="ALS", study_id="NoDataYet")
        assert result.structured_content["cohort"] == []
        assert result.structured_content["excluded_studies"] == [
            {"study_id": "NoDataYet", "status": "no_processed_data", "sample_count": 1}
        ]

    @_patched
    def test_no_filters_matches_everything(self, mock_catalog, mock_samples):
        result = build_cohort()
        assert result.structured_content["total_matched_samples"] == len(_SAMPLES)

    @_patched
    def test_no_url_or_download_field_anywhere(self, mock_catalog, mock_samples):
        """Same core property as get_data_locations: never a URL, only a
        real filesystem path."""
        result = build_cohort(disease_status="ALS")
        text = result.content[0].text
        assert "http://" not in text
        assert "https://" not in text

    @_patched
    def test_cohort_sorted_by_study_id(self, mock_catalog, mock_samples):
        result = build_cohort(disease_status="ALS")
        study_ids = [c["study_id"] for c in result.structured_content["cohort"]]
        assert study_ids == sorted(study_ids)

    @_patched
    def test_resource_links_attached_for_present_formats(self, mock_catalog, mock_samples):
        result = build_cohort(disease_status="ALS")
        uris = {c.uri for c in result.content[1:]}
        assert "pipeline-docs://h5ad_schema" in uris
        assert "pipeline-docs://bulk_rnaseq_schema" in uris
