import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timezone
import json
import botocore.exceptions


@pytest.fixture
def mock_catalog():
    return {"studies": []}


@pytest.fixture
def mock_s3_client():
    client = MagicMock()
    client.exceptions.NoSuchKey = type('NoSuchKey', (Exception,), {})
    return client


class TestRequestDatasetDownload:
    
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_already_available_in_catalog(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test when identifier is already in catalog as available."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {
            "studies": [
                {
                    "study_id": "STUDY_001",
                    "bioproject": "PRJNA123456",
                    "access_restricted": False,
                }
            ]
        }
        
        request_dataset_download("PRJNA123456")
        
        mock_call_result.assert_called_once()
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "already_available"
        assert call_args["study_id"] == "STUDY_001"
    
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_already_tracked_restricted(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test when identifier is tracked but access-restricted."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {
            "studies": [
                {
                    "study_id": "STUDY_002",
                    "doi": "10.1234/example",
                    "access_restricted": True,
                }
            ]
        }
        
        request_dataset_download("10.1234/example")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "already_tracked_restricted"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_already_queued(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test when identifier is already in the download queue."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        
        existing_queue = [
            {
                "identifier": "GSE123456",
                "notes": "Previous request",
                "requested_at": "2026-09-08T12:00:00Z",
            }
        ]
        
        mock_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps(existing_queue).encode())),
            "ETag": '"abc123"',
        }
        
        request_dataset_download("GSE123456")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "already_queued"
        assert call_args["requested_at"] == "2026-09-08T12:00:00Z"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_new_request_queued_success(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test successfully queuing a new dataset request."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception()
        
        request_dataset_download("GSE999999", notes="Test dataset")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "queued"
        
        mock_client.put_object.assert_called_once()
        put_call = mock_client.put_object.call_args[1]
        body_json = json.loads(put_call["Body"].decode())
        assert body_json[0]["identifier"] == "GSE999999"
        assert body_json[0]["notes"] == "Test dataset"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_concurrent_write_retry_then_success(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that PreconditionFailed causes retry and eventual success."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        
        mock_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps([]).encode())),
            "ETag": '"abc123"',
        }
        
        error = botocore.exceptions.ClientError(
            {"Error": {"Code": "PreconditionFailed"}},
            "PutObject"
        )
        mock_client.put_object.side_effect = [error, None]
        
        request_dataset_download("GSE888888")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "queued"
        assert mock_client.put_object.call_count == 2
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_concurrent_write_max_retries_exceeded(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that max retries exceeded returns error status."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        
        mock_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps([]).encode())),
            "ETag": '"abc123"',
        }
        
        error = botocore.exceptions.ClientError(
            {"Error": {"Code": "PreconditionFailed"}},
            "PutObject"
        )
        mock_client.put_object.side_effect = error
        
        request_dataset_download("GSE777777")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "error"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    def test_other_s3_error_raises(self, mock_get_catalog, mock_default_client):
        """Test that non-PreconditionFailed errors are raised."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        
        mock_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps([]).encode())),
            "ETag": '"abc123"',
        }
        
        error = botocore.exceptions.ClientError(
            {"Error": {"Code": "AccessDenied"}},
            "PutObject"
        )
        mock_client.put_object.side_effect = error
        
        with pytest.raises(botocore.exceptions.ClientError):
            request_dataset_download("GSE666666")
    
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_case_insensitive_matching(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that identifier matching is case-insensitive."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {
            "studies": [
                {
                    "study_id": "STUDY_003",
                    "bioproject": "PRJNA123456",
                    "access_restricted": False,
                }
            ]
        }
        
        request_dataset_download("prjna123456")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "already_available"
    
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_whitespace_normalization(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that whitespace is stripped from identifiers."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {
            "studies": [
                {
                    "study_id": "STUDY_004",
                    "gse": ["GSE123456"],
                    "access_restricted": False,
                }
            ]
        }
        
        request_dataset_download("  GSE123456  ")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "already_available"
    
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_multiple_gse_identifiers(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test matching against multiple GSE identifiers in study."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {
            "studies": [
                {
                    "study_id": "STUDY_005",
                    "gse": ["GSE111111", "GSE222222", "GSE333333"],
                    "access_restricted": False,
                }
            ]
        }
        
        request_dataset_download("GSE222222")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "already_available"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket', 'DOWNLOAD_QUEUE_KEY': 'custom/queue.json'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_custom_queue_key_from_env(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that custom DOWNLOAD_QUEUE_KEY environment variable is used."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception()
        
        request_dataset_download("GSE555555")
        
        mock_client.get_object.assert_called_once()
        assert mock_client.get_object.call_args[1]["Key"] == "custom/queue.json"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_default_queue_key(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that default DOWNLOAD_QUEUE_KEY is used when not in env."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception()
        
        request_dataset_download("GSE444444")
        
        assert mock_client.get_object.call_args[1]["Key"] == "requests/download_next.json"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_etag_present_uses_if_match(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that IfMatch is used when etag is present."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        
        mock_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps([]).encode())),
            "ETag": '"etag123"',
        }
        
        request_dataset_download("GSE111111")
        
        put_call = mock_client.put_object.call_args[1]
        assert "IfMatch" in put_call
        assert put_call["IfMatch"] == '"etag123"'
        assert "IfNoneMatch" not in put_call
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_etag_absent_uses_if_none_match(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that IfNoneMatch is used when etag is absent."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception()
        
        request_dataset_download("GSE222222")
        
        put_call = mock_client.put_object.call_args[1]
        assert "IfNoneMatch" in put_call
        assert put_call["IfNoneMatch"] == "*"
        assert "IfMatch" not in put_call
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_none_fields_in_study(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that None fields in study dict don't cause errors."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {
            "studies": [
                {
                    "study_id": "STUDY_006",
                    "bioproject": None,
                    "doi": None,
                    "pmid": None,
                    "cellxgene_collection": None,
                    "synapse": None,
                    "gse": None,
                    "access_restricted": False,
                }
            ]
        }
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception()
        
        request_dataset_download("GSE333333")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "queued"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_412_error_treated_as_precondition_failed(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that 412 error code triggers retry."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        
        mock_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps([]).encode())),
            "ETag": '"abc123"',
        }
        
        error = botocore.exceptions.ClientError(
            {"Error": {"Code": "412"}},
            "PutObject"
        )
        mock_client.put_object.side_effect = [error, None]
        
        request_dataset_download("GSE444444")
        
        assert mock_client.put_object.call_count == 2
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_content_type_is_json(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that put_object specifies correct content type."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception()
        
        request_dataset_download("GSE555555")
        
        put_call = mock_client.put_object.call_args[1]
        assert put_call["ContentType"] == "application/json"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_datetime_format_correct(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that requested_at timestamp is in ISO format with Z suffix."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception()
        
        request_dataset_download("GSE666666")
        
        put_call = mock_client.put_object.call_args[1]
        body_json = json.loads(put_call["Body"].decode())
        
        timestamp = body_json[0]["requested_at"]
        assert timestamp.endswith("Z")
        assert len(timestamp) == 20
        datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_preserves_existing_queue_items(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that new request is appended to existing queue items."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        
        existing = [
            {"identifier": "GSE111111", "notes": "old", "requested_at": "2026-09-01T10:00:00Z"},
            {"identifier": "GSE222222", "notes": None, "requested_at": "2026-09-02T10:00:00Z"},
        ]
        
        mock_client.get_object.return_value = {
            "Body": Mock(read=Mock(return_value=json.dumps(existing).encode())),
            "ETag": '"abc123"',
        }
        
        request_dataset_download("GSE333333", notes="new")
        
        put_call = mock_client.put_object.call_args[1]
        body_json = json.loads(put_call["Body"].decode())
        
        assert len(body_json) == 3
        assert body_json[0]["identifier"] == "GSE111111"
        assert body_json[1]["identifier"] == "GSE222222"
        assert body_json[2]["identifier"] == "GSE333333"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_notes_can_be_none(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test that notes parameter can be None."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {"studies": []}
        
        mock_client = MagicMock()
        mock_default_client.return_value = mock_client
        mock_client.exceptions.NoSuchKey = Exception
        mock_client.get_object.side_effect = Exception()
        
        request_dataset_download("GSE777777", notes=None)
        
        put_call = mock_client.put_object.call_args[1]
        body_json = json.loads(put_call["Body"].decode())
        assert body_json[0]["notes"] is None
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_doi_identifier_matching(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test matching by DOI identifier."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {
            "studies": [
                {
                    "study_id": "STUDY_007",
                    "doi": "10.1234/example.doi",
                    "access_restricted": False,
                }
            ]
        }
        
        request_dataset_download("10.1234/example.doi")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "already_available"
    
    @patch.dict('os.environ', {'BUCKET_NAME': 'test-bucket'})
    @patch('request_dataset_download.default_client')
    @patch('request_dataset_download.get_catalog')
    @patch('request_dataset_download.build_result')
    def test_study_id_identifier_matching(self, mock_call_result, mock_get_catalog, mock_default_client):
        """Test matching by study_id identifier."""
        from request_dataset_download import request_dataset_download
        
        mock_get_catalog.return_value = {
            "studies": [
                {
                    "study_id": "STUDY_008",
                    "access_restricted": False,
                }
            ]
        }
        
        request_dataset_download("study_008")
        
        call_args = mock_call_result.call_args[0][1]
        assert call_args["status"] == "already_available"