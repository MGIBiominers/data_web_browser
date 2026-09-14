"""Maps data formats/domains to their reference resource, as MCP
resource-link content blocks a tool can attach to its result -- so a client
sees the resource is available in the same response, without having to
notice and parse a URI out of a plain JSON field."""
from __future__ import annotations

from mcp import types

_FORMAT_RESOURCES = {
    "h5ad": ("pipeline-docs://h5ad_schema", "h5ad/h5mu file structure reference"),
    "h5mu": ("pipeline-docs://h5ad_schema", "h5ad/h5mu file structure reference"),
    "parquet": ("pipeline-docs://bulk_rnaseq_schema", "Bulk RNA-seq file structure reference"),
    "tsv": ("pipeline-docs://bulk_rnaseq_schema", "Bulk RNA-seq file structure reference"),
    "csv": ("pipeline-docs://bulk_rnaseq_schema", "Bulk RNA-seq file structure reference"),
}
SAMPLE_METADATA = ("pipeline-docs://sample_metadata_schema", "Normalized sample metadata field reference")


def for_formats(formats) -> list:
    seen = {}
    for fmt in formats:
        entry = _FORMAT_RESOURCES.get(fmt)
        if entry:
            seen[entry[0]] = entry
    return [_link(uri, desc) for uri, desc in seen.values()]


def sample_metadata_link():
    return _link(*SAMPLE_METADATA)


def _link(uri: str, description: str):
    return types.ResourceLink(
        type="resource_link", uri=uri, name=uri.split("://", 1)[1],
        description=description, mime_type="text/markdown",
    )
