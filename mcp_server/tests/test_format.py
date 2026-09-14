import pytest
from format import format_label


class TestFormatLabel:
    """Tests for format_label function."""
    
    def test_h5ad_extension(self):
        assert format_label("file.h5ad") == "h5ad"
    
    def test_h5mu_extension(self):
        assert format_label("file.h5mu") == "h5mu"
    
    def test_h5_extension(self):
        assert format_label("file.h5") == "h5"
    
    def test_parquet_extension(self):
        assert format_label("file.parquet") == "parquet"
    
    def test_tsv_gz_extension(self):
        assert format_label("file.tsv.gz") == "tsv"
    
    def test_tsv_extension(self):
        assert format_label("file.tsv") == "tsv"
    
    def test_csv_gz_extension(self):
        assert format_label("file.csv.gz") == "csv"
    
    def test_csv_extension(self):
        assert format_label("file.csv") == "csv"
    
    def test_loom_extension(self):
        assert format_label("file.loom") == "loom"
    
    def test_mtx_gz_extension(self):
        assert format_label("file.mtx.gz") == "mtx"
    
    def test_mtx_extension(self):
        assert format_label("file.mtx") == "mtx"
    
    def test_uppercase_extension(self):
        assert format_label("FILE.H5AD") == "h5ad"
        assert format_label("file.H5AD") == "h5ad"
        assert format_label("File.Tsv.Gz") == "tsv"
    
    def test_mixed_case_extension(self):
        assert format_label("MyData.CSV") == "csv"
        assert format_label("mydata.Loom") == "loom"
    
    def test_unknown_extension(self):
        assert format_label("file.txt") == "other"
        assert format_label("file.fasta") == "other"
        assert format_label("file.bam") == "other"
    
    def test_no_extension(self):
        assert format_label("filename") == "other"
    
    def test_empty_string(self):
        assert format_label("") == "other"
    
    def test_extension_only(self):
        assert format_label(".h5ad") == "h5ad"
        assert format_label(".tsv") == "tsv"
    
    def test_multiple_dots(self):
        assert format_label("data.something.h5ad") == "h5ad"
        assert format_label("data.experiment.tsv.gz") == "tsv"
    
    def test_partial_extension_no_match(self):
        assert format_label("file.h5a") == "other"
        assert format_label("file.tsv.g") == "other"
    
    def test_path_with_extension(self):
        assert format_label("/path/to/file.h5ad") == "h5ad"
        assert format_label("relative/path/data.csv.gz") == "csv"
    
    def test_extension_in_directory_name(self):
        assert format_label("/data.h5ad/myfile.txt") == "other"
    
    def test_dot_at_end(self):
        assert format_label("file.") == "other"
    
    def test_case_insensitive_with_path(self):
        assert format_label("/path/to/FILE.CSV.GZ") == "csv"
        assert format_label("/PATH/TO/data.H5MU") == "h5mu"
    
    def test_extension_priority_order(self):
        """Verify that longer/more specific extensions match first."""
        assert format_label("data.tsv.gz") == "tsv"
        assert format_label("data.csv.gz") == "csv"
        assert format_label("data.mtx.gz") == "mtx"
    
    def test_very_long_filename(self):
        assert format_label("very_long_filename_with_many_characters_and_underscores.h5ad") == "h5ad"
    
    def test_filename_with_numbers_and_special_chars(self):
        assert format_label("sample_123_experiment-v2.csv") == "csv"
        assert format_label("data_2024_01_15.loom") == "loom"