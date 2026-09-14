import pytest
from unittest.mock import patch

import explain_data_file as module_under_test


@pytest.fixture
def mock_get_study():
    with patch('explain_data_file.get_study') as mock:
        yield mock


@pytest.fixture
def mock_format_label():
    with patch('explain_data_file.format_label') as mock:
        yield mock


@pytest.fixture
def mock_rl():
    with patch('explain_data_file.rl') as mock:
        yield mock


class TestExplainDataFile:

    def test_study_not_found(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = None
        
        result = module_under_test.explain_data_file("nonexistent", "file.h5ad")
        
        assert result.structured_content["status"] == "not_found"
        assert result.structured_content["reason"] == "no such study_id"

    def test_file_not_found_in_study(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "other.h5ad", "category": "data"}]
        }
        
        result = module_under_test.explain_data_file("study1", "missing.h5ad")
        
        assert result.structured_content["status"] == "not_found"
        assert result.structured_content["reason"] == "no such file in this study"

    def test_file_with_wrong_category_not_found(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "metadata.json", "category": "metadata"}]
        }
        
        result = module_under_test.explain_data_file("study1", "metadata.json")
        
        assert result.structured_content["status"] == "not_found"

    def test_successful_explanation_with_all_fields(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": "# data\nConverted from file.bam",
            "qc_report": [{"path": "data.h5ad", "status": "pass", "cells": 1000}]
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")
        
        assert result.structured_content["status"] == "ok"
        assert result.structured_content["study_id"] == "study1"
        assert result.structured_content["filename"] == "data.h5ad"
        assert result.structured_content["format"] == "h5ad"
        assert result.structured_content["qc"]["status"] == "pass"
        assert result.structured_content["conversion_note"] is not None

    def test_successful_explanation_no_qc_report(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": "# data\nConverted"
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")
        
        assert result.structured_content["status"] == "ok"
        assert result.structured_content["qc"] is None

    def test_successful_explanation_empty_qc_report(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": None,
            "qc_report": []
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")
        
        assert result.structured_content["qc"] is None

    def test_qc_report_matching_by_filename_in_path(self, mock_get_study, mock_format_label, mock_rl):
        qc_entry = {"path": "data.h5ad", "cells": 1000}
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": None,
            "qc_report": [qc_entry]
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")
        
        assert result.structured_content["qc"] == qc_entry

    def test_qc_report_no_match_returns_none(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": None,
            "qc_report": [{"path": "other.h5ad", "cells": 500}]
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")

        assert result.structured_content["qc"] is None

    def test_qc_report_full_path_matches_by_basename(self, mock_get_study, mock_format_label, mock_rl):
        """A QC entry's path can be a full path, not just a bare filename --
        matching must compare basenames, not just membership."""
        qc_entry = {"path": "studies/study1/processed/data.h5ad", "cells": 1000}
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": None,
            "qc_report": [qc_entry]
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []

        result = module_under_test.explain_data_file("study1", "data.h5ad")

        assert result.structured_content["qc"] == qc_entry

    def test_qc_report_substring_collision_does_not_false_match(self, mock_get_study, mock_format_label, mock_rl):
        """A QC entry whose path merely CONTAINS the target filename as a
        substring (e.g. a differently-named file that happens to embed it)
        must not be treated as a match -- only an exact basename match
        counts."""
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": None,
            "qc_report": [{"path": "other_data.h5ad.bak", "cells": 500}]
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []

        result = module_under_test.explain_data_file("study1", "data.h5ad")

        assert result.structured_content["qc"] is None

    def test_multiple_processed_files_filters_by_category(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [
                {"name": "file1.h5ad", "category": "data"},
                {"name": "file2.h5ad", "category": "data"},
                {"name": "meta.json", "category": "metadata"}
            ],
            "conversion_log_raw": None
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        result = module_under_test.explain_data_file("study1", "file2.h5ad")
        
        assert result.structured_content["status"] == "ok"
        assert result.structured_content["filename"] == "file2.h5ad"

    def test_format_label_called_with_filename(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": None
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        module_under_test.explain_data_file("study1", "data.h5ad")
        
        mock_format_label.assert_called_once_with("data.h5ad")

    def test_resource_links_called_with_format_set(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": None
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        module_under_test.explain_data_file("study1", "data.h5ad")
        
        mock_rl.for_formats.assert_called_once_with({"h5ad"})

    def test_missing_processed_files_key_treated_as_empty(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {}
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")
        
        assert result.structured_content["status"] == "not_found"

    def test_processed_file_missing_category_filtered_out(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad"}]
        }
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")
        
        assert result.structured_content["status"] == "not_found"

    def test_processed_files_empty_list(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {"processed_files": []}
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")
        
        assert result.structured_content["status"] == "not_found"

    def test_conversion_log_none_extraction(self, mock_get_study, mock_format_label, mock_rl):
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": None
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")
        
        assert result.structured_content["conversion_note"] is None

    def test_qc_report_with_multiple_entries_finds_match(self, mock_get_study, mock_format_label, mock_rl):
        qc_entries = [
            {"path": "other.h5ad", "cells": 500},
            {"path": "data.h5ad", "cells": 1000},
            {"path": "another.h5ad", "cells": 750}
        ]
        mock_get_study.return_value = {
            "processed_files": [{"name": "data.h5ad", "category": "data"}],
            "conversion_log_raw": None,
            "qc_report": qc_entries
        }
        mock_format_label.return_value = "h5ad"
        mock_rl.for_formats.return_value = []
        
        result = module_under_test.explain_data_file("study1", "data.h5ad")
        
        assert result.structured_content["qc"]["cells"] == 1000


class TestExtractFileSection:

    def test_none_conversion_log_returns_none(self):
        result = module_under_test._extract_file_section(None, "file.h5ad")
        assert result is None

    def test_empty_string_conversion_log_returns_none(self):
        """An empty conversion log is treated the same as "no conversion
        log at all" (None) -- both mean "nothing to show," consistent with
        the missing-file case."""
        result = module_under_test._extract_file_section("", "file.h5ad")
        assert result is None

    def test_single_match_in_header_exact_filename(self):
        log = "# data.h5ad\nContent here.\n# other\nOther content."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "Content here" in result
        assert "Other content" not in result

    def test_single_match_in_header_stem_only(self):
        log = "# data\nData section.\n# other\nOther section."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "Data section" in result
        assert "Other section" not in result

    def test_single_match_in_body_text(self):
        log = "# section1\nThis mentions data.h5ad.\n# section2\nOther text."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "mentions data.h5ad" in result
        assert "section2" not in result

    def test_multiple_matches_returns_whole_log(self):
        log = "# data\nFirst section.\n# data_v2\nSecond section."
        result = module_under_test._extract_file_section(log, "data")
        assert result == log

    def test_no_matches_returns_whole_log(self):
        log = "# section1\nContent A.\n# section2\nContent B."
        result = module_under_test._extract_file_section(log, "nonexistent.h5ad")
        assert result == log

    def test_stem_extraction_with_known_compound_extension(self):
        """.tsv.gz/.csv.gz/.mtx.gz are real compound extensions in this
        collection -- the stem must strip the whole thing, not just the
        last "." segment (which would wrongly leave "counts.tsv")."""
        log = "# study_counts\nExtracted section.\n# other\nOther."
        result = module_under_test._extract_file_section(log, "study_counts.tsv.gz")
        assert "Extracted section" in result
        assert "Other" not in result

    def test_stem_extraction_with_unrecognized_compound_extension(self):
        """An extension this collection doesn't use (e.g. .tar.gz) isn't
        specially stripped -- only the last "." segment is, so this
        legitimately falls back to the whole-log answer rather than
        guessing a stem that might be wrong."""
        log = "# myfile\nExtracted section.\n# other\nOther."
        result = module_under_test._extract_file_section(log, "myfile.tar.gz")
        assert result == log

    def test_h2_header_matching(self):
        log = "# Main\n## data\nSubsection.\n## other\nOther sub."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "Subsection" in result

    def test_extracted_section_is_stripped(self):
        log = "# data\n  Content.  \n# other\nOther."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert result == result.strip()
        assert not result.startswith(" ")
        assert not result.endswith(" ")

    def test_multiline_section_preserved(self):
        log = "# data\nLine 1\nLine 2\nLine 3\n# other\nOther."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "Line 1" in result
        assert "Line 2" in result
        assert "Line 3" in result
        assert "Other" not in result

    def test_case_sensitive_matching(self):
        log = "# Data\nCapital section.\n# data\nLower section."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "Lower section" in result
        assert "Capital section" not in result

    def test_special_characters_in_filename_stem(self):
        log = "# data_v1.2\nVersion match.\n# data_v1.1\nOlder."
        result = module_under_test._extract_file_section(log, "data_v1.2.h5ad")
        assert "Version match" in result
        assert "Older" not in result

    def test_filename_substring_doesnt_match_partial(self):
        log = "# MyDataFile\nContent.\n# other\nOther."
        result = module_under_test._extract_file_section(log, "datafile.h5ad")
        assert result == log

    def test_section_boundary_correct(self):
        log = "# data\nFirst\nSecond\n# another\nThird."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "Third" not in result
        assert "First" in result
        assert "Second" in result

    def test_whitespace_in_section_preserved(self):
        log = "# data\nLine1\n  Indented\nLine3\n# other\nOther."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "Indented" in result
        assert "Line3" in result

    def test_filename_appears_multiple_times_single_section(self):
        log = "# data\nMentions data.h5ad here.\nAnd data.h5ad again.\n# other\nOther."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "Mentions" in result
        assert "again" in result
        assert "Other" not in result

    def test_both_stem_and_filename_in_different_sections_returns_whole(self):
        log = "# data\nFirst.\n# data.h5ad\nSecond."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert result == log

    def test_empty_section_matched(self):
        log = "# data\n\n# other\nOther content."
        result = module_under_test._extract_file_section(log, "data.h5ad")
        assert "Other content" not in result

    def test_conversion_log_single_section_no_headers(self):
        log = "Some content here"
        result = module_under_test._extract_file_section(log, "file.h5ad")
        assert result == log