# mcp_server

Remote MCP server for the ALS EXTERNAL_DATASETS catalog: search studies and
samples, get comprehensive study/sample detail, understand what's actually
inside a specific processed file, get the real HTCF filesystem location of
processed data (not a download -- see below), check whether a gene was even
measured anywhere in the collection, assemble a filtered cohort's files, and
request a dataset that isn't in the collection yet. See `../DESIGN.md`'s
"MCP server" and "MCP server reactivated" sections for the full architecture
and design decisions.

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
not synthetic data. `fixtures/gene_presence.json` is small hand-written
data matching those same study_ids (the real one is 103MB -- see
"Gene presence index" below for why it's not just a bigger fixture).
`gene_presence` itself works fine with no `gene_presence.json` present at
all -- `catalog_cache.get_gene_presence()` returns an empty index rather
than erroring, so every other tool stays testable without it.

## Gene presence index

`gene_presence` is the one tool that doesn't read `catalog.json`/
`samples.json` directly -- it reads a separate precomputed artifact,
`metadata/gene_presence.json`, built by a **different** script,
`pipeline/build_gene_presence.py`. That script needs a real scientific-
Python environment (h5py + pyarrow, to open actual `.h5ad`/`.parquet` files
and read their gene axis) -- `build_catalog.py`'s stdlib-only environment
can't run it. On HTCF, use the same environment `conversion` already relies
on:

```bash
/ref/rmlab/software/azamat/als_pipeline_env/bin/python3 pipeline/build_gene_presence.py \
  --root /lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS \
  --out gene_presence.json
```

Real numbers as of 2026-09-28: 78 processed files (h5ad + gene-level bulk
parquet only -- transposable-element/splicing/transcript-level files are
deliberately excluded, see the script's own docstring), 513,091 distinct
gene identifiers / 592,533 (gene, study, id_type) entries / **103MB** of
output, ~6 minutes wall time (almost entirely NFS I/O waiting on HTCF's
filesystem, not CPU -- reading only each file's gene axis via `h5py`
directly, never the actual expression matrix, is what keeps this feasible
at all: the same read took 0.05s on a 4.6GB h5ad file). **A first version
of this script was study-per-file rather than study-level, producing 512MB
of output -- large enough that a parsed copy in Lambda's memory would have
exceeded the function's own 512MB memory limit before answering a single
query.** Collapsing to one entry per (gene, study, id_type) rather than
(gene, file) fixed it (5x smaller); see the script's docstring for the
full story.

**Still worth a look before this goes live**: 103MB parsed into Python
objects typically runs 1.5-2.5x larger in memory than its raw JSON size --
close enough to the Lambda's current 512MB `memory_size`
(`infra/mcp.tf`) to be worth bumping that up (e.g. to 1024MB) as part of
whatever deploy actually publishes this artifact, rather than assuming
it'll fit. Not yet a proven problem, just not proven safe either --
nobody's actually run this inside the Lambda yet.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

250 tests as of this writing, all against real dependencies (`mcp`,
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
