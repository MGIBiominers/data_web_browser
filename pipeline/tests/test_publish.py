import json
import pytest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch, call
import sys

# NOTE: deliberately not stubbing sys.modules for boto3/build_catalog/s3_sync/
# coordination/uuid here. build_catalog.py, s3_sync.py, and coordination.py
# are real modules in this package with their own passing test suites;
# globally replacing sys.modules entries at collection time leaks across
# every other test module in the same pytest session. Every test below
# patches what it needs per-test via `patch('publish.<name>', ...)`, which is
# properly scoped to that test and undone afterward.

import publish


class TestInvalidate:
    """Test _invalidate function."""
    
    def test_invalidate_with_boto3_available(self):
        """Should call cloudfront create_invalidation with correct params."""
        with patch('publish.boto3') as mock_boto3, \
             patch('publish.uuid') as mock_uuid:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_uuid.uuid4.return_value.hex = 'test-uuid-hex'
            
            publish._invalidate('DIST123', ['/path1/*', '/path2/*'])
            
            mock_boto3.client.assert_called_once_with('cloudfront')
            mock_client.create_invalidation.assert_called_once()
            call_kwargs = mock_client.create_invalidation.call_args[1]
            assert call_kwargs['DistributionId'] == 'DIST123'
            assert call_kwargs['InvalidationBatch']['Paths']['Items'] == ['/path1/*', '/path2/*']
            assert call_kwargs['InvalidationBatch']['Paths']['Quantity'] == 2
            assert call_kwargs['InvalidationBatch']['CallerReference'] == 'test-uuid-hex'
    
    def test_invalidate_with_empty_paths_list(self):
        """Should handle empty paths list."""
        with patch('publish.boto3') as mock_boto3, \
             patch('publish.uuid') as mock_uuid:
            mock_client = MagicMock()
            mock_boto3.client.return_value = mock_client
            mock_uuid.uuid4.return_value.hex = 'hex'
            
            publish._invalidate('DIST123', [])
            
            call_kwargs = mock_client.create_invalidation.call_args[1]
            assert call_kwargs['InvalidationBatch']['Paths']['Quantity'] == 0
            assert call_kwargs['InvalidationBatch']['Paths']['Items'] == []
    
    def test_invalidate_boto3_not_available(self):
        """Should raise RuntimeError when boto3 is None."""
        with patch('publish.boto3', None):
            with pytest.raises(RuntimeError, match="boto3 is required"):
                publish._invalidate('DIST123', ['/path/*'])


class TestRun:
    """Test run function."""
    
    def test_run_dry_run_no_boto3(self, tmp_path):
        """Dry run should not require boto3."""
        with patch('publish.boto3', None), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination') as mock_coordination:
            
            mock_s3_sync.eligible_studies.return_value = (['study1'], {'study2': 'not eligible'})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = [MagicMock(), MagicMock()]
            mock_catalog.to_dict.return_value = {'studies': []}
            mock_build_catalog.build.return_value = mock_catalog
            
            mock_sample = MagicMock()
            mock_sample.to_dict.return_value = {'id': 'sample1'}
            mock_build_catalog.build_sample_records.return_value = [mock_sample]
            
            result = publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                dry_run=True
            )
            
            assert result['eligible'] == ['study1']
            assert result['skipped'] == {'study2': 'not eligible'}
            assert result['sync_receipts'] == []
            mock_s3_sync.eligible_studies.assert_called_once()
            mock_build_catalog.build.assert_called_once()
    
    def test_run_no_boto3_without_dry_run(self, tmp_path):
        """Should raise when boto3 is None and dry_run=False."""
        with patch('publish.boto3', None), \
             patch('publish.s3_sync') as mock_s3_sync:
            
            mock_s3_sync.eligible_studies.return_value = (['study1'], {})
            
            with pytest.raises(RuntimeError, match="boto3 is required"):
                publish.run(
                    root=tmp_path / 'root',
                    coordination_root=tmp_path / 'coord',
                    bucket='test-bucket',
                    out_dir=tmp_path / 'out',
                    dry_run=False
                )
    
    def test_run_syncs_eligible_studies(self, tmp_path):
        """Should sync each eligible study."""
        with patch('publish.boto3') as mock_boto3, \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = (['study1', 'study2'], {})
            mock_s3_sync.sync_study.side_effect = [{'receipt': 1}, {'receipt': 2}]
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            mock_s3_client = MagicMock()
            mock_boto3.client.return_value = mock_s3_client
            
            result = publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                dry_run=False
            )
            
            assert mock_s3_sync.sync_study.call_count == 2
            assert result['sync_receipts'] == [{'receipt': 1}, {'receipt': 2}]
    
    def test_run_creates_output_dir(self, tmp_path):
        """Should create output directory if it doesn't exist."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            out_dir = tmp_path / 'nonexistent' / 'out'
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=out_dir,
                dry_run=True
            )
            
            assert out_dir.exists()
    
    def test_run_writes_catalog_json(self, tmp_path):
        """Should write catalog.json with correct structure."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {'test': 'catalog_data'}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            out_dir = tmp_path / 'out'
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=out_dir,
                dry_run=True
            )
            
            catalog_file = out_dir / 'catalog.json'
            assert catalog_file.exists()
            data = json.loads(catalog_file.read_text())
            assert data == {'test': 'catalog_data'}
    
    def test_run_writes_samples_json_with_generated_at(self, tmp_path):
        """Should write samples.json with generated_at timestamp."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            
            mock_sample1 = MagicMock()
            mock_sample1.to_dict.return_value = {'id': 'sample1'}
            mock_sample2 = MagicMock()
            mock_sample2.to_dict.return_value = {'id': 'sample2'}
            mock_build_catalog.build_sample_records.return_value = [mock_sample1, mock_sample2]
            
            out_dir = tmp_path / 'out'
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=out_dir,
                dry_run=True
            )
            
            samples_file = out_dir / 'samples.json'
            data = json.loads(samples_file.read_text())
            assert data['generated_at'] == '2026-09-05T12:00:00Z'
            assert len(data['samples']) == 2
            assert data['samples'][0] == {'id': 'sample1'}
            assert data['samples'][1] == {'id': 'sample2'}
    
    def test_run_writes_last_updated_json(self, tmp_path):
        """Should write last_updated.json with correct statistics."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = (['study1', 'study2'], {'study3': 'not eligible', 'study4': 'not eligible'})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            study_mocks = [MagicMock(available_externally=True) for _ in range(5)]
            study_mocks[4].available_externally = False
            mock_catalog.studies = study_mocks
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            
            mock_sample1, mock_sample2 = MagicMock(), MagicMock()
            mock_sample1.to_dict.return_value = {'id': 'sample1'}
            mock_sample2.to_dict.return_value = {'id': 'sample2'}
            mock_build_catalog.build_sample_records.return_value = [mock_sample1, mock_sample2]
            
            out_dir = tmp_path / 'out'
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=out_dir,
                dry_run=True
            )
            
            last_updated_file = out_dir / 'last_updated.json'
            data = json.loads(last_updated_file.read_text())
            assert data['timestamp'] == '2026-09-05T12:00:00Z'
            assert data['n_studies'] == 5
            assert data['n_samples'] == 2
            assert data['n_available_externally'] == 4
            assert data['studies_matched_this_run'] == ['study1', 'study2']
    
    def test_run_uploads_metadata_to_s3(self, tmp_path):
        """Should upload catalog, samples, and last_updated to S3."""
        with patch('publish.boto3') as mock_boto3, \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            mock_s3_client = MagicMock()
            mock_boto3.client.return_value = mock_s3_client
            
            out_dir = tmp_path / 'out'
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=out_dir,
                dry_run=False
            )
            
            assert mock_s3_client.upload_file.call_count == 3
            calls = mock_s3_client.upload_file.call_args_list
            # client.upload_file(Filename, Bucket, Key) -- 3 positional args
            uploaded_files = {call[0][2].split('/')[-1] for call in calls}
            assert uploaded_files == {'catalog.json', 'samples.json', 'last_updated.json'}
            for upload_call in calls:
                assert upload_call[0][1] == 'test-bucket'
                assert upload_call[0][2].startswith('metadata/')
    
    def test_run_no_s3_upload_on_dry_run(self, tmp_path):
        """Should not upload to S3 when dry_run=True."""
        with patch('publish.boto3') as mock_boto3, \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                dry_run=True
            )
            
            mock_boto3.client.assert_not_called()
    
    def test_run_invalidates_cloudfront_with_correct_paths(self, tmp_path):
        """Should invalidate CloudFront with metadata and processed paths."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'), \
             patch('publish._invalidate') as mock_invalidate:
            
            mock_s3_sync.eligible_studies.return_value = (['study1', 'study2'], {})
            mock_s3_sync.sync_study.side_effect = [{}, {}]
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                distribution_id='DIST123',
                dry_run=False
            )
            
            mock_invalidate.assert_called_once()
            dist_id, paths = mock_invalidate.call_args[0]
            assert dist_id == 'DIST123'
            assert '/metadata/*' in paths
            assert '/processed/study1/*' in paths
            assert '/processed/study2/*' in paths
    
    def test_run_no_invalidation_without_distribution_id(self, tmp_path):
        """Should not call _invalidate when distribution_id is None."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'), \
             patch('publish._invalidate') as mock_invalidate:
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                distribution_id=None,
                dry_run=False
            )
            
            mock_invalidate.assert_not_called()
    
    def test_run_records_published_action(self, tmp_path):
        """Should record 'published' action in coordination for non-dry-run."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination') as mock_coordination:
            
            mock_s3_sync.eligible_studies.return_value = (['study1', 'study2'], {'study3': 'not eligible'})
            mock_s3_sync.sync_study.side_effect = [{}, {}]
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = [
                MagicMock(available_externally=False), MagicMock(available_externally=False)
            ]
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []

            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                dry_run=False
            )

            mock_coordination.append_changelog.assert_called_once()
            call_kwargs = mock_coordination.append_changelog.call_args[1]
            assert call_kwargs['action'] == 'published'
            assert 'Synced 2 studies' in call_kwargs['note']
            assert 'skipped 1' in call_kwargs['note']
            assert '2 studies' in call_kwargs['note']
            assert '0 available externally' in call_kwargs['note']
    
    def test_run_records_dry_run_published_action(self, tmp_path):
        """Should record 'dry_run_published' action in coordination for dry-run."""
        with patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination') as mock_coordination:
            
            mock_s3_sync.eligible_studies.return_value = (['study1'], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                dry_run=True
            )
            
            mock_coordination.append_changelog.assert_called_once()
            call_kwargs = mock_coordination.append_changelog.call_args[1]
            assert call_kwargs['action'] == 'dry_run_published'
    
    def test_run_writes_status_for_eligible_studies(self, tmp_path):
        """Should update coordination status with 'published' phase for eligible studies."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination') as mock_coordination:
            
            mock_s3_sync.eligible_studies.return_value = (['study1', 'study2', 'study3'], {})
            mock_s3_sync.sync_study.side_effect = [{}, {}, {}]
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                dry_run=False
            )
            
            mock_coordination.write_status.assert_called_once()
            call_kwargs = mock_coordination.write_status.call_args[1]
            studies_dict = call_kwargs['studies']
            assert set(studies_dict.keys()) == {'study1', 'study2', 'study3'}
            for study_id in ['study1', 'study2', 'study3']:
                assert studies_dict[study_id]['phase'] == 'published'
                assert studies_dict[study_id]['note'] is None
    
    def test_run_passes_bucket_none_on_dry_run(self, tmp_path):
        """Should pass bucket=None to build_catalog on dry-run."""
        with patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                dry_run=True
            )
            
            call_kwargs = mock_build_catalog.build.call_args[1]
            assert call_kwargs['bucket'] is None
    
    def test_run_passes_bucket_to_build_catalog_on_non_dry_run(self, tmp_path):
        """Should pass actual bucket to build_catalog on non-dry-run."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='my-bucket',
                out_dir=tmp_path / 'out',
                dry_run=False
            )
            
            call_kwargs = mock_build_catalog.build.call_args[1]
            assert call_kwargs['bucket'] == 'my-bucket'
    
    def test_run_passes_region_to_boto3_client(self, tmp_path):
        """Should pass region to boto3.client calls."""
        with patch('publish.boto3') as mock_boto3, \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                region='eu-west-1',
                dry_run=False
            )
            
            calls = mock_boto3.client.call_args_list
            for call_obj in calls:
                assert call_obj[1].get('region_name') == 'eu-west-1'
    
    def test_run_passes_region_to_build_catalog(self, tmp_path):
        """Should pass region to build_catalog.build."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = ([], {})
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            mock_catalog.studies = []
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            mock_build_catalog.build_sample_records.return_value = []
            
            publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                region='ap-south-1',
                dry_run=False
            )
            
            call_kwargs = mock_build_catalog.build.call_args[1]
            assert call_kwargs['region'] == 'ap-south-1'
    
    def test_run_returns_correct_dict_structure(self, tmp_path):
        """Should return dict with eligible, skipped, sync_receipts, last_updated."""
        with patch('publish.boto3'), \
             patch('publish.s3_sync') as mock_s3_sync, \
             patch('publish.build_catalog') as mock_build_catalog, \
             patch('publish.coordination'):
            
            mock_s3_sync.eligible_studies.return_value = (['study1', 'study2'], {'study3': 'not eligible'})
            mock_s3_sync.sync_study.side_effect = [{'r': 1}, {'r': 2}]
            
            mock_catalog = MagicMock()
            mock_catalog.generated_at = '2026-09-05T12:00:00Z'
            study_mock = MagicMock(available_externally=True)
            mock_catalog.studies = [study_mock]
            mock_catalog.to_dict.return_value = {}
            mock_build_catalog.build.return_value = mock_catalog
            
            sample_mock = MagicMock()
            sample_mock.to_dict.return_value = {'id': 'sample1'}
            mock_build_catalog.build_sample_records.return_value = [sample_mock]
            
            result = publish.run(
                root=tmp_path / 'root',
                coordination_root=tmp_path / 'coord',
                bucket='test-bucket',
                out_dir=tmp_path / 'out',
                dry_run=False
            )
            
            assert 'eligible' in result
            assert 'skipped' in result
            assert 'sync_receipts' in result
            assert 'last_updated' in result
            assert result['eligible'] == ['study1', 'study2']
            assert result['skipped'] == {'study3': 'not eligible'}
            assert result['sync_receipts'] == [{'r': 1}, {'r': 2}]
            assert result['last_updated']['n_studies'] == 1
            assert result['last_updated']['n_samples'] == 1


class TestMain:
    """Test main function."""
    
    def test_main_calls_run_with_parsed_args(self, tmp_path, monkeypatch):
        """Should parse arguments and call run with correct parameters."""
        with patch('publish.run') as mock_run:
            mock_run.return_value = {
                'eligible': [],
                'skipped': [],
                'sync_receipts': [],
                'last_updated': {'n_studies': 0, 'n_available_externally': 0}
            }
            
            monkeypatch.setattr('sys.argv', [
                'publish.py',
                '--root', str(tmp_path / 'root'),
                '--coordination-root', str(tmp_path / 'coord'),
                '--bucket', 'test-bucket',
                '--region', 'us-east-1',
                '--distribution-id', 'DIST123',
                '--out-dir', str(tmp_path / 'out'),
            ])
            
            publish.main()
            
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs['bucket'] == 'test-bucket'
            assert call_kwargs['region'] == 'us-east-1'
            assert call_kwargs['distribution_id'] == 'DIST123'
            assert call_kwargs['dry_run'] is False
    
    def test_main_with_dry_run_flag(self, tmp_path, monkeypatch):
        """Should set dry_run=True when --dry-run is provided."""
        with patch('publish.run') as mock_run:
            mock_run.return_value = {
                'eligible': [],
                'skipped': [],
                'sync_receipts': [],
                'last_updated': {'n_studies': 0, 'n_available_externally': 0}
            }
            
            monkeypatch.setattr('sys.argv', [
                'publish.py',
                '--root', str(tmp_path / 'root'),
                '--coordination-root', str(tmp_path / 'coord'),
                '--bucket', 'test-bucket',
                '--out-dir', str(tmp_path / 'out'),
                '--dry-run',
            ])
            
            publish.main()
            
            assert mock_run.call_args[1]['dry_run'] is True
    
    def test_main_with_no_region(self, tmp_path, monkeypatch):
        """Should pass region=None when --region is not provided."""
        with patch('publish.run') as mock_run:
            mock_run.return_value = {
                'eligible': [],
                'skipped': [],
                'sync_receipts': [],
                'last_updated': {'n_studies': 0, 'n_available_externally': 0}
            }
            
            monkeypatch.setattr('sys.argv', [
                'publish.py',
                '--root', str(tmp_path / 'root'),
                '--coordination-root', str(tmp_path / 'coord'),
                '--bucket', 'test-bucket',
                '--out-dir', str(tmp_path / 'out'),
            ])
            
            publish.main()
            
            assert mock_run.call_args[1]['region'] is None
    
    def test_main_with_no_distribution_id(self, tmp_path, monkeypatch):
        """Should pass distribution_id=None when --distribution-id is not provided."""
        with patch('publish.run') as mock_run:
            mock_run.return_value = {
                'eligible': [],
                'skipped': [],
                'sync_receipts': [],
                'last_updated': {'n_studies': 0, 'n_available_externally': 0}
            }
            
            monkeypatch.setattr('sys.argv', [
                'publish.py',
                '--root', str(tmp_path / 'root'),
                '--coordination-root', str(tmp_path / 'coord'),
                '--bucket', 'test-bucket',
                '--out-dir', str(tmp_path / 'out'),
            ])
            
            publish.main()
            
            assert mock_run.call_args[1]['distribution_id'] is None
    
    def test_main_prints_summary(self, tmp_path, capsys, monkeypatch):
        """Should print eligible, skipped, and catalog statistics."""
        with patch('publish.run') as mock_run:
            mock_run.return_value = {
                'eligible': ['s1', 's2'],
                'skipped': ['s3'],
                'sync_receipts': [{}, {}],
                'last_updated': {
                    'n_studies': 10,
                    'n_available_externally': 6,
                }
            }
            
            monkeypatch.setattr('sys.argv', [
                'publish.py',
                '--root', str(tmp_path / 'root'),
                '--coordination-root', str(tmp_path / 'coord'),
                '--bucket', 'test-bucket',
                '--out-dir', str(tmp_path / 'out'),
            ])
            
            publish.main()
            
            captured = capsys.readouterr()
            assert 'Eligible: 2, skipped: 1' in captured.out
            assert '10 studies' in captured.out
            assert '6 available externally' in captured.out
    
    def test_main_prints_dry_run_notice(self, tmp_path, capsys, monkeypatch):
        """Should print dry-run notice when --dry-run is used."""
        with patch('publish.run') as mock_run:
            mock_run.return_value = {
                'eligible': [],
                'skipped': [],
                'sync_receipts': [],
                'last_updated': {'n_studies': 0, 'n_available_externally': 0}
            }
            
            monkeypatch.setattr('sys.argv', [
                'publish.py',
                '--root', str(tmp_path / 'root'),
                '--coordination-root', str(tmp_path / 'coord'),
                '--bucket', 'test-bucket',
                '--out-dir', str(tmp_path / 'out'),
                '--dry-run',
            ])
            
            publish.main()
            
            captured = capsys.readouterr()
            assert '[dry-run]' in captured.out
            assert 'no S3 writes or CloudFront invalidation' in captured.out
    
    def test_main_no_dry_run_notice_without_dry_run(self, tmp_path, capsys, monkeypatch):
        """Should not print dry-run notice when --dry-run is not used."""
        with patch('publish.run') as mock_run:
            mock_run.return_value = {
                'eligible': [],
                'skipped': [],
                'sync_receipts': [],
                'last_updated': {'n_studies': 0, 'n_available_externally': 0}
            }
            
            monkeypatch.setattr('sys.argv', [
                'publish.py',
                '--root', str(tmp_path / 'root'),
                '--coordination-root', str(tmp_path / 'coord'),
                '--bucket', 'test-bucket',
                '--out-dir', str(tmp_path / 'out'),
            ])
            
            publish.main()
            
            captured = capsys.readouterr()
            assert '[dry-run]' not in captured.out