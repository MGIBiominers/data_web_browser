"""Typed record shapes for the ALS dataset catalog.

These are the ONLY schema definitions in the project -- build_catalog.py,
s3_sync.py and the web app should all trace back to these field names
rather than each inventing their own. Every field here is sourced directly
from EXTERNAL_DATASETS' own files (studies.tsv, all_samples.tsv, per-study
README/samples.json, and the coordination dir's status JSONs) -- nothing is
borrowed from any other project's schema.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class ProcessedFile:
    """One file found in studies/<id>/processed/ on HTCF."""

    name: str
    bytes: int
    category: str  # "data" | "doc" | "metadata" | "other" -- see sources.classify_file
    sha256: str | None = None  # populated by s3_sync.py once uploaded
    s3_key: str | None = None  # populated once actually present in the bucket


@dataclass
class RolePhase:
    """One coordination role's view of a study (conversion, verification, ...)."""

    phase: str | None
    note: str | None


@dataclass
class StudyRecord:
    study_id: str

    # From studies.tsv
    journal: str | None
    year: str | None
    title: str | None
    pmid: str | None
    doi: str | None
    bioproject: str | None
    gse: list[str]
    cellxgene_collection: str | None
    synapse: str | None
    assay_types: list[str]
    primary_route: str | None
    notes: str | None
    summary: str | None

    # Derived from all_samples.tsv
    n_samples: int
    organisms: list[str]
    disease_statuses: list[str]
    tissues: list[str]

    # From studies/<id>/README.md
    abstract: str | None

    # From the coordination dir's per-role status JSONs
    download: RolePhase
    conversion: RolePhase
    verification: RolePhase
    alignment: RolePhase

    # From studies/<id>/processed/ (+ live S3 state once published)
    processed_files: list[ProcessedFile]
    available_externally: bool
    s3_prefix: str | None

    # Derived from all_samples.tsv's additive canonical-vocabulary columns
    # (disease_status_canonical/tissue/cell_type/genotype_canonical, added
    # 2026-09-11 by the HTCF collection's own vocabulary-normalization pass
    # -- see EXTERNAL_DATASETS/vocabulary/CHANGES.md). These back the web
    # app's filters; disease_statuses/tissues above stay the raw values, for
    # display, exactly as before.
    disease_statuses_canonical: list[str] = field(default_factory=list)
    tissues_canonical: list[str] = field(default_factory=list)
    cell_types: list[str] = field(default_factory=list)
    genotypes_canonical: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SampleRecord:
    """Mirrors an all_samples.tsv row exactly -- no added/renamed fields."""

    study_id: str
    accession: str | None
    sample_id: str | None
    assay_type: str | None
    sample_source: str | None
    organism: str | None
    cell_line_or_donor: str | None
    genotype: str | None
    disease_status: str | None
    tissue_or_cell_type: str | None
    timepoint_or_age: str | None
    treatment: str | None
    sex: str | None
    platform: str | None
    batch: str | None
    file_names: str | None
    is_filtered: str | None
    source_doi_or_pmid: str | None
    extra_disease_onset_site: str | None
    extra_chip_antibody: str | None

    # Additive canonical-vocabulary columns (see StudyRecord's comment above
    # for provenance) -- disease_status/tissue_or_cell_type/genotype above
    # stay the untouched raw values.
    disease_status_canonical: str | None = None
    tissue: str | None = None
    cell_type: str | None = None
    genotype_canonical: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


# Absolute path of the same EXTERNAL_DATASETS tree on RIS (Storage3); the layout
# below it matches the HTCF root exactly.
RIS_ROOT = "/storage3/fs1/rmitra-cajal/Active/EXTERNAL_DATASETS"


@dataclass
class Catalog:
    generated_at: str
    source_root: str
    studies: list[StudyRecord] = field(default_factory=list)
    # Absolute root of the collection per system, e.g. {"htcf": ..., "ris": ...}.
    # source_root stays as the HTCF root for older consumers.
    roots: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "generated_at": self.generated_at,
            "source_root": self.source_root,
            "roots": self.roots,
            "studies": [s.to_dict() for s in self.studies],
        }
