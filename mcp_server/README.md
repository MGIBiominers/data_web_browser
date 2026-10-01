# mcp_server

Remote MCP server for the ALS EXTERNAL_DATASETS catalog: search studies and
samples, get comprehensive study/sample detail, understand what's actually
inside a specific processed file, get the real HTCF filesystem location of
processed data (not a download -- see below), assemble a filtered cohort's
files, and request a dataset that isn't in the collection yet. See
`../DESIGN.md`'s "MCP server" and "MCP server reactivated" sections for the
full architecture and design decisions.

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

## Gene presence index (tool disabled as of 2026-10-01, code kept)

`gene_presence` is **not currently registered in `server.py`** -- real
usage surfaced a design limitation worth fixing before exposing it again:
since this collection deposits exactly what each study's authors uploaded
with no filtering of our own, and standard RNA-seq quantification tools
report the *entire* reference-genome gene set regardless of actual
expression, a "present" result is close to tautological for any
whole-transcriptome study -- nearly every real human/mouse gene symbol
shows up as "present" in nearly every such study, whether or not it was
ever meaningfully detected there. The tool's one genuinely reliable signal
-- ruling a gene *out* for a targeted-panel study, or catching a
species-casing/Ensembl-ID mismatch -- wasn't judged enough on its own to
justify exposing it as a general-purpose gene search tool in its current
form. `tools/gene_presence.py` (including its 2026-09-30 batch-query
support, accepting a list of symbols in one call), its tests, and the
precomputed `gene_presence.json` artifact described below are all kept
as-is, not deleted -- a future version could surface each study's total
gene-panel size (or real detection) alongside presence so a caller can
tell a trivial reference-genome hit from a meaningful one. See
`DESIGN.md` for the full discussion.

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

**Real production incident, 2026-09-28, not a hypothetical:** the first
live deploy uploaded the plain 103MB JSON as-is. `gene_presence` then
timed out at 60s on every call -- confirmed via CloudWatch: a cold start
downloading + `json.loads()`-ing 103MB took longer than the Lambda's own
timeout, and crashed the AWS Lambda Web Adapter's Rust-side response
handling outright (a panic reading a response body that never finished),
not a clean Python error. Fixed by gzip-compressing the artifact before
upload -- **2.1MB** (a 49x reduction; this data is almost entirely
repeated `study_id` strings, which gzip handles extremely well) --
and having `catalog_cache.get_gene_presence()` explicitly `gzip.decompress()`
the S3 object body before parsing (S3/boto3 do not do this automatically;
`get_object` just returns whatever bytes are actually stored). Deploy step,
not something `build_gene_presence.py` itself does:

```bash
gzip -k -9 gene_presence.json   # -> gene_presence.json.gz
aws s3 cp gene_presence.json.gz s3://<bucket>/metadata/gene_presence.json
```

Verified live after the fix: a cold-start `gene_presence` call completes
in ~8s (well inside the timeout); a warm one in ~1.3s. Lambda `memory_size`
was also bumped 512 -> 1024MB and `timeout` 30 -> 60s (`infra/mcp.tf`) as
part of the same deploy, on general principle -- not proven necessary after
the gzip fix, but cheap insurance against a much bigger index in the
future.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

256 tests as of this writing, all against real dependencies (`mcp`,
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
3. Publish current metadata to `metadata/` in the bucket -- `catalog.json`/
   `samples.json` (a plain `aws s3 cp`, or a real non-`--dry-run`
   `pipeline/publish.py` run) and, if built, `gene_presence.json`
   (**gzip it first** -- see "Gene presence index" above; uncompressed
   broke the server outright the first time). This server doesn't need any
   study's actual data files in S3 at all -- `get_data_locations` points
   at HTCF, not S3.
4. Point MCP Inspector or the client snippet above at the real
   `mcp_function_url` Terraform output (path `/mcp`) instead of localhost.

**Current real state (2026-09-28+): local Terraform state for this infra
is gone** (see `DESIGN.md`'s "MCP server reactivated" section) -- running
`terraform apply` here blindly would try to create duplicate resources.
Until that's reconciled (`terraform import` first), updates go through
direct `aws` CLI calls instead of step 2 above:
```bash
# Code, staged through S3 -- a direct --zip-file body upload of anything
# beyond a few MB has repeatedly dropped the connection over a slow link;
# staging through S3 first is far more reliable for this package's ~26MB.
aws s3 cp mcp_lambda_deploy.zip s3://<bucket>/_lambda_deploy/mcp_lambda_deploy.zip
aws lambda update-function-code --function-name <fn> \
  --s3-bucket <bucket> --s3-key _lambda_deploy/mcp_lambda_deploy.zip
aws s3 rm s3://<bucket>/_lambda_deploy/mcp_lambda_deploy.zip   # don't leave it there

# Config (memory/timeout/env vars) and the execution role's inline policy
# need the same manual treatment -- see infra/mcp.tf for what they should
# match; `aws lambda update-function-configuration` and
# `aws iam put-role-policy` respectively.
```
