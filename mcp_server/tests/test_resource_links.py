import pytest
from mcp.types import ResourceLink

from resource_links import for_formats, sample_metadata_link, _link, _FORMAT_RESOURCES, SAMPLE_METADATA


class TestForFormats:
    def test_empty_list_returns_empty_list(self):
        result = for_formats([])
        assert result == []
    
    def test_single_valid_format(self):
        result = for_formats(["h5ad"])
        assert len(result) == 1
        assert result[0].uri == "pipeline-docs://h5ad_schema"
        assert result[0].name == "h5ad_schema"
        assert result[0].description == "h5ad/h5mu file structure reference"
    
    def test_multiple_formats_deduplicates_by_uri(self):
        result = for_formats(["h5ad", "parquet", "csv"])
        assert len(result) == 2
        uris = {r.uri for r in result}
        assert "pipeline-docs://h5ad_schema" in uris
        assert "pipeline-docs://bulk_rnaseq_schema" in uris
    
    def test_invalid_format_ignored(self):
        result = for_formats(["unknown_format"])
        assert result == []
    
    def test_duplicate_formats_deduped(self):
        result = for_formats(["h5ad", "h5ad", "h5ad"])
        assert len(result) == 1
    
    def test_formats_mapping_same_uri_deduped(self):
        result = for_formats(["parquet", "tsv", "csv"])
        assert len(result) == 1
        assert result[0].uri == "pipeline-docs://bulk_rnaseq_schema"
    
    def test_mixed_valid_invalid_formats(self):
        result = for_formats(["h5ad", "invalid", "parquet", "unknown"])
        assert len(result) == 2
        uris = {r.uri for r in result}
        assert len(uris) == 2
    
    def test_returns_list(self):
        result = for_formats(["h5ad"])
        assert isinstance(result, list)
    
    def test_resource_links_have_correct_attributes(self):
        result = for_formats(["h5ad"])
        link = result[0]
        assert hasattr(link, 'type')
        assert hasattr(link, 'uri')
        assert hasattr(link, 'name')
        assert hasattr(link, 'description')
        assert hasattr(link, "mime_type")
        assert link.type == "resource_link"
        assert link.mime_type == "text/markdown"
    
    def test_h5ad_h5mu_map_to_same_resource(self):
        h5ad = for_formats(["h5ad"])
        h5mu = for_formats(["h5mu"])
        assert h5ad[0].uri == h5mu[0].uri
        assert h5ad[0].name == h5mu[0].name
    
    def test_format_list_order_does_not_affect_dedup(self):
        result1 = for_formats(["h5ad", "parquet"])
        result2 = for_formats(["parquet", "h5ad"])
        assert len(result1) == len(result2)
        uris1 = {r.uri for r in result1}
        uris2 = {r.uri for r in result2}
        assert uris1 == uris2


class TestSampleMetadataLink:
    def test_returns_resource_link(self):
        result = sample_metadata_link()
        assert result is not None
        assert isinstance(result, ResourceLink)
    
    def test_correct_uri(self):
        result = sample_metadata_link()
        assert result.uri == "pipeline-docs://sample_metadata_schema"
    
    def test_correct_name(self):
        result = sample_metadata_link()
        assert result.name == "sample_metadata_schema"
    
    def test_correct_description(self):
        result = sample_metadata_link()
        assert result.description == "Normalized sample metadata field reference"
    
    def test_correct_type(self):
        result = sample_metadata_link()
        assert result.type == "resource_link"
    
    def test_correct_mimetype(self):
        result = sample_metadata_link()
        assert result.mime_type == "text/markdown"


class TestLink:
    def test_creates_resource_link(self):
        result = _link("pipeline-docs://test", "Test description")
        assert isinstance(result, ResourceLink)
    
    def test_sets_type(self):
        result = _link("pipeline-docs://test", "Test description")
        assert result.type == "resource_link"
    
    def test_sets_uri(self):
        result = _link("pipeline-docs://test", "Test description")
        assert result.uri == "pipeline-docs://test"
    
    def test_sets_description(self):
        result = _link("pipeline-docs://test", "My description")
        assert result.description == "My description"
    
    def test_sets_mimetype(self):
        result = _link("pipeline-docs://test", "Test description")
        assert result.mime_type == "text/markdown"
    
    def test_extracts_name_from_uri_with_scheme(self):
        result = _link("pipeline-docs://test_resource", "Test")
        assert result.name == "test_resource"
    
    def test_extracts_name_from_uri_complex(self):
        result = _link("prefix://complex_name_123_end", "Test")
        assert result.name == "complex_name_123_end"
    
    def test_name_extraction_with_multiple_separators(self):
        result = _link("scheme://name/with/slashes", "Test")
        assert result.name == "name/with/slashes"
    
class TestFormatResourcesMapping:
    def test_contains_expected_formats(self):
        expected = {"h5ad", "h5mu", "parquet", "tsv", "csv"}
        assert set(_FORMAT_RESOURCES.keys()) == expected
    
    def test_all_values_are_tuples(self):
        for fmt, entry in _FORMAT_RESOURCES.items():
            assert isinstance(entry, tuple)
            assert len(entry) == 2
    
    def test_all_entries_have_string_uri(self):
        for fmt, (uri, desc) in _FORMAT_RESOURCES.items():
            assert isinstance(uri, str)
    
    def test_all_entries_have_string_description(self):
        for fmt, (uri, desc) in _FORMAT_RESOURCES.items():
            assert isinstance(desc, str)
    
    def test_h5ad_mapping(self):
        uri, desc = _FORMAT_RESOURCES["h5ad"]
        assert uri == "pipeline-docs://h5ad_schema"
        assert "h5ad" in desc.lower()
    
    def test_h5mu_mapping(self):
        uri, desc = _FORMAT_RESOURCES["h5mu"]
        assert uri == "pipeline-docs://h5ad_schema"
    
    def test_parquet_mapping(self):
        uri, desc = _FORMAT_RESOURCES["parquet"]
        assert uri == "pipeline-docs://bulk_rnaseq_schema"
    
    def test_tsv_maps_to_bulk_rnaseq(self):
        uri, desc = _FORMAT_RESOURCES["tsv"]
        assert uri == "pipeline-docs://bulk_rnaseq_schema"
    
    def test_csv_maps_to_bulk_rnaseq(self):
        uri, desc = _FORMAT_RESOURCES["csv"]
        assert uri == "pipeline-docs://bulk_rnaseq_schema"


class TestSampleMetadataConstant:
    def test_is_tuple(self):
        assert isinstance(SAMPLE_METADATA, tuple)
    
    def test_has_two_elements(self):
        assert len(SAMPLE_METADATA) == 2
    
    def test_first_element_is_uri(self):
        assert SAMPLE_METADATA[0] == "pipeline-docs://sample_metadata_schema"
    
    def test_second_element_is_description(self):
        assert SAMPLE_METADATA[1] == "Normalized sample metadata field reference"