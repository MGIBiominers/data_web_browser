import json
import pytest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock, patch, call
from datetime import datetime, timezone
import sys

# NOTE: deliberately NOT stubbing sys.modules['sources'/'catalog_schema'/'boto3']
# here. sources.py and catalog_schema.py are real, dependency-free, side-effect-free
# modules (verified by their own test files), so build_catalog imports them for
# real. Globally replacing sys.modules entries at collection time leaks across
# every other test module in the same pytest session (sys.modules is process-wide
# state) -- it previously broke test_sources.py's own `import sources` once both
# files ran in one session. Tests below that need sources/boto3 mocked do it
# per-test via @patch('build_catalog.sources') / @patch('build_catalog._live_s3_state'),
# which is properly scoped and undone after each test.
import build_catalog


class TestNowIso:
    def test_returns_iso_format_string(self):
        result = build_catalog._now_iso()
        assert isinstance(result, str)
        assert result.endswith('Z')
        assert len(result) == 20
        assert result[10] == 'T'
    
    def test_returns_valid_iso8601_format(self):
        result = build_catalog._now_iso()
        assert result.count('-') == 2
        assert result.count(':') == 2
        iso_without_z = result[:-1]
        date_part, time_part = iso_without_z.split('T')
        assert len(date_part.split('-')) == 3
        assert len(time_part.split(':')) == 3


class TestLiveS3State:
    def test_returns_empty_dict_when_bucket_is_none(self):
        result = build_catalog._live_s3_state(None, None)
        assert result == {}
    
    @patch('build_catalog.boto3')
    def test_creates_s3_client_with_correct_region(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = []
        
        build_catalog._live_s3_state('test-bucket', 'eu-west-1')
        
        mock_boto3.client.assert_called_once_with('s3', region_name='eu-west-1')
    
    @patch('build_catalog.boto3')
    def test_paginates_with_correct_prefix(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = []
        
        build_catalog._live_s3_state('bucket-name', None)
        
        mock_paginator.paginate.assert_called_once_with(Bucket='bucket-name', Prefix='processed/')
    
    @patch('build_catalog.boto3')
    def test_parses_single_s3_object_correctly(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Contents': [{'Key': 'processed/study1/file.bam', 'Size': 1024}]}
        ]
        mock_client.head_object.return_value = {'Metadata': {'sha256': 'abc123def456'}}
        
        result = build_catalog._live_s3_state('bucket', None)
        
        assert result['study1']['prefix'] == 'processed/study1/'
        assert result['study1']['files']['file.bam']['bytes'] == 1024
        assert result['study1']['files']['file.bam']['sha256'] == 'abc123def456'
    
    @patch('build_catalog.boto3')
    def test_handles_missing_sha256_metadata(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Contents': [{'Key': 'processed/study1/file.txt', 'Size': 100}]}
        ]
        mock_client.head_object.return_value = {}
        
        result = build_catalog._live_s3_state('bucket', None)
        
        assert result['study1']['files']['file.txt']['sha256'] is None
    
    @patch('build_catalog.boto3')
    def test_skips_malformed_key_with_too_few_parts(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Contents': [{'Key': 'processed/study1', 'Size': 0}]}
        ]
        
        result = build_catalog._live_s3_state('bucket', None)
        
        assert result == {}
    
    @patch('build_catalog.boto3')
    def test_skips_key_with_empty_filename(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {'Contents': [{'Key': 'processed/study1/', 'Size': 0}]}
        ]
        
        result = build_catalog._live_s3_state('bucket', None)
        
        assert result == {}
    
    @patch('build_catalog.boto3')
    def test_handles_page_without_contents_key(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {},
            {'Contents': [{'Key': 'processed/study1/file.txt', 'Size': 50}]}
        ]
        mock_client.head_object.return_value = {'Metadata': {}}
        
        result = build_catalog._live_s3_state('bucket', None)
        
        assert 'study1' in result
    
    @patch('build_catalog.boto3')
    def test_accumulates_multiple_files_per_study(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                'Contents': [
                    {'Key': 'processed/study1/file1.bam', 'Size': 100},
                    {'Key': 'processed/study1/file2.bai', 'Size': 50},
                ]
            }
        ]
        mock_client.head_object.return_value = {'Metadata': {'sha256': 'xyz'}}
        
        result = build_catalog._live_s3_state('bucket', None)
        
        assert len(result['study1']['files']) == 2
        assert 'file1.bam' in result['study1']['files']
        assert 'file2.bai' in result['study1']['files']
    
    @patch('build_catalog.boto3')
    def test_multiple_studies_with_files(self, mock_boto3):
        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client
        mock_paginator = MagicMock()
        mock_client.get_paginator.return_value = mock_paginator
        mock_paginator.paginate.return_value = [
            {
                'Contents': [
                    {'Key': 'processed/study1/file1.txt', 'Size': 100},
                    {'Key': 'processed/study2/file2.txt', 'Size': 200},
                ]
            }
        ]
        mock_client.head_object.return_value = {'Metadata': {'sha256': 'hash'}}
        
        result = build_catalog._live_s3_state('bucket', None)
        
        assert len(result) == 2
        assert 'study1' in result and 'study2' in result


class TestBuild:
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_includes_studies_missing_from_tsv_via_readme_fallback(self, mock_sources, mock_s3_state):
        # Regression test: studies.tsv (owned by download_metadata) can lag
        # behind studies/ directories it already created -- observed
        # directly against the real collection. A study dir with no tsv
        # row must still appear in the catalog, sourced from its README.
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {'in_tsv': {'title': 'From TSV'}}
        mock_sources.list_study_ids.return_value = ['in_tsv', 'dir_only']
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = []
        mock_sources.get_study_phase.return_value = (None, None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []
        mock_sources.load_readme_header.return_value = {
            'title': 'From README fallback', 'journal': 'X', 'year': '2020',
        }

        result = build_catalog.build(Path('/root'), Path('/coord'))

        by_id = {s.study_id: s for s in result.studies}
        assert set(by_id) == {'in_tsv', 'dir_only'}
        assert by_id['in_tsv'].title == 'From TSV'
        assert by_id['dir_only'].title == 'From README fallback'
        mock_sources.load_readme_header.assert_called_once_with(Path('/root'), 'dir_only')

    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_calls_live_s3_state_when_bucket_is_none(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        
        build_catalog.build(Path('/root'), Path('/coord'))
        
        mock_s3_state.assert_called_once_with(None, None)
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_calls_live_s3_state_with_bucket_and_region(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        
        build_catalog.build(Path('/root'), Path('/coord'), bucket='my-bucket', region='us-east-1')
        
        mock_s3_state.assert_called_once_with('my-bucket', 'us-east-1')
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_loads_studies_tsv_from_root(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        
        root = Path('/test/root')
        build_catalog.build(root, Path('/coord'))
        
        mock_sources.load_studies_tsv.assert_called_once_with(root)
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_loads_all_samples_from_root(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        
        root = Path('/test/root')
        build_catalog.build(root, Path('/coord'))
        
        mock_sources.load_all_samples.assert_called_once_with(root)
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_groups_samples_by_study(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {}
        all_samples = [{'study_id': 's1'}, {'study_id': 's2'}]
        mock_sources.load_all_samples.return_value = all_samples
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        
        build_catalog.build(Path('/root'), Path('/coord'))
        
        mock_sources.samples_by_study.assert_called_once_with(all_samples)
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_loads_status_json_for_all_roles(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        
        coord_root = Path('/coord')
        build_catalog.build(Path('/root'), coord_root)
        
        calls = mock_sources.load_status_json.call_args_list
        assert len(calls) == 4
        call_args = [c[0] for c in calls]
        assert (coord_root, 'download_status.json') in call_args
        assert (coord_root, 'conversion_status.json') in call_args
        assert (coord_root, 'verification_status.json') in call_args
        assert (coord_root, 'alignment_status.json') in call_args
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_returns_catalog_object(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        
        result = build_catalog.build(Path('/root'), Path('/coord'))
        
        assert result is not None
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_empty_studies_returns_valid_catalog(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        
        result = build_catalog.build(Path('/root'), Path('/coord'))
        
        assert result is not None
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_single_study_with_no_samples(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {'study1': {'title': 'Study 1'}}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = []
        mock_sources.get_study_phase.return_value = ('pending', None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []
        
        result = build_catalog.build(Path('/root'), Path('/coord'))
        
        assert result is not None
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_extracts_organisms_from_samples(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {'study1': {}}
        mock_sources.load_all_samples.return_value = []
        samples = [
            {'study_id': 'study1', 'organism': 'human'},
            {'study_id': 'study1', 'organism': 'mouse'},
            {'study_id': 'study1', 'organism': 'human'},
        ]
        mock_sources.samples_by_study.return_value = {'study1': samples}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = []
        mock_sources.get_study_phase.return_value = ('completed', None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []
        mock_sources.normalize_organism.side_effect = lambda v: v

        result = build_catalog.build(Path('/root'), Path('/coord'))

        assert result.studies[0].organisms == ['human', 'mouse']

    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_extracts_disease_statuses_and_tissues_via_canon_maps(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {'study1': {}}
        all_samples_raw = [
            {'study_id': 'study1', 'disease_status': 'Control', 'tissue_or_cell_type': 'Cerebellum; Cerebellum'},
            {'study_id': 'study1', 'disease_status': 'control', 'tissue_or_cell_type': 'motor cortex'},
        ]
        mock_sources.load_all_samples.return_value = all_samples_raw
        mock_sources.samples_by_study.return_value = {'study1': all_samples_raw}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = []
        mock_sources.get_study_phase.return_value = ('completed', None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []
        mock_sources.normalize_organism.side_effect = lambda v: v
        # Use the REAL implementations for the two canon helpers and
        # dedupe_joined -- these are exactly what's under test here, so
        # they shouldn't be mocked away.
        import sources as real_sources
        mock_sources.build_case_insensitive_canon.side_effect = real_sources.build_case_insensitive_canon
        mock_sources.dedupe_joined.side_effect = real_sources.dedupe_joined

        result = build_catalog.build(Path('/root'), Path('/coord'))

        study = result.studies[0]
        assert study.disease_statuses == ['Control']  # 'Control'/'control' merged (tie -> alphabetical)
        assert study.tissues == ['Cerebellum', 'motor cortex']  # 'Cerebellum; Cerebellum' deduped to 'Cerebellum'

    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_assay_types_case_folded_across_studies(self, mock_sources, mock_s3_state):
        """Real bug, found 2026-09-28: 'Bulk RNA-seq' (3 studies) vs
        'bulk RNA-seq' (20 studies) in the real collection -- a pure case
        duplicate that used to show up as two separate values. assay_types
        is a studies.tsv-level field (unlike disease_status/tissue, which
        are aggregated from all_samples.tsv rows), so the canon here is
        built from every study's row, not every sample."""
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {
            'study1': {'assay_types': 'Bulk RNA-seq'},
            'study2': {'assay_types': 'bulk RNA-seq'},
            'study3': {'assay_types': 'bulk RNA-seq'},
        }
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = []
        mock_sources.get_study_phase.return_value = ('completed', None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.normalize_organism.side_effect = lambda v: v
        import sources as real_sources
        mock_sources.split_multi.side_effect = real_sources.split_multi
        mock_sources.build_case_insensitive_canon.side_effect = real_sources.build_case_insensitive_canon

        result = build_catalog.build(Path('/root'), Path('/coord'))

        by_id = {s.study_id: s for s in result.studies}
        # Lowercase wins (2 occurrences vs 1) -- all three studies converge
        # on the same casing rather than showing as two distinct facet values.
        assert by_id['study1'].assay_types == ['bulk RNA-seq']
        assert by_id['study2'].assay_types == ['bulk RNA-seq']
        assert by_id['study3'].assay_types == ['bulk RNA-seq']

    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_summary_prefers_studies_tsv_column(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {
            'study1': {'summary': 'From studies.tsv'}
        }
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = []
        mock_sources.get_study_phase.return_value = (None, None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []
        mock_sources.load_readme_summary.return_value = 'From README fallback'

        result = build_catalog.build(Path('/root'), Path('/coord'))

        assert result.studies[0].summary == 'From studies.tsv'
        mock_sources.load_readme_summary.assert_not_called()

    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_summary_falls_back_to_readme_when_tsv_column_missing(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        # Realistic shape: a real csv.DictReader row always has every column
        # key present (never a bare {}), just possibly blank -- an actually
        # empty dict here would (correctly) also trigger the separate
        # "study missing from studies.tsv entirely" README-header fallback,
        # which isn't what this test is checking.
        mock_sources.load_studies_tsv.return_value = {'study1': {'journal': 'X'}}  # no 'summary' key
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = []
        mock_sources.get_study_phase.return_value = (None, None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []
        mock_sources.load_readme_summary.return_value = 'From README fallback'

        result = build_catalog.build(Path('/root'), Path('/coord'))

        assert result.studies[0].summary == 'From README fallback'
        mock_sources.load_readme_summary.assert_called_once_with(Path('/root'), 'study1')

    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_processes_local_files_without_s3_entry(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {'study1': {}}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = [
            {'name': 'output.bam', 'bytes': 1000, 'category': 'data'}
        ]
        mock_sources.get_study_phase.return_value = ('completed', None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []

        result = build_catalog.build(Path('/root'), Path('/coord'))

        pf = result.studies[0].processed_files[0]
        assert pf.name == 'output.bam'
        assert pf.sha256 is None
        assert pf.s3_key is None
        assert result.studies[0].available_externally is False

    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_matches_local_files_with_s3_files(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {
            'study1': {
                'prefix': 'processed/study1/',
                'files': {'output.bam': {'bytes': 1000, 'sha256': 'hash123'}}
            }
        }
        mock_sources.load_studies_tsv.return_value = {'study1': {}}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = [
            {'name': 'output.bam', 'bytes': 1000, 'category': 'data'}
        ]
        mock_sources.get_study_phase.return_value = ('completed', None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []

        result = build_catalog.build(Path('/root'), Path('/coord'), bucket='b')

        pf = result.studies[0].processed_files[0]
        assert pf.sha256 == 'hash123'
        assert pf.s3_key == 'processed/study1/output.bam'

    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_sets_available_externally_true_when_in_s3_state(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {
            'study1': {'prefix': 'p/', 'files': {'output.bam': {'bytes': 1, 'sha256': 'h'}}}
        }
        mock_sources.load_studies_tsv.return_value = {'study1': {}}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = [
            {'name': 'output.bam', 'bytes': 1, 'category': 'data'}
        ]
        mock_sources.get_study_phase.return_value = ('completed', None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []

        result = build_catalog.build(Path('/root'), Path('/coord'), bucket='b')

        assert result.studies[0].available_externally is True

    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_sets_available_externally_false_when_not_in_s3_state(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {'study1': {}}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = [
            {'name': 'output.bam', 'bytes': 1, 'category': 'data'}
        ]
        mock_sources.get_study_phase.return_value = ('completed', None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []

        result = build_catalog.build(Path('/root'), Path('/coord'), bucket='b')

        assert result.studies[0].available_externally is False
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_sorts_studies_alphabetically_by_id(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {
            'zebra': {},
            'apple': {},
            'middle': {},
        }
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        mock_sources.load_status_json.return_value = {}
        mock_sources.list_processed_files.return_value = []
        mock_sources.get_study_phase.return_value = ('pending', None)
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []

        result = build_catalog.build(Path('/root'), Path('/coord'))

        assert [s.study_id for s in result.studies] == ['apple', 'middle', 'zebra']
    
    @patch('build_catalog._live_s3_state')
    @patch('build_catalog.sources')
    def test_gets_study_phase_for_each_role(self, mock_sources, mock_s3_state):
        mock_s3_state.return_value = {}
        mock_sources.load_studies_tsv.return_value = {'study1': {}}
        mock_sources.load_all_samples.return_value = []
        mock_sources.samples_by_study.return_value = {}
        status_docs = {
            'download': {'study1': {'phase': 'done'}},
            'conversion': {'study1': {'phase': 'pending'}},
            'verification': {'study1': {'phase': 'failed'}},
            'alignment': {'study1': {'phase': 'queued'}},
        }
        mock_sources.load_status_json.side_effect = lambda cr, f: status_docs.get(f.split('_')[0], {})
        mock_sources.list_processed_files.return_value = []
        mock_sources.get_study_phase.return_value = ('completed', 'note')
        mock_sources.load_readme_abstract.return_value = None
        mock_sources.split_multi.return_value = []
        
        result = build_catalog.build(Path('/root'), Path('/coord'))

        expected_calls = [
            call(status_docs['download'], 'study1'),
            call(status_docs['conversion'], 'study1'),
            call(status_docs['verification'], 'study1'),
            call(status_docs['alignment'], 'study1'),
        ]
        mock_sources.get_study_phase.assert_has_calls(expected_calls, any_order=True)
        assert result.studies[0].conversion.phase == 'completed'
        assert result.studies[0].conversion.note == 'note'


class TestBuildSampleRecords:
    @patch('build_catalog.sources')
    def test_returns_list(self, mock_sources):
        mock_sources.load_all_samples.return_value = []
        
        result = build_catalog.build_sample_records(Path('/root'))
        
        assert isinstance(result, list)
    
    @patch('build_catalog.sources')
    def test_creates_record_for_each_sample(self, mock_sources):
        mock_sources.load_all_samples.return_value = [
            {'study_id': 's1'},
            {'study_id': 's2'},
            {'study_id': 's3'},
        ]
        
        result = build_catalog.build_sample_records(Path('/root'))
        
        assert len(result) == 3
    
    @patch('build_catalog.sources')
    def test_handles_empty_sample_list(self, mock_sources):
        mock_sources.load_all_samples.return_value = []
        
        result = build_catalog.build_sample_records(Path('/root'))
        
        assert result == []
    
    @patch('build_catalog.sources')
    def test_uses_default_empty_string_for_missing_study_id(self, mock_sources):
        mock_sources.load_all_samples.return_value = [{}]

        result = build_catalog.build_sample_records(Path('/root'))

        assert result[0].study_id == ''

    @patch('build_catalog.sources')
    def test_uses_none_for_optional_fields(self, mock_sources):
        mock_sources.load_all_samples.return_value = [
            {'study_id': 's1'}
        ]
        mock_sources.normalize_organism.side_effect = lambda v: v
        mock_sources.dedupe_joined.side_effect = lambda v, sep=';': v
        mock_sources.build_case_insensitive_canon.side_effect = lambda values: {}

        result = build_catalog.build_sample_records(Path('/root'))

        record = result[0]
        assert record.study_id == 's1'
        for field_name in (
            'accession', 'sample_id', 'assay_type', 'sample_source', 'organism',
            'cell_line_or_donor', 'genotype', 'disease_status', 'tissue_or_cell_type',
            'timepoint_or_age', 'treatment', 'sex', 'platform', 'batch', 'file_names',
            'is_filtered', 'source_doi_or_pmid', 'extra_disease_onset_site',
            'extra_chip_antibody',
        ):
            assert getattr(record, field_name) is None


class TestStatusFilesConstant:
    def test_status_files_has_four_entries(self):
        assert len(build_catalog.STATUS_FILES) == 4
    
    def test_status_files_has_download_role(self):
        assert 'download' in build_catalog.STATUS_FILES
        assert build_catalog.STATUS_FILES['download'] == 'download_status.json'
    
    def test_status_files_has_conversion_role(self):
        assert 'conversion' in build_catalog.STATUS_FILES
        assert build_catalog.STATUS_FILES['conversion'] == 'conversion_status.json'
    
    def test_status_files_has_verification_role(self):
        assert 'verification' in build_catalog.STATUS_FILES
        assert build_catalog.STATUS_FILES['verification'] == 'verification_status.json'
    
    def test_status_files_has_alignment_role(self):
        assert 'alignment' in build_catalog.STATUS_FILES
        assert build_catalog.STATUS_FILES['alignment'] == 'alignment_status.json'