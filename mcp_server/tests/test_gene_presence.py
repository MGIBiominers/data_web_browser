"""Tests for gene_presence.py"""
from unittest.mock import patch

from gene_presence import gene_presence

_PRESENCE = {
    "genes": {
        "STMN2": {"symbol": ["Zelic2025_Immunity", "Cho2020_GSE126044"]},
        "ENSG00000104435": {"ensembl_id": ["SomeStudy"]},
        "UNC13A": {"symbol": ["Zelic2025_Immunity"], "ensembl_id": ["OtherStudy"]},
    }
}


class TestGenePresence:

    @patch('gene_presence.get_gene_presence', return_value=_PRESENCE)
    def test_present_gene_returns_true_and_studies(self, mock_presence):
        result = gene_presence("STMN2")
        assert result.structured_content["present"] is True
        assert result.structured_content["symbol"] == "STMN2"
        assert result.structured_content["studies"] == ["Zelic2025_Immunity", "Cho2020_GSE126044"]
        assert result.structured_content["ensembl_id_only_studies"] == []

    @patch('gene_presence.get_gene_presence', return_value=_PRESENCE)
    def test_absent_gene_returns_false_and_empty_lists(self, mock_presence):
        result = gene_presence("NOT_A_REAL_GENE")
        assert result.structured_content["present"] is False
        assert result.structured_content["studies"] == []
        assert result.structured_content["ensembl_id_only_studies"] == []

    @patch('gene_presence.get_gene_presence', return_value=_PRESENCE)
    def test_querying_by_ensembl_id_returns_ensembl_only_bucket(self, mock_presence):
        result = gene_presence("ENSG00000104435")
        assert result.structured_content["present"] is True
        assert result.structured_content["studies"] == []
        assert result.structured_content["ensembl_id_only_studies"] == ["SomeStudy"]

    @patch('gene_presence.get_gene_presence', return_value=_PRESENCE)
    def test_gene_present_under_both_id_types_separately(self, mock_presence):
        result = gene_presence("UNC13A")
        assert result.structured_content["studies"] == ["Zelic2025_Immunity"]
        assert result.structured_content["ensembl_id_only_studies"] == ["OtherStudy"]

    @patch('gene_presence.get_gene_presence', return_value=_PRESENCE)
    def test_case_sensitive_exact_match(self, mock_presence):
        result = gene_presence("stmn2")
        assert result.structured_content["present"] is False

    @patch('gene_presence.get_gene_presence', return_value={"genes": {}})
    def test_empty_index_reports_not_found_not_error(self, mock_presence):
        result = gene_presence("STMN2")
        assert result.structured_content["present"] is False

    @patch('gene_presence.get_gene_presence', return_value=_PRESENCE)
    def test_full_data_present_in_text_content(self, mock_presence):
        """Same regression class as tool_response's own test: a client that
        only reads `content` must still see the real study list."""
        result = gene_presence("STMN2")
        text = result.content[0].text
        assert "Zelic2025_Immunity" in text
        assert "Cho2020_GSE126044" in text

    @patch('gene_presence.get_gene_presence', return_value=_PRESENCE)
    def test_summary_reflects_present_count(self, mock_presence):
        result = gene_presence("STMN2")
        assert result.content[0].text.startswith("'STMN2' is present in 2 study(ies).")

    @patch('gene_presence.get_gene_presence', return_value=_PRESENCE)
    def test_summary_reflects_ensembl_only(self, mock_presence):
        result = gene_presence("ENSG00000104435")
        assert "under that exact Ensembl ID" in result.content[0].text

    @patch('gene_presence.get_gene_presence', return_value=_PRESENCE)
    def test_summary_reflects_absent(self, mock_presence):
        result = gene_presence("NOT_A_REAL_GENE")
        assert "was not found" in result.content[0].text
