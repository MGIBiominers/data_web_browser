import pytest
from unittest.mock import Mock, patch, MagicMock

from mcp.types import ResourceLink


@pytest.fixture
def mock_samples():
    """Fixture providing mock sample data."""
    return [
        {
            "study_id": "study1",
            "disease_status": "ALS",
            "sex": "male",
            "tissue_or_cell_type": "motor cortex",
            "treatment": "none",
            "platform": "Illumina NovaSeq",
            "sample_id": "sample1",
        },
        {
            "study_id": "study1",
            "disease_status": "ALS",
            "sex": "female",
            "tissue_or_cell_type": "spinal cord",
            "treatment": "none",
            "platform": "Illumina NovaSeq",
            "sample_id": "sample2",
        },
        {
            "study_id": "study2",
            "disease_status": "Control",
            "sex": "male",
            "tissue_or_cell_type": "motor cortex",
            "treatment": "none",
            "platform": "10x Genomics",
            "sample_id": "sample3",
        },
        {
            "study_id": "study2",
            "disease_status": "ALS",
            "sex": "female",
            "tissue_or_cell_type": "motor cortex",
            "treatment": "Rotenone",
            "platform": "Illumina NovaSeq",
            "sample_id": "sample4",
        },
        {
            "study_id": "study3",
            "disease_status": "Control",
            "sex": "female",
            "tissue_or_cell_type": "spinal cord",
            "treatment": "none",
            "platform": "10x Genomics",
            "sample_id": "sample5",
        },
    ]


@pytest.fixture
def mock_link():
    """Fixture for a resource link -- a real ResourceLink, not a MagicMock,
    since CallToolResult's `content` field is Pydantic-validated against the
    real content-block union types."""
    return ResourceLink(
        type="resource_link", uri="pipeline-docs://sample_metadata_schema",
        name="sample_metadata_schema", description="test", mime_type="text/markdown",
    )


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_no_filters_returns_all_samples(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test search with no filters returns all samples."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples()
    
    assert result.structured_content["total_matches"] == 5
    assert result.structured_content["truncated"] is False
    assert len(result.structured_content["samples"]) == 5
    assert result.structured_content["samples"] == mock_samples


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_disease_status_filter(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test filtering by disease_status."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(disease_status="ALS")
    
    assert result.structured_content["total_matches"] == 3
    assert result.structured_content["truncated"] is False
    assert all(s["disease_status"] == "ALS" for s in result.structured_content["samples"])


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_sex_filter(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test filtering by sex."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(sex="female")
    
    assert result.structured_content["total_matches"] == 3
    assert result.structured_content["truncated"] is False
    assert all(s["sex"] == "female" for s in result.structured_content["samples"])


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_tissue_filter(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test filtering by tissue."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(tissue="motor cortex")
    
    assert result.structured_content["total_matches"] == 3
    assert all(s["tissue_or_cell_type"] == "motor cortex" for s in result.structured_content["samples"])


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_treatment_filter(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test filtering by treatment."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(treatment="Rotenone")
    
    assert result.structured_content["total_matches"] == 1
    assert result.structured_content["samples"][0]["treatment"] == "Rotenone"


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_platform_filter(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test filtering by platform."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(platform="10x Genomics")
    
    assert result.structured_content["total_matches"] == 2
    assert all(s["platform"] == "10x Genomics" for s in result.structured_content["samples"])


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_study_id_filter(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test filtering by study_id."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(study_id="study1")
    
    assert result.structured_content["total_matches"] == 2
    assert all(s["study_id"] == "study1" for s in result.structured_content["samples"])


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_multiple_filters_combined(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test filtering with multiple criteria."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(disease_status="ALS", sex="female", tissue="motor cortex")
    
    assert result.structured_content["total_matches"] == 1
    assert result.structured_content["samples"][0]["sample_id"] == "sample4"


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_all_filters_specified(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test with all filter parameters specified."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(
        disease_status="ALS",
        sex="female",
        tissue="motor cortex",
        treatment="Rotenone",
        platform="Illumina NovaSeq",
        study_id="study2",
    )
    
    assert result.structured_content["total_matches"] == 1
    assert result.structured_content["samples"][0]["sample_id"] == "sample4"


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_no_matches_found(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test search that returns no results."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(disease_status="NonexistentDisease")
    
    assert result.structured_content["total_matches"] == 0
    assert result.structured_content["truncated"] is False
    assert result.structured_content["samples"] == []


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_truncation_at_sample_result_cap(mock_get_samples, mock_link_func, mock_link):
    """Test that results are truncated at SAMPLE_RESULT_CAP."""
    from search_samples import search_samples, SAMPLE_RESULT_CAP
    
    large_sample_set = [
        {
            "study_id": f"study{i}",
            "disease_status": "ALS",
            "sex": "male",
            "tissue_or_cell_type": "motor cortex",
            "treatment": "none",
            "platform": "Illumina NovaSeq",
            "sample_id": f"sample{i}",
        }
        for i in range(60)
    ]
    mock_get_samples.return_value = large_sample_set
    mock_link_func.return_value = mock_link
    
    result = search_samples(disease_status="ALS")
    
    assert result.structured_content["total_matches"] == 60
    assert result.structured_content["truncated"] is True
    assert len(result.structured_content["samples"]) == SAMPLE_RESULT_CAP
    assert len(result.structured_content["samples"]) == 50


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_no_truncation_at_cap_boundary(mock_get_samples, mock_link_func, mock_link):
    """Test that truncation flag is False when exactly at cap."""
    from search_samples import search_samples, SAMPLE_RESULT_CAP
    
    samples_at_cap = [
        {
            "study_id": f"study{i}",
            "disease_status": "ALS",
            "sample_id": f"sample{i}",
        }
        for i in range(SAMPLE_RESULT_CAP)
    ]
    mock_get_samples.return_value = samples_at_cap
    mock_link_func.return_value = mock_link
    
    result = search_samples()
    
    assert result.structured_content["total_matches"] == 50
    assert result.structured_content["truncated"] is False
    assert len(result.structured_content["samples"]) == 50


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_empty_catalog(mock_get_samples, mock_link_func, mock_link):
    """Test search when catalog is empty."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = []
    mock_link_func.return_value = mock_link
    
    result = search_samples()
    
    assert result.structured_content["total_matches"] == 0
    assert result.structured_content["truncated"] is False
    assert result.structured_content["samples"] == []


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_result_contains_summary_text(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test that result contains summary text in content."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(disease_status="ALS")
    
    assert len(result.content) >= 1
    assert result.content[0].type == "text"
    assert "Found 3 matching sample(s)" in result.content[0].text


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_summary_text_plural_single(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test summary text for single match."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(treatment="Rotenone")
    
    assert "Found 1 matching sample(s)" in result.content[0].text


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_resource_link_included(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test that resource link is included in content."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples()
    
    mock_link_func.assert_called_once()
    assert mock_link in result.content


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_missing_optional_fields_in_samples(mock_get_samples, mock_link_func, mock_link):
    """Test filtering when samples have missing optional fields."""
    from search_samples import search_samples
    
    samples_with_missing = [
        {
            "study_id": "study1",
            "disease_status": "ALS",
            "sample_id": "sample1",
        },
        {
            "study_id": "study2",
            "disease_status": "ALS",
            "sex": "female",
            "tissue_or_cell_type": "motor cortex",
            "treatment": "none",
            "platform": "10x Genomics",
            "sample_id": "sample2",
        },
    ]
    mock_get_samples.return_value = samples_with_missing
    mock_link_func.return_value = mock_link
    
    result = search_samples(tissue="motor cortex")
    
    assert result.structured_content["total_matches"] == 1
    assert result.structured_content["samples"][0]["sample_id"] == "sample2"


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_case_sensitive_exact_match(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test that filtering is case-sensitive."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples(disease_status="als")
    
    assert result.structured_content["total_matches"] == 0
    
    result = search_samples(disease_status="ALS")
    
    assert result.structured_content["total_matches"] == 3


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_filter_with_none_value(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test that None filter values are ignored."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result_none = search_samples(disease_status=None, sex="male")
    result_explicit = search_samples(sex="male")
    
    assert result_none.structured_content["total_matches"] == result_explicit.structured_content["total_matches"]
    assert len(result_none.structured_content["samples"]) == len(result_explicit.structured_content["samples"])


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_structured_content_structure(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test that structured content has expected keys."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples()
    
    assert "total_matches" in result.structured_content
    assert "truncated" in result.structured_content
    assert "samples" in result.structured_content
    assert isinstance(result.structured_content["total_matches"], int)
    assert isinstance(result.structured_content["truncated"], bool)
    assert isinstance(result.structured_content["samples"], list)


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_samples_order_preserved(mock_get_samples, mock_link_func, mock_samples, mock_link):
    """Test that sample order from catalog is preserved in results."""
    from search_samples import search_samples
    
    mock_get_samples.return_value = mock_samples
    mock_link_func.return_value = mock_link
    
    result = search_samples()
    
    for i, sample in enumerate(result.structured_content["samples"]):
        assert sample["sample_id"] == f"sample{i+1}"


@patch("search_samples.rl.sample_metadata_link")
@patch("search_samples.get_samples")
def test_samples_list_sliced_correctly(mock_get_samples, mock_link_func, mock_link):
    """Test that samples list is sliced to cap even when truncated."""
    from search_samples import search_samples, SAMPLE_RESULT_CAP
    
    large_sample_set = [
        {
            "study_id": "study",
            "disease_status": "ALS",
            "sample_id": f"sample{i}",
        }
        for i in range(100)
    ]
    mock_get_samples.return_value = large_sample_set
    mock_link_func.return_value = mock_link
    
    result = search_samples()
    
    assert len(result.structured_content["samples"]) == SAMPLE_RESULT_CAP
    assert result.structured_content["samples"][-1]["sample_id"] == f"sample{SAMPLE_RESULT_CAP - 1}"