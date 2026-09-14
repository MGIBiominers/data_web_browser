"""FastMCP-style server for the ALS EXTERNAL_DATASETS catalog.

Read-only search/detail/download tools plus static reference resources
describing this collection's file formats and processing methodology, and
one write tool (request_dataset_download) for queuing new-dataset requests.
Runs as a plain ASGI app inside AWS Lambda via the AWS Lambda Web Adapter
(see run.sh and infra/mcp.tf) -- no Lambda-specific code needed here.

Uses the `mcp` Python SDK's v2 API (MCPServer, formerly FastMCP in v1) --
see DESIGN.md for the v1->v2 migration notes this project hit while
building this (FastMCP renamed, streamable_http_app()'s kwargs moved off
the constructor, docstrings still auto-become tool descriptions).
"""
from __future__ import annotations

from pathlib import Path

from mcp.server.mcpserver import MCPServer

from tools import (
    explain_data_file,
    get_download_links,
    get_sample_details,
    get_study_overview,
    request_dataset_download,
    search_samples,
    search_studies,
)

mcp = MCPServer(
    "als-dataset-catalog",
    instructions=(
        "Tools for finding and downloading processed ALS/neurodegeneration "
        "sequencing datasets from the BioMiners EXTERNAL_DATASETS collection. "
        "Start with search_studies or search_samples to find relevant data, "
        "use get_study_overview/get_sample_details for full context on a "
        "specific match, explain_data_file to understand what's actually "
        "inside a given processed file before downloading it, and "
        "get_download_links to get an S3 URL once you know what you want. "
        "See the pipeline-docs:// resources for how this collection's files "
        "are structured and processed. Use request_dataset_download to ask "
        "for a dataset that isn't in the collection yet."
    ),
)

for fn in (
    search_studies.search_studies,
    get_study_overview.get_study_overview,
    search_samples.search_samples,
    get_sample_details.get_sample_details,
    explain_data_file.explain_data_file,
    get_download_links.get_download_links,
    request_dataset_download.request_dataset_download,
):
    mcp.tool()(fn)

def _make_reader(path: Path):
    """A true closure over `path` via this factory's own parameter -- the
    returned function takes zero parameters, which mcp.resource() requires
    for a non-templated (no {...} in the URI) resource; a default-argument
    trick (`def _reader(p=path)`) does NOT work here even though it's a
    common closure-over-loop-variable idiom elsewhere, because mcp.resource
    inspects the handler's signature and rejects ANY declared parameter --
    default value or not -- when the URI has no template variables."""
    def _reader() -> str:
        return path.read_text(encoding="utf-8")
    return _reader


_RESOURCES_DIR = Path(__file__).parent / "resources"
for path in sorted(_RESOURCES_DIR.glob("*.md")):
    mcp.resource(
        f"pipeline-docs://{path.stem}",
        name=path.stem.replace("_", " "),
        description=f"Reference: {path.stem.replace('_', ' ')} -- how this "
                     f"collection's data is structured and processed.",
        mime_type="text/markdown",
    )(_make_reader(path))

# json_response + stateless_http: every request is self-contained (no
# server-held SSE session across invocations), which is what Lambda's
# single invocation/response model needs -- see s3_clients.py's own
# analogous note about not relying on state surviving across Lambda calls.
#
# host="0.0.0.0" matters, not just documents the bind address: leaving it
# at streamable_http_app()'s default ("127.0.0.1") auto-enables DNS
# rebinding protection (allowed_hosts limited to 127.0.0.1/localhost/::1),
# which then rejects every request's real Host header once this is actually
# reachable over the internet via a Lambda Function URL -- discovered as a
# real "Invalid Host header" -> 421 in production, not assumed up front.
# DNS rebinding is a threat model for a LOCAL dev server a malicious
# webpage could redirect a browser to; it doesn't apply to a Lambda Function
# URL, which is only ever reached over its own real HTTPS hostname.
app = mcp.streamable_http_app(json_response=True, stateless_http=True, host="0.0.0.0")
