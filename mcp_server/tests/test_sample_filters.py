import pytest
from unittest import mock
from sample_filters import _norm, matches


class TestNorm:
    """Test the _norm normalization function."""

    def test_norm_strips_and_lowercases_normal_string(self):
        """String with content should be stripped and lowercased."""
        assert _norm("Hello World") == "hello world"

    def test_norm_strips_leading_whitespace(self):
        """Leading whitespace should be stripped."""
        assert _norm("  hello") == "hello"

    def test_norm_strips_trailing_whitespace(self):
        """Trailing whitespace should be stripped."""
        assert _norm("hello  ") == "hello"

    def test_norm_strips_both_leading_and_trailing_whitespace(self):
        """Both leading and trailing whitespace should be stripped."""
        assert _norm("  hello  ") == "hello"

    def test_norm_strips_tabs_and_newlines(self):
        """Tabs and newlines should be stripped."""
        assert _norm("\thello\n") == "hello"

    def test_norm_lowercases_mixed_case(self):
        """Mixed case should be lowercased."""
        assert _norm("HeLLo WoRLd") == "hello world"

    def test_norm_lowercases_all_caps(self):
        """All caps should be lowercased."""
        assert _norm("HELLO") == "hello"

    def test_norm_empty_string_returns_none(self):
        """Empty string should return None."""
        assert _norm("") is None

    def test_norm_whitespace_only_string_returns_none(self):
        """String with only whitespace should return None."""
        assert _norm("   ") is None

    def test_norm_whitespace_only_mixed_returns_none(self):
        """String with tabs, spaces, and newlines only should return None."""
        assert _norm(" \t \n ") is None

    def test_norm_none_returns_none(self):
        """None input should return None."""
        assert _norm(None) is None

    def test_norm_int_returns_none(self):
        """Integer should return None."""
        assert _norm(42) is None

    def test_norm_float_returns_none(self):
        """Float should return None."""
        assert _norm(3.14) is None

    def test_norm_list_returns_none(self):
        """List should return None."""
        assert _norm([1, 2, 3]) is None

    def test_norm_dict_returns_none(self):
        """Dict should return None."""
        assert _norm({"key": "value"}) is None

    def test_norm_bool_returns_none(self):
        """Boolean should return None."""
        assert _norm(True) is None
        assert _norm(False) is None

    def test_norm_preserves_internal_whitespace(self):
        """Internal whitespace should be preserved (not stripped)."""
        assert _norm("hello world") == "hello world"

    def test_norm_handles_special_characters(self):
        """Special characters should be preserved."""
        assert _norm("hello-world") == "hello-world"

    def test_norm_handles_parentheses(self):
        """Parentheses should be preserved."""
        assert _norm("Motor Cortex (BA4)") == "motor cortex (ba4)"

    def test_norm_handles_numbers(self):
        """Numbers should be preserved."""
        assert _norm("iPSC-123") == "ipsc-123"

    def test_norm_handles_semicolons(self):
        """Semicolons should be preserved."""
        assert _norm("post-mortem; tissue") == "post-mortem; tissue"

    def test_norm_unicode_characters(self):
        """Unicode characters should be handled."""
        result = _norm("Café")
        assert isinstance(result, str)
        assert result == "café"


class TestMatches:
    """Test the matches function."""

    # Tests for None query
    def test_matches_none_query_returns_true(self):
        """None query should always return True."""
        sample = {"field": "anything"}
        assert matches(sample, None, "field") is True

    def test_matches_none_query_returns_true_even_if_field_missing(self):
        """None query should return True even if field is missing."""
        sample = {}
        assert matches(sample, None, "field") is True

    # Tests for empty string query
    def test_matches_empty_query_returns_true(self):
        """Empty string query should always return True."""
        sample = {"field": "anything"}
        assert matches(sample, "", "field") is True

    def test_matches_empty_query_with_missing_field_returns_true(self):
        """Empty string query should return True even if field is missing."""
        sample = {}
        assert matches(sample, "", "field") is True

    def test_matches_whitespace_only_query_returns_true(self):
        """Query with only whitespace should return True (treated as empty)."""
        sample = {"field": "value"}
        assert matches(sample, "   ", "field") is True

    def test_matches_tab_only_query_returns_true(self):
        """Query with only tabs should return True (treated as empty)."""
        sample = {"field": "value"}
        assert matches(sample, "\t", "field") is True

    # Tests for exact matching with single field
    def test_matches_exact_match_lowercase(self):
        """Exact lowercase match should return True."""
        sample = {"field": "hello"}
        assert matches(sample, "hello", "field") is True

    def test_matches_exact_match_case_insensitive_query_uppercase(self):
        """Case-insensitive match with uppercase query."""
        sample = {"field": "hello"}
        assert matches(sample, "HELLO", "field") is True

    def test_matches_exact_match_case_insensitive_value_uppercase(self):
        """Case-insensitive match with uppercase value."""
        sample = {"field": "HELLO"}
        assert matches(sample, "hello", "field") is True

    def test_matches_exact_match_mixed_case(self):
        """Case-insensitive match with mixed case."""
        sample = {"field": "HeLLo"}
        assert matches(sample, "hELlo", "field") is True

    def test_matches_no_match_different_values(self):
        """Different values should return False."""
        sample = {"field": "hello"}
        assert matches(sample, "world", "field") is False

    def test_matches_no_match_partial_string(self):
        """Partial string match should return False (requires exact match)."""
        sample = {"field": "hello world"}
        assert matches(sample, "hello", "field") is False

    def test_matches_no_match_substring(self):
        """Substring should not match."""
        sample = {"field": "hello"}
        assert matches(sample, "ell", "field") is False

    # Tests with whitespace in field and query
    def test_matches_strips_whitespace_from_query(self):
        """Whitespace in query should be stripped."""
        sample = {"field": "hello"}
        assert matches(sample, "  hello  ", "field") is True

    def test_matches_strips_whitespace_from_field_value(self):
        """Whitespace in field value should be stripped."""
        sample = {"field": "  hello  "}
        assert matches(sample, "hello", "field") is True

    def test_matches_strips_whitespace_from_both(self):
        """Whitespace in both query and field should be stripped."""
        sample = {"field": "  hello  "}
        assert matches(sample, "  hello  ", "field") is True

    def test_matches_field_with_internal_whitespace(self):
        """Internal whitespace in field and query should match."""
        sample = {"field": "hello world"}
        assert matches(sample, "hello world", "field") is True

    # Tests with missing fields
    def test_matches_missing_field_returns_false(self):
        """Missing field should return False."""
        sample = {}
        assert matches(sample, "query", "field") is False

    def test_matches_field_value_is_none_returns_false(self):
        """Field with None value should return False."""
        sample = {"field": None}
        assert matches(sample, "query", "field") is False

    def test_matches_field_value_is_empty_string_returns_false(self):
        """Field with empty string value should return False."""
        sample = {"field": ""}
        assert matches(sample, "query", "field") is False

    def test_matches_field_value_is_whitespace_only_returns_false(self):
        """Field with whitespace-only value should return False."""
        sample = {"field": "   "}
        assert matches(sample, "query", "field") is False

    # Tests with fallback field
    def test_matches_fallback_field_used_when_primary_missing(self):
        """Fallback field should be used when primary field is missing."""
        sample = {"fallback": "hello"}
        assert matches(sample, "hello", "field", "fallback") is True

    def test_matches_fallback_field_used_when_primary_none(self):
        """Fallback field should be used when primary field is None."""
        sample = {"field": None, "fallback": "hello"}
        assert matches(sample, "hello", "field", "fallback") is True

    def test_matches_fallback_field_used_when_primary_empty(self):
        """Fallback field should be used when primary field is empty."""
        sample = {"field": "", "fallback": "hello"}
        assert matches(sample, "hello", "field", "fallback") is True

    def test_matches_fallback_field_used_when_primary_whitespace(self):
        """Fallback field should be used when primary field is whitespace-only."""
        sample = {"field": "   ", "fallback": "hello"}
        assert matches(sample, "hello", "field", "fallback") is True

    def test_matches_primary_field_preferred_over_fallback(self):
        """Primary field should be preferred over fallback when both exist."""
        sample = {"field": "primary", "fallback": "fallback"}
        assert matches(sample, "primary", "field", "fallback") is True
        assert matches(sample, "fallback", "field", "fallback") is False

    def test_matches_fallback_does_not_match(self):
        """Non-matching fallback should return False."""
        sample = {"fallback": "hello"}
        assert matches(sample, "world", "field", "fallback") is False

    def test_matches_both_field_and_fallback_missing(self):
        """Both field and fallback missing should return False."""
        sample = {}
        assert matches(sample, "query", "field", "fallback") is False

    def test_matches_fallback_none_in_params(self):
        """Explicit None fallback_field should not use fallback."""
        sample = {"field": None, "fallback": "hello"}
        assert matches(sample, "hello", "field", None) is False

    def test_matches_fallback_whitespace_only(self):
        """Fallback with whitespace-only value should not match."""
        sample = {"field": None, "fallback": "   "}
        assert matches(sample, "query", "field", "fallback") is False

    # Tests with non-string field values
    def test_matches_field_value_is_int_returns_false(self):
        """Integer field value should return False."""
        sample = {"field": 42}
        assert matches(sample, "42", "field") is False

    def test_matches_field_value_is_float_returns_false(self):
        """Float field value should return False."""
        sample = {"field": 3.14}
        assert matches(sample, "3.14", "field") is False

    def test_matches_field_value_is_list_returns_false(self):
        """List field value should return False."""
        sample = {"field": ["hello"]}
        assert matches(sample, "hello", "field") is False

    def test_matches_field_value_is_dict_returns_false(self):
        """Dict field value should return False."""
        sample = {"field": {"key": "hello"}}
        assert matches(sample, "hello", "field") is False

    def test_matches_field_value_is_bool_returns_false(self):
        """Boolean field value should return False."""
        sample = {"field": True}
        assert matches(sample, "true", "field") is False

    # Tests for the specific use cases mentioned in the docstring
    def test_matches_sex_field_case_sensitivity_male(self):
        """Test sex field case-insensitive matching for 'male' variants."""
        sample1 = {"sex": "Male"}
        sample2 = {"sex": "male"}
        sample3 = {"sex": "MALE"}
        
        assert matches(sample1, "male", "sex") is True
        assert matches(sample2, "male", "sex") is True
        assert matches(sample3, "male", "sex") is True

    def test_matches_sex_field_case_sensitivity_female(self):
        """Test sex field case-insensitive matching for 'female' variants."""
        sample1 = {"sex": "Female"}
        sample2 = {"sex": "female"}
        sample3 = {"sex": "FEMALE"}
        
        assert matches(sample1, "female", "sex") is True
        assert matches(sample2, "female", "sex") is True
        assert matches(sample3, "female", "sex") is True

    def test_matches_tissue_with_canonical_column(self):
        """Test tissue field with canonical vocabulary column."""
        sample = {"tissue": "Motor Cortex (BA4)", "tissue_raw": "Cortex_Motor_BA4"}
        assert matches(sample, "motor cortex (ba4)", "tissue") is True

    def test_matches_tissue_canonical_preferred_over_raw(self):
        """Test that canonical tissue is preferred over raw tissue."""
        sample = {"tissue": "Motor Cortex (BA4)", "tissue_raw": "Cortex_Motor_BA4"}
        assert matches(sample, "motor cortex (ba4)", "tissue", "tissue_raw") is True
        assert matches(sample, "cortex_motor_ba4", "tissue", "tissue_raw") is False

    def test_matches_tissue_fallback_when_canonical_empty(self):
        """Test tissue fallback when canonical is empty (cell culture case)."""
        sample = {"tissue": "", "tissue_raw": "iPSC-derived motor neuron cultures"}
        assert matches(sample, "ipsc-derived motor neuron cultures", "tissue", "tissue_raw") is True

    def test_matches_tissue_fallback_when_canonical_none(self):
        """Test tissue fallback when canonical is None (cell culture case)."""
        sample = {"tissue": None, "tissue_raw": "iPSC-derived motor neuron cultures"}
        assert matches(sample, "ipsc-derived motor neuron cultures", "tissue", "tissue_raw") is True

    def test_matches_complex_tissue_variants(self):
        """Test matching complex tissue variants with special characters."""
        sample = {
            "tissue": None,
            "tissue_raw": "post-mortem tissue; Motor Cortex (Lateral)"
        }
        result = matches(sample, "post-mortem tissue; motor cortex (lateral)", "tissue", "tissue_raw")
        assert result is True

    def test_matches_tissue_lateral_variant(self):
        """Test matching lateral motor cortex variant."""
        sample = {"tissue": "Motor Cortex (Lateral)", "tissue_raw": "lateral motor cortex"}
        assert matches(sample, "motor cortex (lateral)", "tissue", "tissue_raw") is True

    def test_matches_tissue_motor_cortex_spelling_variants(self):
        """Test multiple raw spelling variants collapse to canonical."""
        samples = [
            {"tissue": "Motor Cortex (BA4)", "tissue_raw": "motor cortex"},
            {"tissue": "Motor Cortex (BA4)", "tissue_raw": "lateral motor cortex"},
            {"tissue": "Motor Cortex (BA4)", "tissue_raw": "Cortex_Motor_BA4"},
            {"tissue": "Motor Cortex (BA4)", "tissue_raw": "Cortex Motor Lateral"},
        ]
        for sample in samples:
            assert matches(sample, "motor cortex (ba4)", "tissue", "tissue_raw") is True

    # Edge cases and boundary conditions
    def test_matches_single_character_match(self):
        """Single character should match correctly."""
        sample = {"field": "a"}
        assert matches(sample, "a", "field") is True
        assert matches(sample, "A", "field") is True

    def test_matches_very_long_string(self):
        """Very long strings should match correctly."""
        long_value = "a" * 1000
        sample = {"field": long_value}
        assert matches(sample, long_value, "field") is True

    def test_matches_unicode_in_field_and_query(self):
        """Unicode characters should match case-insensitively."""
        sample = {"field": "Café"}
        assert matches(sample, "café", "field") is True

    def test_matches_numeric_string_field(self):
        """Numeric strings should match as strings, not integers."""
        sample = {"field": "123"}
        assert matches(sample, "123", "field") is True
        assert matches(sample, "456", "field") is False

    def test_matches_field_name_variations(self):
        """Different field names should be independent."""
        sample = {"field1": "value1", "field2": "value2"}
        assert matches(sample, "value1", "field1") is True
        assert matches(sample, "value2", "field2") is True
        assert matches(sample, "value1", "field2") is False