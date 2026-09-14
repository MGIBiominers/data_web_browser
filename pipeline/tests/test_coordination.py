import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
import pytest

from coordination import SESSION_NAME, _now_iso, append_changelog, write_status


class Test_now_iso:
    @patch('coordination.datetime')
    def test_returns_utc_iso_format(self, mock_datetime):
        """_now_iso returns datetime in UTC ISO 8601 format with Z suffix"""
        mock_now = Mock()
        mock_now.strftime.return_value = "2026-09-05T14:30:45Z"
        mock_datetime.now.return_value = mock_now
        
        result = _now_iso()
        
        assert result == "2026-09-05T14:30:45Z"
    
    @patch('coordination.datetime')
    def test_datetime_now_called_with_utc_timezone(self, mock_datetime):
        """_now_iso calls datetime.now with UTC timezone"""
        mock_now = Mock()
        mock_now.strftime.return_value = "2026-01-01T00:00:00Z"
        mock_datetime.now.return_value = mock_now
        
        _now_iso()
        
        mock_datetime.now.assert_called_once_with(timezone.utc)
    
    @patch('coordination.datetime')
    def test_strftime_format_string(self, mock_datetime):
        """_now_iso uses correct strftime format"""
        mock_now = Mock()
        mock_now.strftime.return_value = "2026-01-01T00:00:00Z"
        mock_datetime.now.return_value = mock_now
        
        _now_iso()
        
        mock_now.strftime.assert_called_once_with("%Y-%m-%dT%H:%M:%SZ")


class TestAppendChangelog:
    @patch('coordination._now_iso')
    def test_appends_entry_to_changelog(self, mock_now_iso, tmp_path):
        """append_changelog adds JSON line to CHANGELOG.jsonl"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        append_changelog(tmp_path, "test_action", "study_1", ["file1.txt"], "test note")
        
        changelog_file = tmp_path / "CHANGELOG.jsonl"
        assert changelog_file.exists()
        content = changelog_file.read_text()
        entry = json.loads(content.strip())
        assert entry["action"] == "test_action"
    
    @patch('coordination._now_iso')
    def test_creates_entry_with_all_fields(self, mock_now_iso, tmp_path):
        """append_changelog creates entry with all required fields in correct structure"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        append_changelog(tmp_path, "action_x", "study_2", ["f1", "f2"], "note text")
        
        changelog_file = tmp_path / "CHANGELOG.jsonl"
        entry = json.loads(changelog_file.read_text().strip())
        
        assert entry["ts"] == "2026-09-05T14:30:45Z"
        assert entry["session"] == SESSION_NAME
        assert entry["action"] == "action_x"
        assert entry["study_id"] == "study_2"
        assert entry["files"] == ["f1", "f2"]
        assert entry["note"] == "note text"
    
    @patch('coordination._now_iso')
    def test_none_study_id_preserved(self, mock_now_iso, tmp_path):
        """append_changelog preserves None study_id in JSON"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        append_changelog(tmp_path, "action", None, [], "note")
        
        changelog_file = tmp_path / "CHANGELOG.jsonl"
        entry = json.loads(changelog_file.read_text().strip())
        
        assert entry["study_id"] is None
    
    @patch('coordination._now_iso')
    def test_empty_files_list(self, mock_now_iso, tmp_path):
        """append_changelog works with empty files list"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        append_changelog(tmp_path, "action", "study_1", [], "note")
        
        changelog_file = tmp_path / "CHANGELOG.jsonl"
        entry = json.loads(changelog_file.read_text().strip())
        
        assert entry["files"] == []
    
    @patch('coordination._now_iso')
    def test_multiple_files_preserved(self, mock_now_iso, tmp_path):
        """append_changelog preserves full files list"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        files_list = ["file1.txt", "file2.txt", "file3.txt"]
        append_changelog(tmp_path, "action", "study", files_list, "note")
        
        changelog_file = tmp_path / "CHANGELOG.jsonl"
        entry = json.loads(changelog_file.read_text().strip())
        
        assert entry["files"] == files_list
    
    @patch('coordination._now_iso')
    def test_append_mode_does_not_truncate(self, mock_now_iso, tmp_path):
        """append_changelog appends without truncating existing file"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        append_changelog(tmp_path, "action1", "study_1", [], "note1")
        append_changelog(tmp_path, "action2", "study_2", [], "note2")
        
        changelog_file = tmp_path / "CHANGELOG.jsonl"
        lines = changelog_file.read_text().strip().split('\n')
        
        assert len(lines) == 2
        assert json.loads(lines[0])["action"] == "action1"
        assert json.loads(lines[1])["action"] == "action2"
    
    @patch('coordination._now_iso')
    def test_valid_json_per_line(self, mock_now_iso, tmp_path):
        """append_changelog writes valid JSON lines"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        append_changelog(tmp_path, "action", "study", ["file.txt"], "note")
        
        changelog_file = tmp_path / "CHANGELOG.jsonl"
        for line in changelog_file.read_text().strip().split('\n'):
            json.loads(line)
    
    @patch('coordination._now_iso')
    def test_timestamp_from_now_iso(self, mock_now_iso, tmp_path):
        """append_changelog uses _now_iso for ts field"""
        test_ts = "2026-03-15T12:34:56Z"
        mock_now_iso.return_value = test_ts
        
        append_changelog(tmp_path, "action", "study", [], "note")
        
        changelog_file = tmp_path / "CHANGELOG.jsonl"
        entry = json.loads(changelog_file.read_text().strip())
        
        assert entry["ts"] == test_ts
    
    @patch('coordination._now_iso')
    def test_session_name_constant(self, mock_now_iso, tmp_path):
        """append_changelog uses SESSION_NAME constant"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        append_changelog(tmp_path, "action", "study", [], "note")
        
        changelog_file = tmp_path / "CHANGELOG.jsonl"
        entry = json.loads(changelog_file.read_text().strip())
        
        assert entry["session"] == "s3_publish"


class TestWriteStatus:
    @patch('coordination._now_iso')
    def test_creates_status_file(self, mock_now_iso, tmp_path):
        """write_status creates s3_publish_status.json file"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        write_status(tmp_path, {})
        
        status_file = tmp_path / "s3_publish_status.json"
        assert status_file.exists()
        assert status_file.is_file()
    
    @patch('coordination._now_iso')
    def test_creates_file_with_required_fields(self, mock_now_iso, tmp_path):
        """write_status creates file with session, updated_at, source_of_seed, studies"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        write_status(tmp_path, {})
        
        status_file = tmp_path / "s3_publish_status.json"
        doc = json.loads(status_file.read_text())
        
        assert "session" in doc
        assert "updated_at" in doc
        assert "source_of_seed" in doc
        assert "studies" in doc
    
    @patch('coordination._now_iso')
    def test_session_field_value(self, mock_now_iso, tmp_path):
        """write_status sets session field to SESSION_NAME"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        write_status(tmp_path, {})
        
        status_file = tmp_path / "s3_publish_status.json"
        doc = json.loads(status_file.read_text())
        
        assert doc["session"] == "s3_publish"
    
    @patch('coordination._now_iso')
    def test_updated_at_field_value(self, mock_now_iso, tmp_path):
        """write_status sets updated_at to _now_iso result"""
        test_ts = "2026-09-05T14:30:45Z"
        mock_now_iso.return_value = test_ts
        
        write_status(tmp_path, {})
        
        status_file = tmp_path / "s3_publish_status.json"
        doc = json.loads(status_file.read_text())
        
        assert doc["updated_at"] == test_ts
    
    @patch('coordination._now_iso')
    def test_source_of_seed_field_value(self, mock_now_iso, tmp_path):
        """write_status includes expected source_of_seed documentation"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        write_status(tmp_path, {})
        
        status_file = tmp_path / "s3_publish_status.json"
        doc = json.loads(status_file.read_text())
        
        assert "Written by pipeline/publish.py" in doc["source_of_seed"]
    
    @patch('coordination._now_iso')
    def test_studies_field_empty_dict(self, mock_now_iso, tmp_path):
        """write_status preserves empty studies dict"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        write_status(tmp_path, {})
        
        status_file = tmp_path / "s3_publish_status.json"
        doc = json.loads(status_file.read_text())
        
        assert doc["studies"] == {}
    
    @patch('coordination._now_iso')
    def test_studies_field_single_study(self, mock_now_iso, tmp_path):
        """write_status preserves single study in studies field"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        studies = {"study_1": {"phase": "alignment", "note": "done"}}
        
        write_status(tmp_path, studies)
        
        status_file = tmp_path / "s3_publish_status.json"
        doc = json.loads(status_file.read_text())
        
        assert doc["studies"] == studies
    
    @patch('coordination._now_iso')
    def test_studies_field_multiple_studies(self, mock_now_iso, tmp_path):
        """write_status preserves multiple studies"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        studies = {
            "study_1": {"phase": "alignment", "note": "done"},
            "study_2": {"phase": "verification", "note": "in progress"},
            "study_3": {"phase": "download", "note": "pending"},
        }
        
        write_status(tmp_path, studies)
        
        status_file = tmp_path / "s3_publish_status.json"
        doc = json.loads(status_file.read_text())
        
        assert doc["studies"] == studies
    
    @patch('coordination._now_iso')
    def test_overwrites_existing_file(self, mock_now_iso, tmp_path):
        """write_status overwrites existing s3_publish_status.json"""
        status_file = tmp_path / "s3_publish_status.json"
        status_file.write_text('{"old": "data"}')
        
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        studies = {"study_1": {"phase": "new"}}
        write_status(tmp_path, studies)
        
        doc = json.loads(status_file.read_text())
        assert "old" not in doc
        assert doc["studies"]["study_1"]["phase"] == "new"
    
    @patch('coordination._now_iso')
    def test_json_indentation(self, mock_now_iso, tmp_path):
        """write_status writes pretty-printed JSON with indent=2"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        
        write_status(tmp_path, {})
        
        status_file = tmp_path / "s3_publish_status.json"
        content = status_file.read_text()
        
        assert "\n" in content
        assert "  " in content
    
    @patch('coordination._now_iso')
    def test_preserves_nested_study_data(self, mock_now_iso, tmp_path):
        """write_status preserves complex nested study structures"""
        mock_now_iso.return_value = "2026-09-05T14:30:45Z"
        studies = {
            "study_1": {
                "phase": "alignment",
                "note": "completed",
                "extra_field": "value",
                "nested": {"key": "val"},
            },
        }
        
        write_status(tmp_path, studies)
        
        status_file = tmp_path / "s3_publish_status.json"
        doc = json.loads(status_file.read_text())
        
        assert doc["studies"]["study_1"]["extra_field"] == "value"
        assert doc["studies"]["study_1"]["nested"]["key"] == "val"