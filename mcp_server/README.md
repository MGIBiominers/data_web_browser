# mcp_server

Remote MCP server for the ALS EXTERNAL_DATASETS catalog: search studies and
samples, get comprehensive study/sample detail, understand what's actually
inside a specific processed file, get the real HTCF filesystem location of
processed data (not a download -- see below), and request a dataset that
isn't in the collection yet. See `../DESIGN.md`'s "MCP server" and "MCP
server reactivated" sections for the full architecture and design
decisions.

**This server never transfers file contents.** `get_data_locations` (added
2026-09-18, replacing the earlier `get_download_links`) only ever returns
the real HTCF path where a study's processed data already lives -- useful
to someone with HTCF filesystem access (a lab member, or a Claude Code
session running on HTCF), not a way to fetch the data through this server
itself. There is no presigning, no S3 download URLs, and no manifest
files anymore.

## Local development

```bash
cd mcp_server
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest

# Run against local fixture JSON instead of S3 (see fixtures/):
CATALOG_SOURCE=local CATALOG_LOCAL_DIR=./fixtures \
  BUCKET_NAME=<any-placeholder> \
  .venv/bin/python -m uvicorn server:app --port 8123
```

Everything except `request_dataset_download` works fully against the local
fixtures with no AWS credentials at all (`get_data_locations` reads paths
straight out of the cached catalog JSON -- no S3 call involved).
`request_dataset_download` needs a real bucket to actually write the
request queue file; against fixtures/no AWS it'll fail with a real
`NoSuchBucket`/similar error at the exact point real infrastructure is
required, which is the expected boundary until `infra/mcp.tf` is applied.

Drive it with the real MCP client SDK (not curl -- Streamable HTTP's
session handshake makes hand-rolled JSON-RPC fragile):

```python
import asyncio
from mcp.client.streamable_http import streamable_http_client
from mcp.client.session import ClientSession

async def main():
    async with streamable_http_client("http://127.0.0.1:8123/mcp") as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(await session.list_tools())
            print(await session.call_tool("search_studies", {"query": "ALS"}))

asyncio.run(main())
```

`fixtures/catalog.json`/`fixtures/samples.json` are a trimmed real slice of
the actual HTCF collection (3 studies: a normal single-cell+bulk study
[Zelic2025_Immunity], a bulk-only study, and one dbGaP-restricted study) --
not synthetic data.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

229 tests as of this writing, all against real dependencies (`mcp`,
`boto3`) with only their I/O-performing methods mocked -- see
`conftest.py` for the sys.path setup that makes bare imports
(`import catalog_cache`, `import search_studies`, etc.) resolve the same
way they do in the real Lambda deployment.

## Deploying

1. `./build.sh` -- installs manylinux/x86_64 wheels (matters: a plain
   `pip install` on a Mac bundles an incompatible `pydantic_core` binary
   that only fails at Lambda cold start) into `build/`, then copies the
   source files in.
2. From `../infra/`: `terraform apply` (creates the Lambda, its Function
   URL, and its execution role -- see `mcp.tf`'s header comment). Needs
   `lambda_web_adapter_layer_arn` set to the current layer ARN from
   https://github.com/awslabs/aws-lambda-web-adapter/releases.
3. Run a real (non-`--dry-run`) `pipeline/publish.py` for at least one
   study so there's real metadata in the bucket to search against (this
   server reads `metadata/catalog.json`/`metadata/samples.json` from S3;
   it doesn't need any study's actual data files to be in S3 at all, since
   `get_data_locations` points at HTCF, not S3).
4. Point MCP Inspector or the client snippet above at the real
   `mcp_function_url` Terraform output (path `/mcp`) instead of localhost.
