import hashlib
import json
import pytest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch, mock_open, call
from datetime import datetime, timezone

# NOTE: deliberately not stubbing sys.modules['sources'] here -- sources.py is
# a real, dependency-free module (see test_sources.py), and globally
# replacing sys.modules entries leaks across every other test module in the
# same pytest session. Tests that need it mocked do so per-test via
# @patch('s3_sync.sources'), which is properly scoped and undone after.

from s3_sync import _sha256_file, eligible_studies, _existing_sha256, sync_study, main


class TestSha256File:
    def test_sha256_file_single_chunk(self, tmp_path):
        content = b"hello world"
        path = tmp_path / "test.txt"
        path.write_bytes(content)

        result = _sha256_file(path)

        assert result == hashlib.sha256(content).hexdigest()

    def test_sha256_file_multiple_chunks(self, tmp_path):
        content = b"a" * (1024 * 1024) + b"b" * (512 * 1024)
        path = tmp_path / "large.txt"
        path.write_bytes(content)

        result = _sha256_file(path)

        assert result == hashlib.sha256(content).hexdigest()

    def test_sha256_file_empty(self, tmp_path):
        path = tmp_path / "empty.txt"
        path.write_bytes(b"")

        result = _sha256_file(path)

        assert result == hashlib.sha256(b"").hexdigest()

    def test_sha256_file_binary_content(self, tmp_path):
        content = bytes(range(256))
        path = tmp_path / "binary.dat"
        path.write_bytes(content)

        result = _sha256_file(path)

        assert result == hashlib.sha256(content).hexdigest()


class TestEligibleStudies:
    @patch('s3_sync.sources')
    def test_all_eligible(self, mock_sources):
        mock_sources.load_studies_tsv.return_value = {"study1": {}, "study2": {}}
        mock_sources.list_study_ids.return_value = ["study1", "study2"]
        mock_sources.load_build_summary.return_value = {}
        mock_sources.skipped_study_ids.return_value = set()
        mock_sources.load_status_json.return_value = {
            "study1": {"phase": "converted"},
            "study2": {"phase": "converted"},
        }
        mock_sources.get_study_phase.side_effect = [
            ("converted", None),
            ("converted", None),
        ]
        mock_sources.list_processed_files.side_effect = [
            [{"name": "file1.txt", "category": "data"}],
            [{"name": "file2.txt", "category": "data"}],
        ]
        
        eligible, skipped = eligible_studies(Path("/root"), Path("/coord"))
        
        assert set(eligible) == {"study1", "study2"}
        assert skipped == {}

    @patch('s3_sync.sources')
    def test_hard_skipped_study(self, mock_sources):
        mock_sources.load_studies_tsv.return_value = {"study1": {}}
        mock_sources.list_study_ids.return_value = ["study1"]
        mock_sources.load_build_summary.return_value = {}
        mock_sources.skipped_study_ids.return_value = {"study1"}
        mock_sources.load_status_json.return_value = {}
        
        eligible, skipped = eligible_studies(Path("/root"), Path("/coord"))
        
        assert eligible == []
        assert "study1" in skipped
        assert "explicitly skipped in build_summary.json" in skipped["study1"]

    @patch('s3_sync.sources')
    def test_unconverted_study(self, mock_sources):
        mock_sources.load_studies_tsv.return_value = {"study1": {}}
        mock_sources.list_study_ids.return_value = ["study1"]
        mock_sources.load_build_summary.return_value = {}
        mock_sources.skipped_study_ids.return_value = set()
        mock_sources.load_status_json.return_value = {"study1": {"phase": "raw"}}
        mock_sources.get_study_phase.return_value = ("raw", "pending")
        
        eligible, skipped = eligible_studies(Path("/root"), Path("/coord"))
        
        assert eligible == []
        assert "study1" in skipped
        assert "conversion phase is 'raw'" in skipped["study1"]

    @patch('s3_sync.sources')
    def test_converted_partial_study(self, mock_sources):
        mock_sources.load_studies_tsv.return_value = {"study1": {}}
        mock_sources.list_study_ids.return_value = ["study1"]
        mock_sources.load_build_summary.return_value = {}
        mock_sources.skipped_study_ids.return_value = set()
        mock_sources.load_status_json.return_value = {}
        mock_sources.get_study_phase.return_value = ("converted_partial", None)
        mock_sources.list_processed_files.return_value = [
            {"name": "file1.txt", "category": "data"}
        ]
        
        eligible, skipped = eligible_studies(Path("/root"), Path("/coord"))
        
        assert eligible == ["study1"]
        assert skipped == {}

    @patch('s3_sync.sources')
    def test_no_data_files(self, mock_sources):
        mock_sources.load_studies_tsv.return_value = {"study1": {}}
        mock_sources.list_study_ids.return_value = ["study1"]
        mock_sources.load_build_summary.return_value = {}
        mock_sources.skipped_study_ids.return_value = set()
        mock_sources.load_status_json.return_value = {}
        mock_sources.get_study_phase.return_value = ("converted", None)
        mock_sources.list_processed_files.return_value = [
            {"name": "metadata.json", "category": "metadata"},
            {"name": "doc.txt", "category": "doc"},
        ]
        
        eligible, skipped = eligible_studies(Path("/root"), Path("/coord"))
        
        assert eligible == []
        assert "study1" in skipped
        assert "no 'data'-category files" in skipped["study1"]

    @patch('s3_sync.sources')
    def test_mixed_eligible_and_skipped(self, mock_sources):
        mock_sources.load_studies_tsv.return_value = {
            "s1": {}, "s2": {}, "s3": {}, "s4": {}
        }
        mock_sources.list_study_ids.return_value = ["s1", "s2", "s3", "s4"]
        mock_sources.load_build_summary.return_value = {}
        mock_sources.skipped_study_ids.return_value = {"s1"}
        mock_sources.load_status_json.return_value = {}
        # s1 is hard-skipped before its phase is ever checked. Of the
        # remaining s2/s3/s4, only studies whose phase is converted go on
        # to have list_processed_files called at all -- s3's "raw" phase
        # short-circuits before that call.
        mock_sources.get_study_phase.side_effect = [
            ("converted", None),  # s2
            ("raw", None),        # s3 -- skipped here, list_processed_files not called
            ("converted", None),  # s4
        ]
        mock_sources.list_processed_files.side_effect = [
            [{"name": "file.txt", "category": "data"}],      # s2 -> eligible
            [{"name": "file.txt", "category": "metadata"}],  # s4 -> no data files, skipped
        ]

        eligible, skipped = eligible_studies(Path("/root"), Path("/coord"))

        assert set(eligible) == {"s2"}
        assert len(skipped) == 3


class TestExistingSha256:
    def test_existing_sha256_found(self):
        mock_client = MagicMock()
        mock_client.head_object.return_value = {
            "Metadata": {"sha256": "abc123"}
        }
        
        result = _existing_sha256(mock_client, "my-bucket", "key/path")
        
        assert result == "abc123"
        mock_client.head_object.assert_called_once_with(Bucket="my-bucket", Key="key/path")

    def test_existing_sha256_not_found(self):
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"
        )

        result = _existing_sha256(mock_client, "my-bucket", "key/path")

        assert result is None

    def test_existing_sha256_no_metadata(self):
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"Metadata": {}}
        
        result = _existing_sha256(mock_client, "my-bucket", "key/path")
        
        assert result is None

    def test_existing_sha256_missing_metadata_key(self):
        mock_client = MagicMock()
        mock_client.head_object.return_value = {}
        
        result = _existing_sha256(mock_client, "my-bucket", "key/path")
        
        assert result is None


class TestSyncStudy:
    @patch('s3_sync._sha256_file')
    @patch('s3_sync.sources')
    def test_sync_study_upload_new_files(self, mock_sources, mock_sha256):
        mock_sources.list_processed_files.return_value = [
            {"name": "file1.txt", "bytes": 100, "category": "data"},
            {"name": "file2.txt", "bytes": 200, "category": "data"},
        ]
        mock_sha256.side_effect = ["hash1", "hash2"]
        
        mock_client = MagicMock()
        
        receipt = sync_study(
            mock_client, Path("/root"), "study1", "bucket", dry_run=False
        )
        
        assert receipt["study_id"] == "study1"
        assert receipt["s3_prefix"] == "processed/study1/"
        assert len(receipt["uploaded"]) == 2
        assert receipt["uploaded"][0]["sha256"] == "hash1"
        assert receipt["uploaded"][1]["sha256"] == "hash2"
        assert len(receipt["skipped_unchanged"]) == 0
        assert receipt["dry_run"] is False
        assert mock_client.upload_file.call_count == 2

    @patch('s3_sync._sha256_file')
    @patch('s3_sync._existing_sha256')
    @patch('s3_sync.sources')
    def test_sync_study_skip_unchanged(self, mock_sources, mock_existing, mock_sha256):
        mock_sources.list_processed_files.return_value = [
            {"name": "file1.txt", "bytes": 100, "category": "data"},
        ]
        mock_sha256.return_value = "hash1"
        mock_existing.return_value = "hash1"
        
        mock_client = MagicMock()
        
        receipt = sync_study(
            mock_client, Path("/root"), "study1", "bucket", dry_run=False
        )
        
        assert len(receipt["uploaded"]) == 0
        assert receipt["skipped_unchanged"] == ["file1.txt"]
        mock_client.upload_file.assert_not_called()

    @patch('s3_sync._sha256_file')
    @patch('s3_sync.sources')
    def test_sync_study_dry_run(self, mock_sources, mock_sha256):
        mock_sources.list_processed_files.return_value = [
            {"name": "file1.txt", "bytes": 100, "category": "data"},
        ]
        mock_sha256.return_value = "hash1"
        
        mock_client = MagicMock()
        
        receipt = sync_study(
            mock_client, Path("/root"), "study1", "bucket", dry_run=True
        )
        
        assert receipt["dry_run"] is True
        assert len(receipt["uploaded"]) == 1
        assert len(receipt["skipped_unchanged"]) == 0
        mock_client.upload_file.assert_not_called()

    @patch('s3_sync._sha256_file')
    @patch('s3_sync.sources')
    def test_sync_study_mixed_files(self, mock_sources, mock_sha256):
        mock_sources.list_processed_files.return_value = [
            {"name": "new.txt", "bytes": 100, "category": "data"},
            {"name": "unchanged.txt", "bytes": 200, "category": "data"},
        ]
        mock_sha256.side_effect = ["hash_new", "hash_unchanged"]

        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.head_object.side_effect = [
            ClientError({"Error": {"Code": "404", "Message": "Not Found"}}, "HeadObject"),
            {"Metadata": {"sha256": "hash_unchanged"}},
        ]
        
        receipt = sync_study(
            mock_client, Path("/root"), "study1", "bucket", dry_run=False
        )
        
        assert len(receipt["uploaded"]) == 1
        assert len(receipt["skipped_unchanged"]) == 1
        assert mock_client.upload_file.call_count == 1

    @patch('s3_sync._sha256_file')
    @patch('s3_sync.sources')
    def test_sync_study_empty_processed_dir(self, mock_sources, mock_sha256):
        mock_sources.list_processed_files.return_value = []
        
        mock_client = MagicMock()
        
        receipt = sync_study(
            mock_client, Path("/root"), "study1", "bucket", dry_run=False
        )
        
        assert len(receipt["uploaded"]) == 0
        assert len(receipt["skipped_unchanged"]) == 0
        mock_client.upload_file.assert_not_called()

    @patch('s3_sync._sha256_file')
    @patch('s3_sync.sources')
    def test_sync_study_metadata_in_upload(self, mock_sources, mock_sha256):
        mock_sources.list_processed_files.return_value = [
            {"name": "file.txt", "bytes": 50, "category": "data"},
        ]
        mock_sha256.return_value = "abc123"
        
        mock_client = MagicMock()
        
        receipt = sync_study(
            mock_client, Path("/root"), "study1", "bucket", dry_run=False
        )
        
        call_args = mock_client.upload_file.call_args
        assert call_args[0][0] == str(Path("/root/studies/study1/processed/file.txt"))
        assert call_args[0][1] == "bucket"
        assert call_args[0][2] == "processed/study1/file.txt"
        assert call_args[1]["ExtraArgs"]["Metadata"]["sha256"] == "abc123"


class TestMain:
    @patch('s3_sync.sync_study')
    @patch('s3_sync.eligible_studies')
    @patch('s3_sync.boto3')
    def test_main_success(self, mock_boto3, mock_eligible, mock_sync):
        mock_eligible.return_value = (["study1"], {"study2": "reason"})
        mock_sync.return_value = {
            "study_id": "study1",
            "s3_prefix": "processed/study1/",
            "uploaded": [{"name": "file.txt"}],
            "skipped_unchanged": [],
            "dry_run": False,
            "synced_at": "2024-01-01T00:00:00Z",
        }
        
        with patch('sys.argv', [
            'script', '--root', '/root', '--coordination-root', '/coord',
            '--bucket', 'test-bucket', '--out-dir', '/out'
        ]):
            with patch('pathlib.Path.mkdir'):
                with patch('pathlib.Path.write_text') as mock_write:
                    with patch('builtins.print'):
                        main()
        
        mock_eligible.assert_called_once()
        mock_sync.assert_called_once()
        assert mock_write.call_count >= 2

    @patch('s3_sync.boto3', None)
    def test_main_no_boto3(self):
        with patch('sys.argv', [
            'script', '--root', '/root', '--coordination-root', '/coord',
            '--bucket', 'test-bucket', '--out-dir', '/out'
        ]):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert "boto3 is required" in str(exc_info.value)

    @patch('s3_sync.sync_study')
    @patch('s3_sync.eligible_studies')
    @patch('s3_sync.boto3')
    def test_main_dry_run(self, mock_boto3, mock_eligible, mock_sync):
        mock_eligible.return_value = (["study1"], {})
        mock_sync.return_value = {
            "study_id": "study1",
            "s3_prefix": "processed/study1/",
            "uploaded": [],
            "skipped_unchanged": [],
            "dry_run": True,
            "synced_at": "2024-01-01T00:00:00Z",
        }
        
        with patch('sys.argv', [
            'script', '--root', '/root', '--coordination-root', '/coord',
            '--bucket', 'test-bucket', '--out-dir', '/out', '--dry-run'
        ]):
            with patch('pathlib.Path.mkdir'):
                with patch('pathlib.Path.write_text'):
                    with patch('builtins.print'):
                        main()
        
        call_args = mock_sync.call_args
        assert call_args[0][3] == 'test-bucket'
        assert call_args[0][4] == True

    @patch('s3_sync.sync_study')
    @patch('s3_sync.eligible_studies')
    @patch('s3_sync.boto3')
    def test_main_only_filter(self, mock_boto3, mock_eligible, mock_sync):
        mock_eligible.return_value = (["study1", "study2"], {})
        mock_sync.return_value = {
            "study_id": "study1",
            "s3_prefix": "processed/study1/",
            "uploaded": [],
            "skipped_unchanged": [],
            "dry_run": False,
            "synced_at": "2024-01-01T00:00:00Z",
        }
        
        with patch('sys.argv', [
            'script', '--root', '/root', '--coordination-root', '/coord',
            '--bucket', 'test-bucket', '--out-dir', '/out', '--only', 'study1'
        ]):
            with patch('pathlib.Path.mkdir'):
                with patch('pathlib.Path.write_text'):
                    with patch('builtins.print'):
                        main()
        
        mock_sync.assert_called_once()
        assert mock_sync.call_args[0][2] == "study1"

    @patch('s3_sync.sync_study')
    @patch('s3_sync.eligible_studies')
    @patch('s3_sync.boto3')
    def test_main_output_files(self, mock_boto3, mock_eligible, mock_sync):
        mock_eligible.return_value = (["study1"], {"study2": "skipped"})
        mock_sync.return_value = {
            "study_id": "study1",
            "s3_prefix": "processed/study1/",
            "uploaded": [{"name": "file.txt"}],
            "skipped_unchanged": [],
            "dry_run": False,
            "synced_at": "2024-01-01T00:00:00Z",
        }
        
        with patch('sys.argv', [
            'script', '--root', '/root', '--coordination-root', '/coord',
            '--bucket', 'test-bucket', '--out-dir', '/out'
        ]):
            with patch('pathlib.Path.mkdir'):
                with patch('pathlib.Path.write_text') as mock_write:
                    with patch('builtins.print'):
                        main()
        
        writes = [call[0][0] for call in mock_write.call_args_list]
        written_json = None
        for write in writes:
            try:
                data = json.loads(write)
                if "skipped" in data:
                    written_json = data
                    break
            except (json.JSONDecodeError, TypeError):
                pass
        
        assert written_json is not None
        assert written_json["eligible_count"] == 1
        assert written_json["skipped_count"] == 1
        assert "study2" in written_json["skipped"]

    @patch('s3_sync.sync_study')
    @patch('s3_sync.eligible_studies')
    @patch('s3_sync.boto3')
    def test_main_with_region(self, mock_boto3, mock_eligible, mock_sync):
        mock_eligible.return_value = ([], {})
        mock_boto3.client.return_value = MagicMock()
        
        with patch('sys.argv', [
            'script', '--root', '/root', '--coordination-root', '/coord',
            '--bucket', 'test-bucket', '--out-dir', '/out', '--region', 'us-west-2'
        ]):
            with patch('pathlib.Path.mkdir'):
                with patch('pathlib.Path.write_text'):
                    with patch('builtins.print'):
                        main()
        
        mock_boto3.client.assert_called_once_with("s3", region_name="us-west-2")

    @patch('s3_sync.sync_study')
    @patch('s3_sync.eligible_studies')
    @patch('s3_sync.boto3')
    def test_main_multiple_only_filters(self, mock_boto3, mock_eligible, mock_sync):
        mock_eligible.return_value = (["s1", "s2", "s3"], {})
        mock_sync.return_value = {
            "study_id": "s1",
            "s3_prefix": "processed/s1/",
            "uploaded": [],
            "skipped_unchanged": [],
            "dry_run": False,
            "synced_at": "2024-01-01T00:00:00Z",
        }
        
        with patch('sys.argv', [
            'script', '--root', '/root', '--coordination-root', '/coord',
            '--bucket', 'test-bucket', '--out-dir', '/out',
            '--only', 's1', '--only', 's2'
        ]):
            with patch('pathlib.Path.mkdir'):
                with patch('pathlib.Path.write_text'):
                    with patch('builtins.print'):
                        main()
        
        assert mock_sync.call_count == 2