import pytest
from unittest.mock import Mock, MagicMock, patch, mock_open, call
from pathlib import Path
from io import StringIO
import json

from sources import (
    classify_file,
    load_studies_tsv,
    load_all_samples,
    load_build_summary,
    skipped_study_ids,
    load_status_json,
    get_study_phase,
    load_readme_abstract,
    load_readme_summary,
    list_processed_files,
    list_study_ids,
    load_readme_header,
    split_multi,
    samples_by_study,
    normalize_organism,
    dedupe_joined,
    build_case_insensitive_canon,
)


class TestClassifyFile:
    def test_data_extensions(self):
        assert classify_file("file.h5ad") == "data"
        assert classify_file("file.parquet") == "data"
        assert classify_file("file.tsv") == "data"
        assert classify_file("file.csv") == "data"
        assert classify_file("file.tsv.gz") == "data"
        assert classify_file("file.csv.gz") == "data"
        assert classify_file("file.loom") == "data"
        assert classify_file("file.mtx") == "data"
        assert classify_file("file.mtx.gz") == "data"
        assert classify_file("file.h5mu") == "data"
        assert classify_file("file.h5") == "data"

    def test_doc_extensions(self):
        assert classify_file("README.md") == "doc"
        assert classify_file("file.md") == "doc"

    def test_metadata_extensions(self):
        assert classify_file("metadata.json") == "metadata"
        assert classify_file("config.json") == "metadata"

    def test_other_extensions(self):
        assert classify_file("file.txt") == "other"
        assert classify_file("file.bam") == "other"
        assert classify_file("file") == "other"

    def test_case_insensitive(self):
        assert classify_file("FILE.H5AD") == "data"
        assert classify_file("file.H5AD") == "data"
        assert classify_file("README.MD") == "doc"
        assert classify_file("METADATA.JSON") == "metadata"

    def test_multiple_extensions(self):
        assert classify_file("archive.tsv.gz") == "data"
        assert classify_file("data.csv.gz") == "data"


class TestLoadStudiesTsv:
    def test_load_studies_tsv_basic(self):
        with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
            mock_f.return_value.__enter__.return_value = StringIO(
                "study_id\tname\nstud1\tName One\nstud2\tName Two\n"
            )
            result = load_studies_tsv(Path("/fake/root"))
        assert "stud1" in result
        assert "stud2" in result

    def test_load_studies_tsv_empty(self):
        with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
            mock_f.return_value.__enter__.return_value = StringIO("study_id\tname\n")
            result = load_studies_tsv(Path("/fake/root"))
        assert result == {}

    def test_load_studies_tsv_skip_empty_study_id(self):
        tsv_content = "study_id\tname\n\tEmpty ID\nstud1\tName One\n   \tWhitespace\n"
        with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
            mock_f.return_value.__enter__.return_value = StringIO(tsv_content)
            result = load_studies_tsv(Path("/fake/root"))
        assert len(result) == 1
        assert "stud1" in result

    def test_load_studies_tsv_whitespace_stripping(self):
        tsv_content = "study_id\tname\n  stud1  \tName\n"
        with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
            mock_f.return_value.__enter__.return_value = StringIO(tsv_content)
            result = load_studies_tsv(Path("/fake/root"))
        assert "stud1" in result


class TestLoadAllSamples:
    def test_load_all_samples_basic(self):
        tsv_content = "sample_id\tstudy_id\nS1\nstud1\nS2\nstud1\n"
        with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
            mock_f.return_value.__enter__.return_value = StringIO(
                "sample_id\tstudy_id\nS1\nstud1\nS2\nstud1\n"
            )
            result = load_all_samples(Path("/fake/root"))
        assert isinstance(result, list)

    def test_load_all_samples_empty(self):
        with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
            mock_f.return_value.__enter__.return_value = StringIO("sample_id\n")
            result = load_all_samples(Path("/fake/root"))
        assert result == []

    def test_load_all_samples_preserves_fields(self):
        tsv_content = "sample_id\tage\nsamp1\t50\n"
        with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
            mock_f.return_value.__enter__.return_value = StringIO(tsv_content)
            result = load_all_samples(Path("/fake/root"))
        assert len(result) == 1
        assert result[0]["sample_id"] == "samp1"


class TestLoadBuildSummary:
    def test_load_build_summary_exists(self):
        json_data = [
            {"study_id": "study1", "n_samples": 10},
            {"study_id": "study2", "n_samples": 20},
        ]
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
                mock_f.return_value.__enter__.return_value = StringIO(
                    json.dumps(json_data)
                )
                result = load_build_summary(Path("/fake/root"))
        assert len(result) == 2
        assert result[0]["study_id"] == "study1"

    def test_load_build_summary_not_exists(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = load_build_summary(Path("/fake/root"))
        assert result == []

    def test_load_build_summary_empty_json(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
                mock_f.return_value.__enter__.return_value = StringIO("[]")
                result = load_build_summary(Path("/fake/root"))
        assert result == []


class TestSkippedStudyIds:
    # Real-world regression: a study can have study_dir=None WITHOUT being
    # deliberately excluded (e.g. SRP566214_dataset's build_summary.json
    # entry has study_dir=None but status "COMPLETE..." -- just an
    # unpopulated field, not a skip). The signal is the status text, not
    # study_dir.
    def test_skipped_study_ids_basic(self):
        build_summary = [
            {"study_id": "study1", "study_dir": "/path/to/study1", "status": "COMPLETE"},
            {"study_id": "study2", "study_dir": None, "status": "SKIPPED - dbGaP controlled-access"},
            {"study_id": "study3", "study_dir": "/path/to/study3", "status": "COMPLETE"},
        ]
        result = skipped_study_ids(build_summary)
        assert result == {"study2"}

    def test_skipped_study_ids_null_study_dir_but_not_skipped_status(self):
        build_summary = [
            {"study_id": "study1", "study_dir": None, "status": "COMPLETE - 8/8 FASTQ runs downloaded"},
        ]
        result = skipped_study_ids(build_summary)
        assert result == set()

    def test_skipped_study_ids_multiple_skipped(self):
        build_summary = [
            {"study_id": "s1", "study_dir": None, "status": "SKIPPED - reason one"},
            {"study_id": "s2", "study_dir": None, "status": "skipped - lowercase still counts"},
            {"study_id": "s3", "study_dir": "/path/s3", "status": "COMPLETE"},
        ]
        result = skipped_study_ids(build_summary)
        assert result == {"s1", "s2"}

    def test_skipped_study_ids_no_skipped(self):
        build_summary = [
            {"study_id": "study1", "study_dir": "/path", "status": "COMPLETE"},
            {"study_id": "study2", "study_dir": "/path", "status": "COMPLETE"},
        ]
        result = skipped_study_ids(build_summary)
        assert result == set()

    def test_skipped_study_ids_missing_study_id(self):
        build_summary = [
            {"study_dir": None, "status": "SKIPPED - no id"},
            {"study_id": "study1", "study_dir": None, "status": "SKIPPED - has id"},
        ]
        result = skipped_study_ids(build_summary)
        assert result == {"study1"}

    def test_skipped_study_ids_empty_list(self):
        result = skipped_study_ids([])
        assert result == set()

    def test_skipped_study_ids_none_study_id_string(self):
        build_summary = [
            {"study_id": None, "study_dir": None, "status": "SKIPPED - no id"},
            {"study_id": "study1", "study_dir": None, "status": "SKIPPED - has id"},
        ]
        result = skipped_study_ids(build_summary)
        assert result == {"study1"}

    def test_skipped_study_ids_missing_status_field(self):
        build_summary = [{"study_id": "study1", "study_dir": None}]
        result = skipped_study_ids(build_summary)
        assert result == set()


class TestLoadStatusJson:
    def test_load_status_json_exists(self):
        json_data = {"studies": {"study1": {"phase": "complete"}}}
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
                mock_f.return_value.__enter__.return_value = StringIO(
                    json.dumps(json_data)
                )
                result = load_status_json(Path("/fake/root"), "status.json")
        assert "studies" in result
        assert result["studies"]["study1"]["phase"] == "complete"

    def test_load_status_json_not_exists(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = load_status_json(Path("/fake/root"), "status.json")
        assert result == {}

    def test_load_status_json_empty(self):
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.open", new_callable=mock_open) as mock_f:
                mock_f.return_value.__enter__.return_value = StringIO("{}")
                result = load_status_json(Path("/fake/root"), "status.json")
        assert result == {}


class TestGetStudyPhase:
    def test_get_study_phase_found_with_phase_and_note(self):
        status_doc = {
            "studies": {"study1": {"phase": "processing", "note": "In progress"}}
        }
        phase, note = get_study_phase(status_doc, "study1")
        assert phase == "processing"
        assert note == "In progress"

    def test_get_study_phase_found_phase_only(self):
        status_doc = {"studies": {"study1": {"phase": "complete"}}}
        phase, note = get_study_phase(status_doc, "study1")
        assert phase == "complete"
        assert note is None

    def test_get_study_phase_found_note_only(self):
        status_doc = {"studies": {"study1": {"note": "Delayed"}}}
        phase, note = get_study_phase(status_doc, "study1")
        assert phase is None
        assert note == "Delayed"

    def test_get_study_phase_default_for_unlisted(self):
        status_doc = {"studies": {"_default_for_unlisted": "Not started"}}
        phase, note = get_study_phase(status_doc, "unknown")
        assert phase is None
        assert note == "Not started"

    def test_get_study_phase_not_found_no_default(self):
        status_doc = {"studies": {"study1": {"phase": "complete"}}}
        phase, note = get_study_phase(status_doc, "unknown")
        assert phase is None
        assert note is None

    def test_get_study_phase_empty_status_doc(self):
        phase, note = get_study_phase({}, "study1")
        assert phase is None
        assert note is None

    def test_get_study_phase_entry_not_dict_uses_default(self):
        status_doc = {
            "studies": {
                "study1": "string",
                "_default_for_unlisted": "Default",
            }
        }
        phase, note = get_study_phase(status_doc, "study1")
        assert phase is None
        assert note == "Default"

    def test_get_study_phase_default_not_string(self):
        status_doc = {"studies": {"_default_for_unlisted": {"phase": "none"}}}
        phase, note = get_study_phase(status_doc, "unknown")
        assert phase is None
        assert note is None


class TestLoadReadmeAbstract:
    def test_load_readme_abstract_found(self):
        content = (
            "# Title\n"
            "## Abstract\n"
            "Abstract text here.\n"
            "Multiple lines.\n"
            "## Methods\n"
            "Methods content\n"
        )
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                result = load_readme_abstract(Path("/fake/root"), "study1")
        assert "Abstract text here." in result
        assert "Multiple lines." in result
        assert "Methods" not in result

    def test_load_readme_abstract_at_end_of_file(self):
        content = "## Abstract\nAbstract content"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                result = load_readme_abstract(Path("/fake/root"), "study1")
        assert result == "Abstract content"

    def test_load_readme_abstract_not_found(self):
        content = "# Title\n## Methods\nMethods content\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                result = load_readme_abstract(Path("/fake/root"), "study1")
        assert result is None

    def test_load_readme_abstract_file_not_exists(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = load_readme_abstract(Path("/fake/root"), "study1")
        assert result is None

    def test_load_readme_abstract_case_sensitive(self):
        content = "## abstract\nLowercase abstract\n## Methods\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                result = load_readme_abstract(Path("/fake/root"), "study1")
        assert result is None

    def test_load_readme_abstract_whitespace_handling(self):
        content = "##  Abstract  \nContent\n## Next\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                result = load_readme_abstract(Path("/fake/root"), "study1")
        assert result == "Content"

    def test_load_readme_abstract_strips_result(self):
        content = "## Abstract\n   Indented content   \n## Methods\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                result = load_readme_abstract(Path("/fake/root"), "study1")
        assert result == "Indented content"


class TestLoadReadmeSummary:
    def test_found_between_accessions_and_abstract(self):
        # Real README shape (2026-09-06): Summary comes before Abstract.
        content = (
            "# Title\n"
            "**Assay types:** bulk RNA-seq\n"
            "## Summary\n"
            "A short plain-language summary.\n"
            "## Abstract\n"
            "The full academic abstract.\n"
        )
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                result = load_readme_summary(Path("/fake/root"), "study1")
        assert result == "A short plain-language summary."

    def test_not_found_returns_none(self):
        content = "# Title\n## Abstract\nOnly an abstract, no summary section.\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                result = load_readme_summary(Path("/fake/root"), "study1")
        assert result is None

    def test_file_not_exists(self):
        with patch("pathlib.Path.exists", return_value=False):
            result = load_readme_summary(Path("/fake/root"), "study1")
        assert result is None

    def test_does_not_match_abstract_section(self):
        # Regression guard: summary and abstract extraction must not
        # cross-contaminate (they share the same underlying helper).
        content = "## Abstract\nAbstract only.\n"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_text", return_value=content):
                assert load_readme_summary(Path("/fake/root"), "study1") is None
                assert load_readme_abstract(Path("/fake/root"), "study1") == "Abstract only."


class TestListProcessedFiles:
    def test_list_processed_files_not_directory(self):
        with patch("pathlib.Path.is_dir", return_value=False):
            result = list_processed_files(Path("/fake/root"), "study1")
        assert result == []

    def test_list_processed_files_empty_directory(self):
        with patch("pathlib.Path.is_dir", return_value=True):
            with patch("pathlib.Path.iterdir", return_value=[]):
                result = list_processed_files(Path("/fake/root"), "study1")
        assert result == []

    def test_list_processed_files_with_data_files(self):
        mock_file = MagicMock()
        mock_file.name = "data.h5ad"
        mock_file.is_file.return_value = True
        mock_file.stat.return_value.st_size = 1024
        
        with patch("pathlib.Path.is_dir", return_value=True):
            with patch("pathlib.Path.iterdir", return_value=[mock_file]):
                result = list_processed_files(Path("/fake/root"), "study1")
        
        assert len(result) == 1
        assert result[0]["name"] == "data.h5ad"
        assert result[0]["bytes"] == 1024
        assert result[0]["category"] == "data"

    def test_list_processed_files_multiple_categories(self):
        data_file = MagicMock()
        data_file.name = "data.csv"
        data_file.is_file.return_value = True
        data_file.stat.return_value.st_size = 2048
        
        doc_file = MagicMock()
        doc_file.name = "README.md"
        doc_file.is_file.return_value = True
        doc_file.stat.return_value.st_size = 512
        
        with patch("pathlib.Path.is_dir", return_value=True):
            with patch("pathlib.Path.iterdir", return_value=[data_file, doc_file]):
                result = list_processed_files(Path("/fake/root"), "study1")
        
        assert len(result) == 2
        categories = {r["name"]: r["category"] for r in result}
        assert categories["data.csv"] == "data"
        assert categories["README.md"] == "doc"

    def test_list_processed_files_skip_directories(self):
        data_file = MagicMock()
        data_file.name = "data.h5ad"
        data_file.is_file.return_value = True
        data_file.stat.return_value.st_size = 1024
        
        dir_entry = MagicMock()
        dir_entry.name = "subdir"
        dir_entry.is_file.return_value = False
        
        with patch("pathlib.Path.is_dir", return_value=True):
            with patch("pathlib.Path.iterdir", return_value=[data_file, dir_entry]):
                result = list_processed_files(Path("/fake/root"), "study1")
        
        assert len(result) == 1
        assert result[0]["name"] == "data.h5ad"

    def test_list_processed_files_sorted_by_name(self):
        file_b = MagicMock()
        file_b.name = "zebra.h5ad"
        file_b.is_file.return_value = True
        file_b.stat.return_value.st_size = 100
        
        file_a = MagicMock()
        file_a.name = "alpha.csv"
        file_a.is_file.return_value = True
        file_a.stat.return_value.st_size = 200
        
        with patch("pathlib.Path.is_dir", return_value=True):
            with patch("pathlib.Path.iterdir", return_value=[file_b, file_a]):
                result = list_processed_files(Path("/fake/root"), "study1")
        
        assert result[0]["name"] == "alpha.csv"
        assert result[1]["name"] == "zebra.h5ad"

    def test_list_processed_files_zero_byte_file(self):
        empty_file = MagicMock()
        empty_file.name = "empty.txt"
        empty_file.is_file.return_value = True
        empty_file.stat.return_value.st_size = 0
        
        with patch("pathlib.Path.is_dir", return_value=True):
            with patch("pathlib.Path.iterdir", return_value=[empty_file]):
                result = list_processed_files(Path("/fake/root"), "study1")
        
        assert len(result) == 1
        assert result[0]["bytes"] == 0


class TestSplitMulti:
    def test_split_multi_none(self):
        assert split_multi(None) == []

    def test_split_multi_empty_string(self):
        assert split_multi("") == []

    def test_split_multi_whitespace_only(self):
        assert split_multi("   ") == []

    def test_split_multi_none_uppercase(self):
        assert split_multi("NONE") == []

    def test_split_multi_none_lowercase(self):
        assert split_multi("none") == []

    def test_split_multi_none_mixed_case(self):
        assert split_multi("NoNe") == []

    def test_split_multi_none_with_explanation(self):
        """Real bug, external server review 2026-09-19: Pineda2024_Cell's
        studies.tsv `gse` cell is "NONE (SRA-only deposit, no GEO series)" --
        an exact "NONE" match doesn't catch this, and the whole sentence
        used to land in the study's gse list as a fake accession."""
        assert split_multi("NONE (SRA-only deposit, no GEO series)") == []

    def test_split_multi_semicolon_delimited(self):
        result = split_multi("study1;study2;study3")
        assert result == ["study1", "study2", "study3"]

    def test_split_multi_comma_delimited(self):
        result = split_multi("study1,study2,study3")
        assert result == ["study1", "study2", "study3"]

    def test_split_multi_mixed_delimiters(self):
        result = split_multi("study1;study2,study3")
        assert result == ["study1", "study2", "study3"]

    def test_split_multi_with_whitespace(self):
        result = split_multi("  study1  ;  study2  ,  study3  ")
        assert result == ["study1", "study2", "study3"]

    def test_split_multi_consecutive_delimiters(self):
        result = split_multi("study1;;study2")
        assert result == ["study1", "study2"]

    def test_split_multi_trailing_delimiters(self):
        result = split_multi("study1;study2;")
        assert result == ["study1", "study2"]

    def test_split_multi_leading_delimiters(self):
        result = split_multi(";study1;study2")
        assert result == ["study1", "study2"]

    def test_split_multi_single_value(self):
        result = split_multi("study1")
        assert result == ["study1"]

    def test_split_multi_single_value_with_spaces(self):
        result = split_multi("  study1  ")
        assert result == ["study1"]


class TestSamplesByStudy:
    def test_samples_by_study_basic(self):
        samples = [
            {"sample_id": "s1", "study_id": "study1"},
            {"sample_id": "s2", "study_id": "study1"},
            {"sample_id": "s3", "study_id": "study2"},
        ]
        result = samples_by_study(samples)
        
        assert len(result) == 2
        assert len(result["study1"]) == 2
        assert len(result["study2"]) == 1

    def test_samples_by_study_empty_list(self):
        result = samples_by_study([])
        assert result == {}

    def test_samples_by_study_missing_study_id(self):
        samples = [
            {"sample_id": "s1"},
            {"sample_id": "s2", "study_id": "study1"},
        ]
        result = samples_by_study(samples)
        
        assert len(result) == 1
        assert "study1" in result
        assert len(result["study1"]) == 1

    def test_samples_by_study_empty_study_id(self):
        samples = [
            {"sample_id": "s1", "study_id": ""},
            {"sample_id": "s2", "study_id": "study1"},
        ]
        result = samples_by_study(samples)
        
        assert len(result) == 1
        assert "study1" in result

    def test_samples_by_study_none_study_id(self):
        samples = [
            {"sample_id": "s1", "study_id": None},
            {"sample_id": "s2", "study_id": "study1"},
        ]
        result = samples_by_study(samples)
        
        assert len(result) == 1
        assert "study1" in result

    def test_samples_by_study_preserves_all_fields(self):
        samples = [
            {"sample_id": "s1", "study_id": "study1", "age": 50, "sex": "F"},
            {"sample_id": "s2", "study_id": "study1", "age": 60, "sex": "M"},
        ]
        result = samples_by_study(samples)
        
        assert result["study1"][0]["age"] == 50
        assert result["study1"][1]["age"] == 60
        assert result["study1"][0]["sex"] == "F"
        assert result["study1"][1]["sex"] == "M"

    def test_samples_by_study_maintains_order(self):
        samples = [
            {"sample_id": "s1", "study_id": "study1"},
            {"sample_id": "s2", "study_id": "study1"},
            {"sample_id": "s3", "study_id": "study1"},
        ]
        result = samples_by_study(samples)
        
        assert result["study1"][0]["sample_id"] == "s1"
        assert result["study1"][1]["sample_id"] == "s2"
        assert result["study1"][2]["sample_id"] == "s3"

    def test_samples_by_study_multiple_studies(self):
        samples = [
            {"sample_id": "s1", "study_id": "A"},
            {"sample_id": "s2", "study_id": "B"},
            {"sample_id": "s3", "study_id": "A"},
            {"sample_id": "s4", "study_id": "C"},
            {"sample_id": "s5", "study_id": "B"},
        ]
        result = samples_by_study(samples)

        assert len(result) == 3
        assert len(result["A"]) == 2
        assert len(result["B"]) == 2
        assert len(result["C"]) == 1


class TestListStudyIds:
    def test_no_studies_dir(self, tmp_path):
        assert list_study_ids(tmp_path) == []

    def test_lists_directories_only(self, tmp_path):
        studies = tmp_path / "studies"
        studies.mkdir()
        (studies / "StudyB").mkdir()
        (studies / "StudyA").mkdir()
        (studies / "not_a_study.txt").write_text("x")

        assert list_study_ids(tmp_path) == ["StudyA", "StudyB"]

    def test_empty_studies_dir(self, tmp_path):
        (tmp_path / "studies").mkdir()
        assert list_study_ids(tmp_path) == []


class TestLoadReadmeHeader:
    README_TEMPLATE = (
        "# {title}\n\n"
        "**Journal:** {journal} ({year})\n"
        "**Study ID:** {study_id}\n"
        "**Accessions:** {accessions}\n"
        "**Assay types:** {assay_types}\n"
        "**Primary data route:** {route}\n"
    )

    def _write_readme(self, tmp_path, study_id, **kwargs):
        study_dir = tmp_path / "studies" / study_id
        study_dir.mkdir(parents=True)
        defaults = dict(
            title="A Test Study",
            journal="Nature neuroscience",
            year="2019",
            study_id=study_id,
            accessions='{"gse": ["GSE121569"]}',
            assay_types="bulk RNA-seq",
            route="GEO",
        )
        defaults.update(kwargs)
        (study_dir / "README.md").write_text(self.README_TEMPLATE.format(**defaults))

    def test_missing_file_returns_none(self, tmp_path):
        assert load_readme_header(tmp_path, "NoSuchStudy") is None

    def test_parses_all_fields(self, tmp_path):
        self._write_readme(tmp_path, "Klim2019_GSE121569")

        row = load_readme_header(tmp_path, "Klim2019_GSE121569")

        assert row["study_id"] == "Klim2019_GSE121569"
        assert row["title"] == "A Test Study"
        assert row["journal"] == "Nature neuroscience"
        assert row["year"] == "2019"
        assert row["gse"] == "GSE121569"
        assert row["bioproject"] is None
        assert row["assay_types"] == "bulk RNA-seq"
        assert row["primary_route"] == "GEO"
        assert "not yet in studies.tsv" in row["notes"]

    def test_multiple_gse_joined_with_semicolon(self, tmp_path):
        self._write_readme(
            tmp_path, "Liu2019_CellReports_GSE126543",
            accessions='{"gse": ["GSE126541", "GSE126542"]}',
        )

        row = load_readme_header(tmp_path, "Liu2019_CellReports_GSE126543")

        assert row["gse"] == "GSE126541;GSE126542"

    def test_bioproject_and_synapse_and_cellxgene(self, tmp_path):
        self._write_readme(
            tmp_path, "SomeStudy",
            accessions='{"bioproject": "PRJNA1", "synapse": "syn1", "cellxgene": "col1"}',
        )

        row = load_readme_header(tmp_path, "SomeStudy")

        assert row["bioproject"] == "PRJNA1"
        assert row["synapse"] == "syn1"
        assert row["cellxgene_collection"] == "col1"
        assert row["gse"] is None

    def test_malformed_accessions_json_does_not_crash(self, tmp_path):
        self._write_readme(tmp_path, "BrokenStudy", accessions="{not valid json}")

        row = load_readme_header(tmp_path, "BrokenStudy")

        assert row["gse"] is None
        assert row["bioproject"] is None

    def test_unknown_journal_and_year(self, tmp_path):
        self._write_readme(tmp_path, "GSE310722_dataset", journal="unknown", year="unknown")

        row = load_readme_header(tmp_path, "GSE310722_dataset")

        assert row["journal"] == "unknown"
        assert row["year"] == "unknown"


class TestNormalizeOrganism:
    def test_plain_string_passthrough(self):
        assert normalize_organism("Homo sapiens") == "Homo sapiens"

    def test_none_passthrough(self):
        assert normalize_organism(None) is None

    def test_empty_string_passthrough(self):
        assert normalize_organism("") == ""

    def test_cellxgene_ontology_list_single_entry(self):
        # Real value observed in all_samples.tsv for Brain2025_Multiome /
        # CrypticExon_ActaNeuropathol2023 (2026-09-05).
        raw = "[{'label': 'Homo sapiens', 'ontology_term_id': 'NCBITaxon:9606'}]"
        assert normalize_organism(raw) == "Homo sapiens"

    def test_cellxgene_ontology_list_multiple_entries(self):
        raw = "[{'label': 'Homo sapiens', 'ontology_term_id': 'NCBITaxon:9606'}, {'label': 'Mus musculus', 'ontology_term_id': 'NCBITaxon:10090'}]"
        assert normalize_organism(raw) == "Homo sapiens; Mus musculus"

    def test_malformed_bracket_string_returned_unchanged(self):
        raw = "[{not valid python"
        assert normalize_organism(raw) == raw

    def test_list_of_non_dicts_returned_unchanged(self):
        raw = "[1, 2, 3]"
        assert normalize_organism(raw) == raw

    def test_dict_without_label_key_returned_unchanged(self):
        raw = "[{'ontology_term_id': 'NCBITaxon:9606'}]"
        assert normalize_organism(raw) == raw

    def test_not_a_list_literal_returned_unchanged(self):
        raw = "{'label': 'Homo sapiens'}"
        assert normalize_organism(raw) == raw


class TestSplitMultiParenAware:
    # Real values from studies.tsv `assay_types` (2026-09-06) that a naive
    # split on every ',' would break into orphaned '(' / ')' fragments.
    def test_comma_inside_parens_not_split(self):
        result = split_multi("scRNA-seq (iPSC-MN, ddSEQ + 10x)")
        assert result == ["scRNA-seq (iPSC-MN, ddSEQ + 10x)"]

    def test_comma_inside_parens_not_split_second_real_example(self):
        result = split_multi("scRNA-seq (Smart-seq2, iPSC-MN)")
        assert result == ["scRNA-seq (Smart-seq2, iPSC-MN)"]

    def test_semicolon_outside_parens_still_splits(self):
        result = split_multi("snRNA-seq (spinal cord); scRNA-seq (mouse SOD1)")
        assert result == ["snRNA-seq (spinal cord)", "scRNA-seq (mouse SOD1)"]

    def test_mixed_paren_and_bare_entries(self):
        result = split_multi("scRNA-seq (iPSC-MN); bulk RNA-seq (siQKI iPSC-MN); bulk RNA-seq (mouse OPC)")
        assert result == [
            "scRNA-seq (iPSC-MN)",
            "bulk RNA-seq (siQKI iPSC-MN)",
            "bulk RNA-seq (mouse OPC)",
        ]

    def test_unbalanced_closing_paren_does_not_crash(self):
        # depth is clamped at 0 rather than going negative
        result = split_multi("a), b, c")
        assert result == ["a)", "b", "c"]


class TestDedupeJoined:
    def test_none_passthrough(self):
        assert dedupe_joined(None) is None

    def test_empty_string_passthrough(self):
        assert dedupe_joined("") == ""

    def test_repeated_identical_parts_collapsed(self):
        # Real value from all_samples.tsv `tissue_or_cell_type` (2026-09-06)
        assert dedupe_joined("Cerebellum; Cerebellum") == "Cerebellum"

    def test_three_identical_parts_collapsed(self):
        assert dedupe_joined("X; X; X") == "X"

    def test_distinct_parts_left_alone(self):
        assert dedupe_joined("skin; iN") == "skin; iN"

    def test_partial_overlap_preserves_order_and_dedupes(self):
        assert dedupe_joined("Cerebellum; Cerebellum, BA4") == "Cerebellum; Cerebellum, BA4"

    def test_custom_separator(self):
        assert dedupe_joined("a,a,b", sep=",") == "a, b"

    def test_no_separator_present(self):
        assert dedupe_joined("motor cortex") == "motor cortex"


class TestBuildCaseInsensitiveCanon:
    def test_empty_input(self):
        assert build_case_insensitive_canon([]) == {}

    def test_no_duplicates(self):
        canon = build_case_insensitive_canon(["ALS", "Control"])
        assert canon == {"ALS": "ALS", "Control": "Control"}

    def test_merges_pure_case_variants_to_most_common(self):
        # Real counts from all_samples.tsv disease_status (2026-09-06):
        # 'Control' and 'control' both appear 112 times -- a tie, so it
        # breaks alphabetically ('Control' < 'control').
        canon = build_case_insensitive_canon(["Control"] * 112 + ["control"] * 112)
        assert canon["Control"] == "Control"
        assert canon["control"] == "Control"

    def test_merges_majority_casing_when_not_tied(self):
        canon = build_case_insensitive_canon(["Disorders"] * 245 + ["DIsorders"] * 8)
        assert canon["Disorders"] == "Disorders"
        assert canon["DIsorders"] == "Disorders"

    def test_ignores_none_and_empty(self):
        canon = build_case_insensitive_canon([None, "", "ALS"])
        assert canon == {"ALS": "ALS"}

    def test_strips_whitespace_before_grouping(self):
        canon = build_case_insensitive_canon([" ALS ", "ALS"])
        assert canon["ALS"] == "ALS"
        assert canon[" ALS "] == "ALS"

    def test_distinct_beyond_case_left_separate(self):
        canon = build_case_insensitive_canon(["Control", "CTL"])
        assert canon == {"Control": "Control", "CTL": "CTL"}