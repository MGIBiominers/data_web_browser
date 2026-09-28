"""Integration-style tests for server.py.

server.py is pure composition/wiring code (create MCPServer, register 7
tools + 5 resources, build the ASGI app) -- the meaningful thing to verify
is that the real wiring actually works against the real `mcp` SDK, not that
internal calls happen in some mocked sequence.

Deliberately NOT mocking MCPServer/Path here: `mock.patch('server.X')`
resolves its target via `importlib.import_module('server')` if `server`
isn't already in sys.modules -- which means the patch's own target
resolution triggers a REAL, unpatched run of server.py's module-level code
(the real MCPServer, the real Path.glob() over resources/) BEFORE the mock
is swapped in. Every assertion against the mock then sees nothing, because
the real objects already did all the work. Patching the class at its
defining location instead (`mcp.server.mcpserver.MCPServer`) would dodge
that, but mocking `pathlib.Path` globally is its own hazard (it's used by
pytest/mock internals too). A real import plus real introspection avoids
the whole timing trap and tests something closer to what actually matters.
"""
from __future__ import annotations

import asyncio
import os

os.environ.setdefault("CATALOG_SOURCE", "local")
os.environ.setdefault("BUCKET_NAME", "test-bucket")

from starlette.applications import Starlette

import server

EXPECTED_TOOLS = {
    "search_studies", "get_study_overview", "search_samples",
    "get_sample_details", "explain_data_file", "get_data_locations",
    "request_dataset_download", "gene_presence", "build_cohort",
}
EXPECTED_RESOURCE_URIS = {
    "pipeline-docs://alignment_methodology",
    "pipeline-docs://bulk_rnaseq_schema",
    "pipeline-docs://decontx_methodology",
    "pipeline-docs://h5ad_schema",
    "pipeline-docs://sample_metadata_schema",
}


def test_server_name():
    assert server.mcp.name == "als-dataset-catalog"


def test_instructions_mention_key_tools_and_resources():
    instructions = server.mcp.instructions
    for name in ("search_studies", "search_samples", "get_data_locations", "request_dataset_download"):
        assert name in instructions
    assert "pipeline-docs://" in instructions


def test_all_seven_tools_registered():
    tools = asyncio.run(server.mcp.list_tools())
    assert {t.name for t in tools} == EXPECTED_TOOLS


def test_tool_descriptions_come_from_docstrings():
    """Confirms the mcp SDK is actually reading each function's docstring
    as its description (rather than e.g. registering with no description),
    since that's the mechanism the whole "give each tool a rich
    description" requirement (from the approved plan) relies on."""
    tools = asyncio.run(server.mcp.list_tools())
    by_name = {t.name: t for t in tools}
    assert "Search the ALS/neurodegeneration dataset catalog" in by_name["search_studies"].description
    assert "queue" in by_name["request_dataset_download"].description.lower()


def test_all_five_resources_registered():
    resources = asyncio.run(server.mcp.list_resources())
    assert {str(r.uri) for r in resources} == EXPECTED_RESOURCE_URIS


def test_resource_names_replace_underscores_with_spaces():
    resources = asyncio.run(server.mcp.list_resources())
    by_uri = {str(r.uri): r for r in resources}
    assert by_uri["pipeline-docs://h5ad_schema"].name == "h5ad schema"
    assert by_uri["pipeline-docs://sample_metadata_schema"].name == "sample metadata schema"


def test_resource_mime_type_is_markdown():
    resources = asyncio.run(server.mcp.list_resources())
    assert all(r.mime_type == "text/markdown" for r in resources)


def test_resource_description_references_this_collection():
    resources = asyncio.run(server.mcp.list_resources())
    assert all("this collection's data is structured and processed" in r.description for r in resources)


def test_resource_reader_returns_real_file_content():
    """Each resource's reader must actually read ITS OWN file -- this is
    exactly what the _make_reader factory-closure exists to guarantee
    (a naive default-argument closure over the loop variable would also
    work for lookup, but mcp.resource() rejects any declared parameter on a
    non-templated resource -- see _make_reader's docstring)."""
    content = asyncio.run(server.mcp.read_resource("pipeline-docs://h5ad_schema"))
    assert "layers[\"raw\"]" in content[0].content
    assert content[0].mime_type == "text/markdown"

    other = asyncio.run(server.mcp.read_resource("pipeline-docs://decontx_methodology"))
    assert "DecontX" in other[0].content
    assert "obs columns" not in other[0].content  # h5ad_schema-specific phrasing


def test_app_is_a_starlette_asgi_app():
    assert isinstance(server.app, Starlette)
