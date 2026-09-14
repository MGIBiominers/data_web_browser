import pytest
from unittest.mock import patch, MagicMock, call
import json
import sys

# Mock boto3 before importing the module under test
sys.modules['boto3'] = MagicMock()

import catalog_cache


@pytest.fixture
def reset_state():
    """Clear module-level cache state before and after each test."""
    catalog_cache._state.clear()
    yield
    catalog_cache._state.clear()


class TestGetCachedLocalSource:
    """Tests for _get_cached with local filesystem source."""

    def test_local_source_reads_from_file(self, reset_state):
        """When _LOCAL_SOURCE is True, read from local directory."""
        test_data = {"test": "data", "key": "value"}

        mock_path = MagicMock()
        mock_path.__truediv__.return_value.read_text.return_value = json.dumps(test_data)

        with patch.object(catalog_cache, '_LOCAL_SOURCE', True):
            with patch.object(catalog_cache, '_LOCAL_DIR', mock_path):
                result = catalog_cache._get_cached('metadata/catalog.json', 'test_cache')

        assert result == test_data
        mock_path.__truediv__.assert_called_once()


class TestGetCachedS3Source:
    """Tests for _get_cached with S3 source."""

    def test_s3_cache_miss_fetches_and_stores(self, reset_state):
        """On cache miss (new ETag), fetch from S3 and store."""
        test_data = {"studies": [{"study_id": "s1"}]}
        test_etag = '"md5hashvalue"'

        mock_client = MagicMock()
        mock_client.head_object.return_value = {'ETag': test_etag}
        mock_client.get_object.return_value = {
            'Body': MagicMock(read=MagicMock(return_value=json.dumps(test_data).encode()))
        }

        with patch.object(catalog_cache, '_LOCAL_SOURCE', False):
            with patch.object(catalog_cache, '_BUCKET', 'my-bucket'):
                with patch.object(catalog_cache, '_CATALOG_KEY', 'metadata/catalog.json'):
                    with patch('catalog_cache.boto3.client', return_value=mock_client):
                        result = catalog_cache._get_cached('metadata/catalog.json', 'catalog')

        assert result == test_data
        assert catalog_cache._state['catalog'] == test_data
        assert catalog_cache._state['catalog_etag'] == test_etag
        mock_client.head_object.assert_called_once_with(
            Bucket='my-bucket', Key='metadata/catalog.json'
        )
        mock_client.get_object.assert_called_once_with(
            Bucket='my-bucket', Key='metadata/catalog.json'
        )

    def test_s3_cache_hit_skips_fetch(self, reset_state):
        """On cache hit (same ETag), skip get_object call."""
        test_data = {"studies": []}
        test_etag = '"md5hashvalue"'
        catalog_cache._state['catalog'] = test_data
        catalog_cache._state['catalog_etag'] = test_etag

        mock_client = MagicMock()
        mock_client.head_object.return_value = {'ETag': test_etag}

        with patch.object(catalog_cache, '_LOCAL_SOURCE', False):
            with patch.object(catalog_cache, '_BUCKET', 'my-bucket'):
                with patch.object(catalog_cache, '_CATALOG_KEY', 'metadata/catalog.json'):
                    with patch('catalog_cache.boto3.client', return_value=mock_client):
                        result = catalog_cache._get_cached('metadata/catalog.json', 'catalog')

        assert result == test_data
        mock_client.head_object.assert_called_once()
        mock_client.get_object.assert_not_called()

    def test_s3_etag_changed_refetches(self, reset_state):
        """When ETag changes, fetch new data."""
        old_data = {"version": 1}
        new_data = {"version": 2}
        old_etag = '"old"'
        new_etag = '"new"'

        catalog_cache._state['catalog'] = old_data
        catalog_cache._state['catalog_etag'] = old_etag

        mock_client = MagicMock()
        mock_client.head_object.return_value = {'ETag': new_etag}
        mock_client.get_object.return_value = {
            'Body': MagicMock(read=MagicMock(return_value=json.dumps(new_data).encode()))
        }

        with patch.object(catalog_cache, '_LOCAL_SOURCE', False):
            with patch.object(catalog_cache, '_BUCKET', 'my-bucket'):
                with patch.object(catalog_cache, '_CATALOG_KEY', 'metadata/catalog.json'):
                    with patch('catalog_cache.boto3.client', return_value=mock_client):
                        result = catalog_cache._get_cached('metadata/catalog.json', 'catalog')

        assert result == new_data
        assert catalog_cache._state['catalog'] == new_data
        assert catalog_cache._state['catalog_etag'] == new_etag
        mock_client.get_object.assert_called_once()


class TestGetCatalog:
    """Tests for get_catalog() function."""

    def test_get_catalog_calls_get_cached_correctly(self, reset_state):
        """get_catalog calls _get_cached with correct parameters."""
        expected_result = {
            "generated_at": "2026-01-01T00:00:00Z",
            "source_root": "s3://my-bucket/data",
            "studies": [{"study_id": "GSE123"}]
        }

        with patch('catalog_cache._get_cached', return_value=expected_result) as mock_get:
            with patch.object(catalog_cache, '_CATALOG_KEY', 'metadata/catalog.json'):
                result = catalog_cache.get_catalog()

        assert result == expected_result
        mock_get.assert_called_once_with('metadata/catalog.json', 'catalog')

    def test_get_catalog_returns_dict(self, reset_state):
        """get_catalog returns a dict (not list or other type)."""
        test_dict = {"key": "value"}

        with patch('catalog_cache._get_cached', return_value=test_dict):
            result = catalog_cache.get_catalog()
            assert isinstance(result, dict)


class TestGetSamples:
    """Tests for get_samples() function."""

    def test_get_samples_unwraps_wrapper_object(self, reset_state):
        """get_samples unwraps {"samples": [...]} structure."""
        sample_list = [
            {"sample_id": "S1", "study_id": "GSE123"},
            {"sample_id": "S2", "study_id": "GSE123"}
        ]
        wrapper = {
            "generated_at": "2026-01-01T00:00:00Z",
            "samples": sample_list
        }

        with patch('catalog_cache._get_cached', return_value=wrapper):
            result = catalog_cache.get_samples()

        assert result == sample_list
        assert isinstance(result, list)
        assert len(result) == 2

    def test_get_samples_empty_list(self, reset_state):
        """get_samples handles empty samples list."""
        wrapper = {"generated_at": "2026-01-01T00:00:00Z", "samples": []}

        with patch('catalog_cache._get_cached', return_value=wrapper):
            result = catalog_cache.get_samples()

        assert result == []

    def test_get_samples_calls_get_cached_correctly(self, reset_state):
        """get_samples calls _get_cached with correct parameters."""
        with patch('catalog_cache._get_cached') as mock_get:
            with patch.object(catalog_cache, '_SAMPLES_KEY', 'metadata/samples.json'):
                mock_get.return_value = {"samples": []}
                catalog_cache.get_samples()

        mock_get.assert_called_once_with('metadata/samples.json', 'samples')

    def test_get_samples_missing_key_raises_error(self, reset_state):
        """Missing 'samples' key in wrapper raises KeyError."""
        malformed_wrapper = {"generated_at": "2026-01-01"}

        with patch('catalog_cache._get_cached', return_value=malformed_wrapper):
            with pytest.raises(KeyError):
                catalog_cache.get_samples()


class TestGetStudy:
    """Tests for get_study() function."""

    def test_get_study_finds_by_study_id(self, reset_state):
        """get_study returns matching study by study_id."""
        studies = [
            {"study_id": "GSE123", "title": "ALS Study 1", "samples": 10},
            {"study_id": "GSE456", "title": "ALS Study 2", "samples": 15},
            {"study_id": "GSE789", "title": "Control Study", "samples": 5}
        ]
        catalog = {"generated_at": "2026-01-01", "studies": studies}

        with patch('catalog_cache.get_catalog', return_value=catalog):
            result = catalog_cache.get_study("GSE456")

        assert result == {"study_id": "GSE456", "title": "ALS Study 2", "samples": 15}

    def test_get_study_returns_none_not_found(self, reset_state):
        """get_study returns None when study_id not found."""
        catalog = {
            "generated_at": "2026-01-01",
            "studies": [{"study_id": "GSE123", "title": "Study"}]
        }

        with patch('catalog_cache.get_catalog', return_value=catalog):
            result = catalog_cache.get_study("NONEXISTENT")

        assert result is None

    def test_get_study_empty_studies_list(self, reset_state):
        """get_study with empty studies list returns None."""
        catalog = {"generated_at": "2026-01-01", "studies": []}

        with patch('catalog_cache.get_catalog', return_value=catalog):
            result = catalog_cache.get_study("GSE123")

        assert result is None

    def test_get_study_finds_first_match(self, reset_state):
        """get_study returns first matching study."""
        studies = [
            {"study_id": "GSE123", "version": 1},
            {"study_id": "GSE123", "version": 2}
        ]
        catalog = {"generated_at": "2026-01-01", "studies": studies}

        with patch('catalog_cache.get_catalog', return_value=catalog):
            result = catalog_cache.get_study("GSE123")

        assert result == {"study_id": "GSE123", "version": 1}

    def test_get_study_case_sensitive_match(self, reset_state):
        """get_study is case-sensitive for study_id matching."""
        catalog = {
            "generated_at": "2026-01-01",
            "studies": [{"study_id": "GSE123"}]
        }

        with patch('catalog_cache.get_catalog', return_value=catalog):
            result = catalog_cache.get_study("gse123")

        assert result is None


class TestErrorHandling:
    """Tests for error handling and exceptional cases."""

    def test_malformed_json_raises_error(self, reset_state):
        """Malformed JSON from S3 raises JSONDecodeError."""
        invalid_json = b'{invalid json'

        mock_client = MagicMock()
        mock_client.head_object.return_value = {'ETag': '"newtag"'}
        mock_client.get_object.return_value = {
            'Body': MagicMock(read=MagicMock(return_value=invalid_json))
        }

        with patch.object(catalog_cache, '_LOCAL_SOURCE', False):
            with patch.object(catalog_cache, '_BUCKET', 'bucket'):
                with patch.object(catalog_cache, '_CATALOG_KEY', 'metadata/catalog.json'):
                    with patch('catalog_cache.boto3.client', return_value=mock_client):
                        with pytest.raises(json.JSONDecodeError):
                            catalog_cache._get_cached('metadata/catalog.json', 'catalog')

    def test_s3_head_object_failure(self, reset_state):
        """S3 head_object failure propagates."""
        mock_client = MagicMock()
        mock_client.head_object.side_effect = Exception("S3 connection failed")

        with patch.object(catalog_cache, '_LOCAL_SOURCE', False):
            with patch.object(catalog_cache, '_BUCKET', 'bucket'):
                with patch.object(catalog_cache, '_CATALOG_KEY', 'metadata/catalog.json'):
                    with patch('catalog_cache.boto3.client', return_value=mock_client):
                        with pytest.raises(Exception, match="S3 connection failed"):
                            catalog_cache._get_cached('metadata/catalog.json', 'catalog')

    def test_s3_get_object_failure(self, reset_state):
        """S3 get_object failure propagates."""
        mock_client = MagicMock()
        mock_client.head_object.return_value = {'ETag': '"newtag"'}
        mock_client.get_object.side_effect = Exception("Download failed")

        with patch.object(catalog_cache, '_LOCAL_SOURCE', False):
            with patch.object(catalog_cache, '_BUCKET', 'bucket'):
                with patch.object(catalog_cache, '_CATALOG_KEY', 'metadata/catalog.json'):
                    with patch('catalog_cache.boto3.client', return_value=mock_client):
                        with pytest.raises(Exception, match="Download failed"):
                            catalog_cache._get_cached('metadata/catalog.json', 'catalog')

    def test_local_file_not_found(self, reset_state):
        """Missing local file raises FileNotFoundError."""
        mock_path = MagicMock()
        mock_path.__truediv__.return_value.read_text.side_effect = FileNotFoundError("File not found")

        with patch.object(catalog_cache, '_LOCAL_SOURCE', True):
            with patch.object(catalog_cache, '_LOCAL_DIR', mock_path):
                with pytest.raises(FileNotFoundError):
                    catalog_cache._get_cached('metadata/catalog.json', 'catalog')


class TestStateManagement:
    """Tests for module-level state persistence."""

    def test_state_persists_across_calls(self, reset_state):
        """_state dict persists values across multiple function calls."""
        mock_data = {"test": "data"}
        mock_etag = '"etag1"'

        mock_client = MagicMock()
        mock_client.head_object.return_value = {'ETag': mock_etag}
        mock_client.get_object.return_value = {
            'Body': MagicMock(read=MagicMock(return_value=json.dumps(mock_data).encode()))
        }

        with patch.object(catalog_cache, '_LOCAL_SOURCE', False):
            with patch.object(catalog_cache, '_BUCKET', 'bucket'):
                with patch.object(catalog_cache, '_CATALOG_KEY', 'metadata/catalog.json'):
                    with patch('catalog_cache.boto3.client', return_value=mock_client):
                        result1 = catalog_cache._get_cached('metadata/catalog.json', 'catalog')
                        result2 = catalog_cache._get_cached('metadata/catalog.json', 'catalog')

        assert result1 == result2 == mock_data
        assert mock_client.get_object.call_count == 1
        assert mock_client.head_object.call_count == 2

    def test_multiple_independent_caches(self, reset_state):
        """Different cache keys maintain separate state."""
        catalog_data = {"type": "catalog"}
        samples_data = {"type": "samples"}

        mock_client = MagicMock()
        mock_client.head_object.side_effect = [
            {'ETag': '"cat_etag"'},
            {'ETag': '"samp_etag"'}
        ]
        mock_client.get_object.side_effect = [
            {'Body': MagicMock(read=MagicMock(return_value=json.dumps(catalog_data).encode()))},
            {'Body': MagicMock(read=MagicMock(return_value=json.dumps(samples_data).encode()))}
        ]

        with patch.object(catalog_cache, '_LOCAL_SOURCE', False):
            with patch.object(catalog_cache, '_BUCKET', 'bucket'):
                with patch.object(catalog_cache, '_CATALOG_KEY', 'metadata/catalog.json'):
                    with patch.object(catalog_cache, '_SAMPLES_KEY', 'metadata/samples.json'):
                        with patch('catalog_cache.boto3.client', return_value=mock_client):
                            cat = catalog_cache._get_cached('metadata/catalog.json', 'catalog')
                            samp = catalog_cache._get_cached('metadata/samples.json', 'samples')

        assert cat == catalog_data
        assert samp == samples_data
        assert catalog_cache._state['catalog'] == catalog_data
        assert catalog_cache._state['samples'] == samples_data