import pytest
from dataclasses import asdict
from pipeline.catalog_schema import (
    ProcessedFile,
    RolePhase,
    StudyRecord,
    SampleRecord,
    Catalog,
)


class TestProcessedFile:
    def test_instantiation_with_required_fields(self):
        pf = ProcessedFile(name="test.txt", bytes=1024, category="data")
        assert pf.name == "test.txt"
        assert pf.bytes == 1024
        assert pf.category == "data"
        assert pf.sha256 is None
        assert pf.s3_key is None

    def test_instantiation_with_all_fields(self):
        pf = ProcessedFile(
            name="test.txt",
            bytes=1024,
            category="metadata",
            sha256="abc123",
            s3_key="s3://bucket/test.txt"
        )
        assert pf.sha256 == "abc123"
        assert pf.s3_key == "s3://bucket/test.txt"

    def test_category_values(self):
        for category in ["data", "doc", "metadata", "other"]:
            pf = ProcessedFile(name="test", bytes=100, category=category)
            assert pf.category == category

    def test_bytes_zero(self):
        pf = ProcessedFile(name="test", bytes=0, category="data")
        assert pf.bytes == 0

    def test_bytes_large_value(self):
        pf = ProcessedFile(name="test", bytes=1_000_000_000_000, category="data")
        assert pf.bytes == 1_000_000_000_000

    def test_sha256_none_and_populated(self):
        pf1 = ProcessedFile(name="test", bytes=100, category="data", sha256=None)
        assert pf1.sha256 is None
        pf2 = ProcessedFile(name="test", bytes=100, category="data", sha256="")
        assert pf2.sha256 == ""


class TestRolePhase:
    def test_instantiation_with_all_none(self):
        rp = RolePhase(phase=None, note=None)
        assert rp.phase is None
        assert rp.note is None

    def test_instantiation_with_values(self):
        rp = RolePhase(phase="verification", note="In progress")
        assert rp.phase == "verification"
        assert rp.note == "In progress"

    def test_partial_values(self):
        rp1 = RolePhase(phase="conversion", note=None)
        assert rp1.phase == "conversion"
        assert rp1.note is None
        rp2 = RolePhase(phase=None, note="Complete")
        assert rp2.phase is None
        assert rp2.note == "Complete"

    def test_to_dict(self):
        rp = RolePhase(phase="alignment", note="Done")
        result = asdict(rp)
        assert result == {"phase": "alignment", "note": "Done"}


class TestStudyRecord:
    def test_instantiation_minimal(self):
        sr = StudyRecord(
            study_id="s001",
            journal=None, year=None, title=None, pmid=None, doi=None,
            bioproject=None, gse=[], cellxgene_collection=None,
            synapse=None, assay_types=[], primary_route=None, notes=None, summary=None,
            n_samples=0, organisms=[], disease_statuses=[], tissues=[], abstract=None,
            download=RolePhase(None, None),
            conversion=RolePhase(None, None),
            verification=RolePhase(None, None),
            alignment=RolePhase(None, None),
            processed_files=[], available_externally=False, s3_prefix=None
        )
        assert sr.study_id == "s001"
        assert sr.n_samples == 0
        assert sr.organisms == []
        assert sr.processed_files == []

    def test_instantiation_full(self):
        sr = StudyRecord(
            study_id="s002",
            journal="Nature",
            year="2023",
            title="ALS Study",
            pmid="12345678",
            doi="10.1234/test",
            bioproject="PRJNA123456",
            gse=["GSE123456", "GSE123457"],
            cellxgene_collection="col123",
            synapse="syn123456",
            assay_types=["RNA-seq", "ATAC-seq"],
            primary_route="download",
            notes="Test notes", summary=None,
            n_samples=1000,
            organisms=["Homo sapiens"], disease_statuses=[], tissues=[],
            abstract="Test abstract",
            download=RolePhase("complete", None),
            conversion=RolePhase("in_progress", "Pending"),
            verification=RolePhase(None, None),
            alignment=RolePhase("queued", None),
            processed_files=[ProcessedFile("f1.txt", 1024, "data")],
            available_externally=True,
            s3_prefix="s3://bucket/s002"
        )
        assert sr.journal == "Nature"
        assert sr.year == "2023"
        assert sr.n_samples == 1000
        assert len(sr.gse) == 2
        assert len(sr.assay_types) == 2

    def test_gse_empty_and_multiple(self):
        sr1 = StudyRecord(
            study_id="s003", journal=None, year=None, title=None, pmid=None,
            doi=None, bioproject=None, gse=[], cellxgene_collection=None,
            synapse=None, assay_types=[], primary_route=None, notes=None, summary=None,
            n_samples=0, organisms=[], disease_statuses=[], tissues=[], abstract=None,
            download=RolePhase(None, None), conversion=RolePhase(None, None),
            verification=RolePhase(None, None), alignment=RolePhase(None, None),
            processed_files=[], available_externally=False, s3_prefix=None
        )
        assert sr1.gse == []
        
        sr2 = StudyRecord(
            study_id="s004", journal=None, year=None, title=None, pmid=None,
            doi=None, bioproject=None, gse=["GSE1", "GSE2", "GSE3"],
            cellxgene_collection=None, synapse=None, assay_types=[],
            primary_route=None, notes=None, summary=None, n_samples=0, organisms=[], disease_statuses=[], tissues=[],
            abstract=None, download=RolePhase(None, None),
            conversion=RolePhase(None, None), verification=RolePhase(None, None),
            alignment=RolePhase(None, None), processed_files=[],
            available_externally=False, s3_prefix=None
        )
        assert len(sr2.gse) == 3

    def test_organisms_multiple(self):
        sr = StudyRecord(
            study_id="s005", journal=None, year=None, title=None, pmid=None,
            doi=None, bioproject=None, gse=[], cellxgene_collection=None,
            synapse=None, assay_types=[], primary_route=None, notes=None, summary=None,
            n_samples=5, organisms=["Homo sapiens", "Mus musculus"], disease_statuses=[], tissues=[], abstract=None,
            download=RolePhase(None, None), conversion=RolePhase(None, None),
            verification=RolePhase(None, None), alignment=RolePhase(None, None),
            processed_files=[], available_externally=False, s3_prefix=None
        )
        assert len(sr.organisms) == 2
        assert "Homo sapiens" in sr.organisms

    def test_to_dict_basic(self):
        sr = StudyRecord(
            study_id="s006", journal="Test Journal", year="2024",
            title="Test Title", pmid=None, doi=None, bioproject=None, gse=[],
            cellxgene_collection=None, synapse=None, assay_types=[],
            primary_route=None, notes=None, summary=None, n_samples=10,
            organisms=["Homo sapiens"], disease_statuses=[], tissues=[], abstract="Abstract text",
            download=RolePhase("complete", None),
            conversion=RolePhase(None, None),
            verification=RolePhase(None, None),
            alignment=RolePhase(None, None),
            processed_files=[], available_externally=False, s3_prefix=None
        )
        result = sr.to_dict()
        assert isinstance(result, dict)
        assert result["study_id"] == "s006"
        assert result["journal"] == "Test Journal"
        assert result["n_samples"] == 10

    def test_to_dict_with_nested_objects(self):
        pf = ProcessedFile("file.txt", 512, "data", sha256="abc123")
        sr = StudyRecord(
            study_id="s007", journal=None, year=None, title=None, pmid=None,
            doi=None, bioproject=None, gse=[], cellxgene_collection=None,
            synapse=None, assay_types=[], primary_route=None, notes=None, summary=None,
            n_samples=0, organisms=[], disease_statuses=[], tissues=[], abstract=None,
            download=RolePhase("pending", "Review"),
            conversion=RolePhase(None, None),
            verification=RolePhase(None, None),
            alignment=RolePhase(None, None),
            processed_files=[pf], available_externally=False, s3_prefix=None
        )
        result = sr.to_dict()
        assert isinstance(result["download"], dict)
        assert result["download"]["phase"] == "pending"
        assert result["download"]["note"] == "Review"
        assert len(result["processed_files"]) == 1
        assert result["processed_files"][0]["name"] == "file.txt"

    def test_all_role_phases_combinations(self):
        for phase_val in [None, "pending", "complete"]:
            for note_val in [None, "Some note"]:
                sr = StudyRecord(
                    study_id="s008", journal=None, year=None, title=None,
                    pmid=None, doi=None, bioproject=None, gse=[],
                    cellxgene_collection=None, synapse=None, assay_types=[],
                    primary_route=None, notes=None, summary=None, n_samples=0, organisms=[], disease_statuses=[], tissues=[],
                    abstract=None, download=RolePhase(phase_val, note_val),
                    conversion=RolePhase(None, None),
                    verification=RolePhase(None, None),
                    alignment=RolePhase(None, None),
                    processed_files=[], available_externally=False, s3_prefix=None
                )
                assert sr.download.phase == phase_val
                assert sr.download.note == note_val

    def test_multiple_processed_files(self):
        files = [
            ProcessedFile(f"f{i}.txt", i*100, "data") for i in range(5)
        ]
        sr = StudyRecord(
            study_id="s009", journal=None, year=None, title=None, pmid=None,
            doi=None, bioproject=None, gse=[], cellxgene_collection=None,
            synapse=None, assay_types=[], primary_route=None, notes=None, summary=None,
            n_samples=0, organisms=[], disease_statuses=[], tissues=[], abstract=None,
            download=RolePhase(None, None),
            conversion=RolePhase(None, None),
            verification=RolePhase(None, None),
            alignment=RolePhase(None, None),
            processed_files=files, available_externally=False, s3_prefix=None
        )
        assert len(sr.processed_files) == 5
        assert sr.processed_files[0].name == "f0.txt"
        assert sr.processed_files[4].name == "f4.txt"


class TestSampleRecord:
    def test_instantiation_minimal(self):
        sr = SampleRecord(
            study_id="study_001",
            accession=None, sample_id=None, assay_type=None, sample_source=None,
            organism=None, cell_line_or_donor=None, genotype=None,
            disease_status=None, tissue_or_cell_type=None, timepoint_or_age=None,
            treatment=None, sex=None, platform=None, batch=None, file_names=None,
            is_filtered=None, source_doi_or_pmid=None,
            extra_disease_onset_site=None, extra_chip_antibody=None
        )
        assert sr.study_id == "study_001"
        assert sr.accession is None

    def test_instantiation_full(self):
        sr = SampleRecord(
            study_id="study_002", accession="SRR123456", sample_id="sample_001",
            assay_type="RNA-seq", sample_source="tissue", organism="Homo sapiens",
            cell_line_or_donor="donor_001", genotype="WT", disease_status="ALS",
            tissue_or_cell_type="motor_neuron", timepoint_or_age="30",
            treatment="none", sex="F", platform="Illumina", batch="batch_1",
            file_names="sample_001_R1.fastq.gz", is_filtered="true",
            source_doi_or_pmid="10.1234/test", extra_disease_onset_site="limb",
            extra_chip_antibody="CD4"
        )
        assert sr.accession == "SRR123456"
        assert sr.assay_type == "RNA-seq"
        assert sr.organism == "Homo sapiens"
        assert sr.sex == "F"

    def test_to_dict_all_none(self):
        sr = SampleRecord(
            study_id="study_003",
            accession=None, sample_id=None, assay_type=None, sample_source=None,
            organism=None, cell_line_or_donor=None, genotype=None,
            disease_status=None, tissue_or_cell_type=None, timepoint_or_age=None,
            treatment=None, sex=None, platform=None, batch=None, file_names=None,
            is_filtered=None, source_doi_or_pmid=None,
            extra_disease_onset_site=None, extra_chip_antibody=None
        )
        result = sr.to_dict()
        assert isinstance(result, dict)
        assert result["study_id"] == "study_003"
        for key in result:
            if key != "study_id":
                assert result[key] is None

    def test_to_dict_with_values(self):
        sr = SampleRecord(
            study_id="study_004", accession="ACC123", sample_id="SAMPLE123",
            assay_type="ATAC-seq", sample_source="blood", organism="Mus musculus",
            cell_line_or_donor="donor_002", genotype="KO", disease_status="healthy",
            tissue_or_cell_type="immune_cell", timepoint_or_age="20",
            treatment="treatment_A", sex="M", platform="10x", batch="batch_2",
            file_names="multi_file.tar.gz", is_filtered="false",
            source_doi_or_pmid="PMID:123456", extra_disease_onset_site="spinal",
            extra_chip_antibody="CD8"
        )
        result = sr.to_dict()
        assert result["study_id"] == "study_004"
        assert result["accession"] == "ACC123"
        assert result["organism"] == "Mus musculus"
        assert result["is_filtered"] == "false"

    def test_partial_values(self):
        sr = SampleRecord(
            study_id="study_005", accession="ACC456", sample_id=None,
            assay_type="RNA-seq", sample_source=None, organism="Homo sapiens",
            cell_line_or_donor=None, genotype=None, disease_status="ALS",
            tissue_or_cell_type=None, timepoint_or_age=None, treatment=None,
            sex="F", platform=None, batch="batch_3", file_names=None,
            is_filtered=None, source_doi_or_pmid=None,
            extra_disease_onset_site=None, extra_chip_antibody=None
        )
        result = sr.to_dict()
        assert result["accession"] == "ACC456"
        assert result["sample_id"] is None
        assert result["sex"] == "F"

    def test_empty_string_values(self):
        sr = SampleRecord(
            study_id="", accession="", sample_id="", assay_type="",
            sample_source="", organism="", cell_line_or_donor="",
            genotype="", disease_status="", tissue_or_cell_type="",
            timepoint_or_age="", treatment="", sex="", platform="",
            batch="", file_names="", is_filtered="", source_doi_or_pmid="",
            extra_disease_onset_site="", extra_chip_antibody="",
            disease_status_canonical="", tissue="", cell_type="",
            genotype_canonical="",
        )
        result = sr.to_dict()
        for value in result.values():
            assert value == ""


class TestCatalog:
    def test_instantiation_minimal(self):
        cat = Catalog(generated_at="2024-01-01T00:00:00Z", source_root="/data")
        assert cat.generated_at == "2024-01-01T00:00:00Z"
        assert cat.source_root == "/data"
        assert cat.studies == []

    def test_to_dict_empty(self):
        cat = Catalog(generated_at="2024-01-01T00:00:00Z", source_root="/data/root")
        result = cat.to_dict()
        assert isinstance(result, dict)
        assert result["generated_at"] == "2024-01-01T00:00:00Z"
        assert result["source_root"] == "/data/root"
        assert result["studies"] == []

    def test_to_dict_with_single_study(self):
        study = StudyRecord(
            study_id="study_test", journal="Journal", year="2024",
            title="Title", pmid=None, doi=None, bioproject=None, gse=["GSE123"],
            cellxgene_collection=None, synapse=None, assay_types=["RNA-seq"],
            primary_route=None, notes=None, summary=None, n_samples=5,
            organisms=["Homo sapiens"], disease_statuses=[], tissues=[], abstract="Abstract text",
            download=RolePhase("complete", None),
            conversion=RolePhase(None, None),
            verification=RolePhase(None, None),
            alignment=RolePhase(None, None),
            processed_files=[], available_externally=True, s3_prefix="s3://bucket/study"
        )
        cat = Catalog(
            generated_at="2024-01-01T12:00:00Z",
            source_root="/path/to/data",
            studies=[study]
        )
        result = cat.to_dict()
        assert result["generated_at"] == "2024-01-01T12:00:00Z"
        assert result["source_root"] == "/path/to/data"
        assert len(result["studies"]) == 1
        assert result["studies"][0]["study_id"] == "study_test"
        assert result["studies"][0]["journal"] == "Journal"

    def test_to_dict_with_multiple_studies(self):
        study1 = StudyRecord(
            study_id="s1", journal="Nature", year="2023", title="Study One",
            pmid="111", doi="10.1/one", bioproject="PRJNA111", gse=["GSE111"],
            cellxgene_collection="col1", synapse="syn111", assay_types=["RNA-seq"],
            primary_route="download", notes="First", summary=None, n_samples=100,
            organisms=["Homo sapiens"], disease_statuses=[], tissues=[], abstract="Abstract 1",
            download=RolePhase("complete", None),
            conversion=RolePhase("in_progress", None),
            verification=RolePhase(None, None),
            alignment=RolePhase(None, None),
            processed_files=[ProcessedFile("f1.txt", 1024, "data")],
            available_externally=True, s3_prefix="s3://bucket/s1"
        )
        study2 = StudyRecord(
            study_id="s2", journal="Science", year="2024", title="Study Two",
            pmid="222", doi="10.1/two", bioproject="PRJNA222", gse=["GSE221"],
            cellxgene_collection="col2", synapse="syn222",
            assay_types=["ATAC-seq"], primary_route="api", notes="Second", summary=None,
            n_samples=200, organisms=["Mus musculus", "Homo sapiens"], disease_statuses=[], tissues=[],
            abstract="Abstract 2",
            download=RolePhase("complete", None),
            conversion=RolePhase("complete", None),
            verification=RolePhase("complete", None),
            alignment=RolePhase("complete", None),
            processed_files=[], available_externally=False, s3_prefix=None
        )
        cat = Catalog(
            generated_at="2024-01-15T10:30:00Z",
            source_root="/data/source",
            studies=[study1, study2]
        )
        result = cat.to_dict()
        assert len(result["studies"]) == 2
        assert result["studies"][0]["study_id"] == "s1"
        assert result["studies"][1]["study_id"] == "s2"

    def test_to_dict_preserves_nested_structure(self):
        pf = ProcessedFile("file.txt", 100, "data", sha256="abc", s3_key="s3://key")
        sr = StudyRecord(
            study_id="s_nested", journal=None, year=None, title=None, pmid=None,
            doi=None, bioproject=None, gse=[], cellxgene_collection=None,
            synapse=None, assay_types=[], primary_route=None, notes=None, summary=None,
            n_samples=1, organisms=[], disease_statuses=[], tissues=[], abstract=None,
            download=RolePhase("pending", "Waiting"),
            conversion=RolePhase(None, None),
            verification=RolePhase(None, None),
            alignment=RolePhase(None, None),
            processed_files=[pf], available_externally=False, s3_prefix=None
        )
        cat = Catalog(
            generated_at="2024-01-01T00:00:00Z",
            source_root="/data",
            studies=[sr]
        )
        result = cat.to_dict()
        study_dict = result["studies"][0]
        assert isinstance(study_dict["download"], dict)
        assert study_dict["download"]["phase"] == "pending"
        assert len(study_dict["processed_files"]) == 1
        assert study_dict["processed_files"][0]["sha256"] == "abc"


class TestEdgeCases:
    def test_special_characters_in_strings(self):
        pf = ProcessedFile(name="file\n\t.txt", bytes=0, category="data")
        assert "\n" in pf.name

    def test_large_byte_counts(self):
        pf = ProcessedFile(name="large", bytes=999_999_999_999_999, category="data")
        assert pf.bytes == 999_999_999_999_999

    def test_many_processed_files(self):
        files = [ProcessedFile(f"file{i}.txt", i, "data") for i in range(1000)]
        sr = StudyRecord(
            study_id="many_files", journal=None, year=None, title=None, pmid=None,
            doi=None, bioproject=None, gse=[], cellxgene_collection=None,
            synapse=None, assay_types=[], primary_route=None, notes=None, summary=None,
            n_samples=0, organisms=[], disease_statuses=[], tissues=[], abstract=None,
            download=RolePhase(None, None),
            conversion=RolePhase(None, None),
            verification=RolePhase(None, None),
            alignment=RolePhase(None, None),
            processed_files=files, available_externally=False, s3_prefix=None
        )
        assert len(sr.processed_files) == 1000

    def test_many_studies_in_catalog(self):
        studies = []
        for i in range(100):
            study = StudyRecord(
                study_id=f"s{i:03d}", journal=None, year=None, title=None,
                pmid=None, doi=None, bioproject=None, gse=[], 
                cellxgene_collection=None, synapse=None, assay_types=[],
                primary_route=None, notes=None, summary=None, n_samples=i, organisms=[], disease_statuses=[], tissues=[],
                abstract=None, download=RolePhase(None, None),
                conversion=RolePhase(None, None),
                verification=RolePhase(None, None),
                alignment=RolePhase(None, None),
                processed_files=[], available_externally=False, s3_prefix=None
            )
            studies.append(study)
        cat = Catalog(
            generated_at="2024-01-01T00:00:00Z",
            source_root="/data",
            studies=studies
        )
        result = cat.to_dict()
        assert len(result["studies"]) == 100

class TestCatalogRoots:
    def test_to_dict_includes_roots_and_keeps_source_root(self):
        from catalog_schema import Catalog

        cat = Catalog(generated_at="t", source_root="/a", roots={"htcf": "/a", "ris": "/b"})
        d = cat.to_dict()
        assert d["source_root"] == "/a"
        assert d["roots"] == {"htcf": "/a", "ris": "/b"}

    def test_roots_default_empty(self):
        from catalog_schema import Catalog

        assert Catalog(generated_at="t", source_root="/a").to_dict()["roots"] == {}
