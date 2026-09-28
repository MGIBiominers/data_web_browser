"""Tests for build_gene_presence.py.

Uses real small h5ad-shaped HDF5 files and real parquet files (via h5py/
pyarrow directly) rather than mocking file I/O -- this module's whole job
is reading real binary file formats, so a fixture built the same way is far
more trustworthy than mocking h5py.File/pq.read_schema's internals.
"""
from __future__ import annotations

import h5py
import pyarrow as pa
import pyarrow.parquet as pq

from build_gene_presence import (
    _h5ad_genes,
    _load_symbol_map,
    _parquet_genes,
    scan,
)


def _write_h5ad_like(path, gene_names, index_attr_name="_index"):
    """Minimal HDF5 file with just the /var/<index> group h5py needs --
    not a real full h5ad (no X/obs), since _h5ad_genes never touches those."""
    with h5py.File(path, "w") as f:
        var = f.create_group("var")
        var.attrs["_index"] = index_attr_name
        var.create_dataset(index_attr_name, data=[g.encode("utf-8") for g in gene_names])


class TestH5adGenes:
    def test_reads_gene_names(self, tmp_path):
        path = tmp_path / "study.h5ad"
        _write_h5ad_like(path, ["STMN2", "UNC13A", "TARDBP"])
        assert _h5ad_genes(path) == ["STMN2", "UNC13A", "TARDBP"]

    def test_custom_index_attr_name(self, tmp_path):
        path = tmp_path / "study.h5ad"
        _write_h5ad_like(path, ["Xkr4", "Gm1992"], index_attr_name="gene_ids")
        assert _h5ad_genes(path) == ["Xkr4", "Gm1992"]

    def test_empty_h5ad(self, tmp_path):
        path = tmp_path / "study.h5ad"
        _write_h5ad_like(path, [])
        assert _h5ad_genes(path) == []


class TestLoadSymbolMap:
    def test_no_companion_file_returns_none(self, tmp_path):
        assert _load_symbol_map(tmp_path, "study_bulk_GSE1_counts.parquet") is None

    def test_loads_matching_companion_file(self, tmp_path):
        (tmp_path / "study_bulk_GSE1_gene_symbol_map.tsv").write_text(
            "gene_id\tgene_symbol\nENSG001\tSTMN2\nENSG002\tUNC13A\n", encoding="utf-8"
        )
        result = _load_symbol_map(tmp_path, "study_bulk_GSE1_counts.parquet")
        assert result == {"ENSG001": "STMN2", "ENSG002": "UNC13A"}

    def test_does_not_match_a_different_file_groups_map(self, tmp_path):
        # Real case: SRP566214_dataset has two bulk file groups (-AAV and
        # -AAVS1), each with its own map -- must not cross-match.
        (tmp_path / "study_bulk_GSE1-AAV_gene_symbol_map.tsv").write_text(
            "gene_id\tgene_symbol\nENSG001\tSTMN2\n", encoding="utf-8"
        )
        assert _load_symbol_map(tmp_path, "study_bulk_GSE1-AAVS1_counts.parquet") is None

    def test_skips_malformed_lines(self, tmp_path):
        (tmp_path / "study_bulk_GSE1_gene_symbol_map.tsv").write_text(
            "gene_id\tgene_symbol\nENSG001\tSTMN2\nmalformed_line_no_tab\nENSG002\tUNC13A\n",
            encoding="utf-8",
        )
        result = _load_symbol_map(tmp_path, "study_bulk_GSE1_counts.parquet")
        assert result == {"ENSG001": "STMN2", "ENSG002": "UNC13A"}


class TestParquetGenes:
    def _write_parquet(self, path, columns):
        table = pa.table({c: [1.0] for c in columns})
        pq.write_table(table, path)

    def test_symbol_columns_used_as_is(self, tmp_path):
        path = tmp_path / "study_bulk_GSE1_counts.parquet"
        self._write_parquet(path, ["OR4F5", "SAMD11", "NOC2L"])
        genes, id_type = _parquet_genes(path)
        assert set(genes) == {"OR4F5", "SAMD11", "NOC2L"}
        assert id_type == "symbol"

    def test_ensembl_columns_translated_with_companion_map(self, tmp_path):
        path = tmp_path / "study_bulk_GSE1_counts.parquet"
        self._write_parquet(path, ["ENSG00000001", "ENSG00000002"])
        (tmp_path / "study_bulk_GSE1_gene_symbol_map.tsv").write_text(
            "gene_id\tgene_symbol\nENSG00000001\tSTMN2\nENSG00000002\tUNC13A\n",
            encoding="utf-8",
        )
        genes, id_type = _parquet_genes(path)
        assert set(genes) == {"STMN2", "UNC13A"}
        assert id_type == "symbol"

    def test_ensembl_columns_without_map_fall_back_to_raw_ids(self, tmp_path):
        path = tmp_path / "study_bulk_GSE1_counts.parquet"
        self._write_parquet(path, ["ENSG00000001", "ENSG00000002"])
        genes, id_type = _parquet_genes(path)
        assert set(genes) == {"ENSG00000001", "ENSG00000002"}
        assert id_type == "ensembl_id"

    def test_mouse_ensembl_ids_also_detected(self, tmp_path):
        path = tmp_path / "study_bulk_GSE1_counts.parquet"
        self._write_parquet(path, ["ENSMUSG00000001", "ENSMUSG00000002"])
        genes, id_type = _parquet_genes(path)
        assert id_type == "ensembl_id"  # no companion map -> raw IDs kept


class TestScan:
    def _make_study(self, root, study_id, files):
        """files: {filename: 'h5ad'|'parquet-symbol'|'parquet-ensembl'|'other'}"""
        processed = root / "studies" / study_id / "processed"
        processed.mkdir(parents=True)
        for filename, kind in files.items():
            path = processed / filename
            if kind == "h5ad":
                _write_h5ad_like(path, ["STMN2", "UNC13A"])
            elif kind == "parquet-symbol":
                table = pa.table({"OR4F5": [1.0], "SAMD11": [2.0]})
                pq.write_table(table, path)
            elif kind == "parquet-ensembl":
                table = pa.table({"ENSG00000001": [1.0]})
                pq.write_table(table, path)
            else:
                path.write_text("not a real data file", encoding="utf-8")
        return processed

    def test_collects_genes_from_h5ad(self, tmp_path):
        self._make_study(tmp_path, "study1", {"study1_data.h5ad": "h5ad"})
        presence = scan(tmp_path)
        assert presence["STMN2"] == {"symbol": ["study1"]}

    def test_collects_genes_from_gene_level_parquet(self, tmp_path):
        self._make_study(tmp_path, "study1", {"study1_bulk_GSE1_counts.parquet": "parquet-symbol"})
        presence = scan(tmp_path)
        assert presence["OR4F5"] == {"symbol": ["study1"]}

    def test_ensembl_fallback_kept_under_its_own_id_type_key(self, tmp_path):
        self._make_study(tmp_path, "study1", {"study1_bulk_GSE1_counts.parquet": "parquet-ensembl"})
        presence = scan(tmp_path)
        assert presence["ENSG00000001"] == {"ensembl_id": ["study1"]}

    def test_multiple_files_in_same_study_do_not_duplicate_study_entry(self, tmp_path):
        # The real bug this guards against: a study with 3 h5ad files
        # sharing common genes used to record that study 3 times for the
        # same gene (512MB of redundant JSON, 2026-09-28) -- one
        # study_id-per-gene entry regardless of how many of its files
        # contain that gene.
        self._make_study(tmp_path, "study1", {"a.h5ad": "h5ad", "b.h5ad": "h5ad"})
        presence = scan(tmp_path)
        assert presence["STMN2"] == {"symbol": ["study1"]}

    def test_excludes_te_counts_files(self, tmp_path):
        self._make_study(tmp_path, "study1", {"study1_bulk_GSE1_te_counts.parquet": "parquet-symbol"})
        assert scan(tmp_path) == {}

    def test_excludes_splicing_files(self, tmp_path):
        self._make_study(tmp_path, "study1", {"study1_bulk_GSE1_splicing.parquet": "parquet-symbol"})
        assert scan(tmp_path) == {}

    def test_excludes_non_data_files(self, tmp_path):
        self._make_study(tmp_path, "study1", {"conversion_log.md": "other"})
        assert scan(tmp_path) == {}

    def test_study_without_processed_dir_skipped(self, tmp_path):
        (tmp_path / "studies" / "study1").mkdir(parents=True)
        assert scan(tmp_path) == {}

    def test_same_gene_across_multiple_studies_both_recorded(self, tmp_path):
        self._make_study(tmp_path, "study1", {"a.h5ad": "h5ad"})
        self._make_study(tmp_path, "study2", {"b.h5ad": "h5ad"})
        presence = scan(tmp_path)
        assert set(presence["STMN2"]["symbol"]) == {"study1", "study2"}

    def test_duplicate_genes_within_one_file_deduplicated(self, tmp_path):
        # STMN2 appearing twice in the same h5ad's var_names collapses to
        # one study entry, not two.
        processed = tmp_path / "studies" / "study1" / "processed"
        processed.mkdir(parents=True)
        _write_h5ad_like(processed / "a.h5ad", ["STMN2", "STMN2", "UNC13A"])
        presence = scan(tmp_path)
        assert presence["STMN2"]["symbol"] == ["study1"]
