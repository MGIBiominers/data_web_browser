import pytest
import json
import sys
from unittest.mock import Mock, patch, MagicMock, call
from io import BytesIO


@pytest.fixture(autouse=True)
def mock_external_libs():
    """Mock all external dependencies before importing the module."""
    # mcp/mcp.types are deliberately NOT stubbed here -- they're the real,
    # installed SDK, and CallToolResult/TextContent are real Pydantic models
    # whose validation we want exercised, not replaced with a MagicMock that
    # would make every result.structured_content[...] assertion below check
    # one fake against another.
    mocks = {
        'resource_links': MagicMock(),
        'catalog_cache': MagicMock(),
        'format': MagicMock(),
        's3_clients': MagicMock(),
    }

    # Save whatever was already in sys.modules (if anything) so teardown can
    # put it back exactly, rather than deleting the key outright -- another
    # test file (e.g. test_s3_clients.py) may hold a reference to the real
    # module object it imported at its own collection time, and a bare
    # `del sys.modules[name]` here would orphan that reference: anything
    # that re-resolves the module by name afterward (e.g. mock.patch's
    # dotted-path lookup) would get a fresh re-import instead of that same
    # object, silently splitting shared module state in two.
    previous = {name: sys.modules.get(name) for name in mocks}

    for name, mock in mocks.items():
        sys.modules[name] = mock

    if 'get_download_links' in sys.modules:
        del sys.modules['get_download_links']

    yield mocks

    if 'get_download_links' in sys.modules:
        del sys.modules['get_download_links']

    for name, original in previous.items():
        if original is None:
            sys.modules.pop(name, None)
        else:
            sys.modules[name] = original


@pytest.fixture
def module_under_test():
    """Import the module fresh, with mocks already in place (see
    mock_external_libs, which also clears any stale get_download_links
    import before this runs)."""
    import get_download_links as gdl
    return gdl


def test_single_study_single_file_direct_mode(module_under_test, mock_external_libs):
    """Test direct mode with single study and file."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [{
                    'name': 'data.h5ad',
                    'category': 'data',
                    's3_key': 'study1/data.h5ad',
                    'bytes': 1000,
                }]
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url1'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links(['study1'])
        
        assert result.structured_content['mode'] == 'direct'
        assert len(result.structured_content['files']) == 1
        assert result.structured_content['files'][0]['study_id'] == 'study1'
        assert result.structured_content['files'][0]['filename'] == 'data.h5ad'
        assert result.structured_content['files'][0]['format'] == 'h5ad'
        assert result.structured_content['files'][0]['bytes'] == 1000
        assert result.structured_content['excluded'] == []


def test_study_not_found(module_under_test, mock_external_libs):
    """Test excluded study when not found."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {'studies': []}
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links(['nonexistent'])
        
        assert len(result.structured_content['excluded']) == 1
        assert result.structured_content['excluded'][0]['study_id'] == 'nonexistent'
        assert result.structured_content['excluded'][0]['status'] == 'not_found'


def test_access_restricted_study(module_under_test, mock_external_libs):
    """Test excluded study when access-restricted."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'restricted_study',
                'access_restricted': True,
                'processed_files': []
            }]
        }
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links(['restricted_study'])
        
        assert len(result.structured_content['excluded']) == 1
        assert result.structured_content['excluded'][0]['study_id'] == 'restricted_study'
        assert result.structured_content['excluded'][0]['status'] == 'restricted'
        assert 'dbGaP' in result.structured_content['excluded'][0]['reason']


def test_format_filter_applied(module_under_test, mock_external_libs):
    """Test that format filter excludes unmatched formats."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [
                    {'name': 'data.h5ad', 'category': 'data', 's3_key': 'study1/data.h5ad', 'bytes': 1000},
                    {'name': 'data.csv', 'category': 'data', 's3_key': 'study1/data.csv', 'bytes': 500}
                ]
            }]
        }
        
        mock_external_libs['format'].format_label.side_effect = lambda x: 'h5ad' if 'h5ad' in x else 'csv'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links(['study1'], formats=['h5ad'])
        
        assert len(result.structured_content['files']) == 1
        assert result.structured_content['files'][0]['format'] == 'h5ad'


def test_manifest_mode_over_threshold(module_under_test, mock_external_libs):
    """Test manifest mode when files exceed threshold."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        files = [
            {'name': f'data{i}.h5ad', 'category': 'data', 's3_key': f'study/data{i}.h5ad', 'bytes': 1000}
            for i in range(10)
        ]
        
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': files
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/manifest-url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_default = Mock()
        mock_external_libs['s3_clients'].default_client.return_value = mock_default
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        with patch('get_download_links.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = 'test-uuid-123'
            result = module_under_test.get_download_links(['study1'])
        
        assert result.structured_content['mode'] == 'manifest'
        assert result.structured_content['file_count'] == 10
        assert result.structured_content['total_bytes'] == 10000
        assert 'manifest_url' in result.structured_content


def test_mixed_studies_found_restricted_notfound(module_under_test, mock_external_libs):
    """Test with mix of found, restricted, and not-found studies."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [
                {
                    'study_id': 'study1',
                    'access_restricted': False,
                    'processed_files': [{'name': 'data.h5ad', 'category': 'data', 's3_key': 'study1/data.h5ad', 'bytes': 1000}]
                },
                {
                    'study_id': 'restricted',
                    'access_restricted': True,
                    'processed_files': []
                }
            ]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links(['study1', 'restricted', 'notfound'])
        
        assert len(result.structured_content['files']) == 1
        assert len(result.structured_content['excluded']) == 2
        excluded_ids = [e['study_id'] for e in result.structured_content['excluded']]
        assert 'restricted' in excluded_ids
        assert 'notfound' in excluded_ids


def test_no_eligible_files(module_under_test, mock_external_libs):
    """Test when study has no eligible files."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [
                    {'name': 'metadata.json', 'category': 'metadata', 's3_key': 'study1/metadata.json', 'bytes': 100}
                ]
            }]
        }
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links(['study1'])
        
        assert len(result.structured_content['files']) == 0
        assert result.structured_content['mode'] == 'direct'


def test_files_without_s3_key_filtered(module_under_test, mock_external_libs):
    """Test that files without s3_key are skipped."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [
                    {'name': 'data.h5ad', 'category': 'data', 'bytes': 1000}
                ]
            }]
        }
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links(['study1'])
        
        assert len(result.structured_content['files']) == 0


def test_s3_key_removed_from_result(module_under_test, mock_external_libs):
    """Test that s3_key is popped and not in final result."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [{'name': 'data.h5ad', 'category': 'data', 's3_key': 'study1/data.h5ad', 'bytes': 1000}]
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links(['study1'])
        
        assert 's3_key' not in result.structured_content['files'][0]
        assert 'url' in result.structured_content['files'][0]


def test_presigned_url_parameters(module_under_test, mock_external_libs):
    """Test presigned URL generation uses correct parameters."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'my-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '3600',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [{'name': 'data.h5ad', 'category': 'data', 's3_key': 'path/to/file.h5ad', 'bytes': 1000}]
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        module_under_test.get_download_links(['study1'])
        
        call_args = mock_signer.generate_presigned_url.call_args_list[0]
        assert call_args[0][0] == 'get_object'
        assert call_args[1]['Params']['Bucket'] == 'my-bucket'
        assert call_args[1]['Params']['Key'] == 'path/to/file.h5ad'
        assert call_args[1]['ExpiresIn'] == 3600


def test_at_threshold_direct_mode(module_under_test, mock_external_libs):
    """Test direct mode when file count equals threshold."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        files = [
            {'name': f'data{i}.h5ad', 'category': 'data', 's3_key': f'study/data{i}.h5ad', 'bytes': 1000}
            for i in range(5)
        ]
        
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': files
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links(['study1'])
        
        assert result.structured_content['mode'] == 'direct'
        assert len(result.structured_content['files']) == 5


def test_one_over_threshold_manifest_mode(module_under_test, mock_external_libs):
    """Test manifest mode when file count exceeds threshold."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        files = [
            {'name': f'data{i}.h5ad', 'category': 'data', 's3_key': f'study/data{i}.h5ad', 'bytes': 1000}
            for i in range(6)
        ]
        
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': files
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_default = Mock()
        mock_external_libs['s3_clients'].default_client.return_value = mock_default
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        with patch('get_download_links.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = 'test-uuid'
            result = module_under_test.get_download_links(['study1'])
        
        assert result.structured_content['mode'] == 'manifest'
        assert result.structured_content['file_count'] == 6


def test_manifest_valid_json_content(module_under_test, mock_external_libs):
    """Test that manifest file contains valid JSON with correct fields."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        files = [
            {'name': f'data{i}.h5ad', 'category': 'data', 's3_key': f'study/data{i}.h5ad', 'bytes': 1000}
            for i in range(10)
        ]
        
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': files
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_default = Mock()
        mock_external_libs['s3_clients'].default_client.return_value = mock_default
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        with patch('get_download_links.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = 'test-uuid'
            module_under_test.get_download_links(['study1'])
        
        put_call = mock_default.put_object.call_args[1]
        body_str = put_call['Body'].decode('utf-8')
        manifest = json.loads(body_str)
        
        assert isinstance(manifest, list)
        assert len(manifest) == 10
        for entry in manifest:
            assert 'study_id' in entry
            assert 'filename' in entry
            assert 'format' in entry
            assert 'bytes' in entry
            assert 'url' in entry
            assert 's3_key' not in entry


def test_manifest_upload_correct_bucket_and_key(module_under_test, mock_external_libs):
    """Test manifest is uploaded with correct bucket and key."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '2',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [
                    {'name': 'data1.h5ad', 'category': 'data', 's3_key': 'study/data1.h5ad', 'bytes': 1000},
                    {'name': 'data2.h5ad', 'category': 'data', 's3_key': 'study/data2.h5ad', 'bytes': 1000},
                    {'name': 'data3.h5ad', 'category': 'data', 's3_key': 'study/data3.h5ad', 'bytes': 1000}
                ]
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_default = Mock()
        mock_external_libs['s3_clients'].default_client.return_value = mock_default
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        with patch('get_download_links.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = 'abc123'
            module_under_test.get_download_links(['study1'])
        
        put_call = mock_default.put_object.call_args[1]
        assert put_call['Bucket'] == 'test-bucket'
        assert 'manifests/abc123.json' in put_call['Key']
        assert put_call['ContentType'] == 'application/json'


def test_resource_links_format_collection(module_under_test, mock_external_libs):
    """Test that resource_links.for_formats is called with all formats present."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [
                    {'name': 'data.h5ad', 'category': 'data', 's3_key': 'study/data.h5ad', 'bytes': 1000},
                    {'name': 'data.csv', 'category': 'data', 's3_key': 'study/data.csv', 'bytes': 500},
                    {'name': 'data.zarr', 'category': 'data', 's3_key': 'study/data.zarr', 'bytes': 2000}
                ]
            }]
        }
        
        mock_external_libs['format'].format_label.side_effect = lambda x: x.split('.')[-1]
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        module_under_test.get_download_links(['study1'])
        
        called_formats = mock_external_libs['resource_links'].for_formats.call_args[0][0]
        assert 'h5ad' in called_formats
        assert 'csv' in called_formats
        assert 'zarr' in called_formats


def test_total_bytes_calculation(module_under_test, mock_external_libs):
    """Test total_bytes is correctly summed in manifest mode."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '2',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [
                    {'name': 'data1.h5ad', 'category': 'data', 's3_key': 'study/data1.h5ad', 'bytes': 1000},
                    {'name': 'data2.h5ad', 'category': 'data', 's3_key': 'study/data2.h5ad', 'bytes': 2000},
                    {'name': 'data3.h5ad', 'category': 'data', 's3_key': 'study/data3.h5ad', 'bytes': 3000}
                ]
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_default = Mock()
        mock_external_libs['s3_clients'].default_client.return_value = mock_default
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        with patch('get_download_links.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = 'uuid'
            result = module_under_test.get_download_links(['study1'])
        
        assert result.structured_content['total_bytes'] == 6000


def test_empty_study_list(module_under_test, mock_external_libs):
    """Test with empty study_ids list."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {'studies': []}
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        result = module_under_test.get_download_links([])
        
        assert result.structured_content['mode'] == 'direct'
        assert len(result.structured_content['files']) == 0
        assert len(result.structured_content['excluded']) == 0


def test_custom_threshold_env_var(module_under_test, mock_external_libs):
    """Test that custom DOWNLOAD_LINK_MANIFEST_THRESHOLD is respected."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '2',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        files = [
            {'name': f'data{i}.h5ad', 'category': 'data', 's3_key': f'study/data{i}.h5ad', 'bytes': 1000}
            for i in range(3)
        ]
        
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': files
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_default = Mock()
        mock_external_libs['s3_clients'].default_client.return_value = mock_default
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        with patch('get_download_links.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = 'uuid'
            result = module_under_test.get_download_links(['study1'])
        
        assert result.structured_content['mode'] == 'manifest'


def test_custom_presign_ttl_env_var(module_under_test, mock_external_libs):
    """Test that custom PRESIGN_TTL_SECONDS is used."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '5',
        'PRESIGN_TTL_SECONDS': '7200',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [{
                'study_id': 'study1',
                'access_restricted': False,
                'processed_files': [{'name': 'data.h5ad', 'category': 'data', 's3_key': 'study/data.h5ad', 'bytes': 1000}]
            }]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        module_under_test.get_download_links(['study1'])
        
        call_args = mock_signer.generate_presigned_url.call_args_list[0]
        assert call_args[1]['ExpiresIn'] == 7200


def test_multiple_studies_same_manifest(module_under_test, mock_external_libs):
    """Test manifest includes files from multiple studies."""
    with patch.dict('os.environ', {
        'BUCKET_NAME': 'test-bucket',
        'DOWNLOAD_LINK_MANIFEST_THRESHOLD': '2',
        'PRESIGN_TTL_SECONDS': '86400',
    }):
        mock_external_libs['catalog_cache'].get_catalog.return_value = {
            'studies': [
                {
                    'study_id': 'study1',
                    'access_restricted': False,
                    'processed_files': [
                        {'name': 'data1.h5ad', 'category': 'data', 's3_key': 'study1/data1.h5ad', 'bytes': 1000},
                        {'name': 'data2.h5ad', 'category': 'data', 's3_key': 'study1/data2.h5ad', 'bytes': 1000}
                    ]
                },
                {
                    'study_id': 'study2',
                    'access_restricted': False,
                    'processed_files': [
                        {'name': 'data3.h5ad', 'category': 'data', 's3_key': 'study2/data3.h5ad', 'bytes': 1000}
                    ]
                }
            ]
        }
        
        mock_external_libs['format'].format_label.return_value = 'h5ad'
        
        mock_signer = Mock()
        mock_signer.generate_presigned_url.return_value = 'https://s3.test/url'
        mock_external_libs['s3_clients'].presign_client.return_value = mock_signer
        
        mock_default = Mock()
        mock_external_libs['s3_clients'].default_client.return_value = mock_default
        
        mock_external_libs['resource_links'].for_formats.return_value = []
        
        with patch('get_download_links.uuid.uuid4') as mock_uuid:
            mock_uuid.return_value.hex = 'uuid'
            result = module_under_test.get_download_links(['study1', 'study2'])
        
        put_call = mock_default.put_object.call_args[1]
        body_str = put_call['Body'].decode('utf-8')
        manifest = json.loads(body_str)
        
        study_ids = {e['study_id'] for e in manifest}
        assert 'study1' in study_ids
        assert 'study2' in study_ids
        assert len(manifest) == 3