"""Shared helper for building MCP tool responses.

Every tool must put its full result data directly in a text content block,
not only in structured_content. Confirmed via real-world use (not just
theory): a real MCP client connected to this server surfaced only the
one-line summary from `content` for every tool call -- it never showed
structured_content at all. The MCP spec treats structured_content as an
optional, additional machine-readable mirror of the result; `content` is
the channel a calling model is actually guaranteed to see. A tool that puts
its real payload ONLY in structured_content is betting on every client
choosing to forward it to the model, which isn't a safe bet -- and wasn't
true for the client actually used.

The fix: always serialize the same data that goes into structured_content
into the text block too, so the result is visible regardless of what a
given client does with structured_content. structured_content is still
set, for clients that do use it.
"""
from __future__ import annotations

import json

from mcp.types import CallToolResult, ContentBlock, TextContent


def build_result(
    summary: str,
    data: dict,
    extra_content: list[ContentBlock] | None = None,
) -> CallToolResult:
    """Build a CallToolResult whose content is self-sufficient.

    Args:
        summary: a short, human-readable first line (e.g. "Found 3 matching
            studies.").
        data: the full result -- the same dict also set as structured_content,
            serialized as JSON directly beneath the summary line.
        extra_content: additional content blocks to append (e.g. resource
            links from resource_links.py).

    Returns:
        A CallToolResult with one TextContent block (summary + full JSON
        data) followed by any extra_content, and structured_content set to
        `data` for clients that do use it.
    """
    text = f"{summary}\n\n{json.dumps(data, indent=2, default=str)}"
    content: list[ContentBlock] = [TextContent(type="text", text=text)]
    if extra_content:
        content.extend(extra_content)
    return CallToolResult(content=content, structured_content=data)
