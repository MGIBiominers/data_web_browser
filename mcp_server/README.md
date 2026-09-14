# mcp_server

**Deprecated (2026-09-14).** No longer under active development or use --
kept in the repo for reference only. See `../DESIGN.md`'s "MCP server
deprecated" section. The AWS Lambda deployment described below is being
torn down; don't assume the Function URL still resolves.

Remote MCP server for the ALS EXTERNAL_DATASETS catalog: search studies and
samples, get comprehensive study/sample detail, understand what's inside a
specific processed file, get S3 download links, and request a dataset that
isn't in the collection yet. See `../DESIGN.md`'s "MCP server" section for
the full architecture and design decisions.

## Local development

```bash
cd mcp_server
python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest

# Run against local fixture JSON instead of S3 (see fixtures/):
CATALOG_SOURCE=local CATALOG_LOCAL_DIR=./fixtures \
  BUCKET_NAME=<any-placeholder> PRESIGN_CREDENTIALS_PARAM=<any-placeholder> \
  .venv/bin/python -m uvicorn server:app --port 8123
```

Anything that doesn't touch S3 (`search_studies`, `get_study_overview`,
`search_samples`, `get_sample_details`, `explain_data_file`, and reading
resources) works fully against the local fixtures with no AWS credentials
at all. `get_download_links` and `request_dataset_download` need a real
bucket and a real SSM parameter to actually complete — against fixtures/no
AWS they'll fail with a real `ParameterNotFound`/similar error at the exact
point real infrastructure is required, which is the expected boundary until
`infra/mcp.tf` is applied.

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
[Zelic2025_Immunity], a bulk-only study, and the one access-restricted
dbGaP study) -- not synthetic data. `Zelic2025_Immunity`'s processed files
have hand-added `s3_key`/`sha256` values (no real sync has happened yet) so
`get_download_links`' direct-mode path has something realistic to presign
against once real AWS credentials are available.

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

222 tests as of this writing, all against real dependencies (`mcp`,
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
   URL, both IAM identities, and the manifest-expiration lifecycle rule --
   see `mcp.tf`'s header comment). Needs `lambda_web_adapter_layer_arn` set
   to the current layer ARN from
   https://github.com/awslabs/aws-lambda-web-adapter/releases.
3. One-time manual step (never automated -- see `mcp.tf`): create the
   presign IAM user's access key and seed it into the SSM parameter
   Terraform created as a placeholder.
   ```bash
   aws iam create-access-key --user-name <mcp_presign_user_name output>
   aws ssm put-parameter --name <mcp_presign_credentials_param output> \
     --type SecureString --overwrite \
     --value '{"access_key_id": "...", "secret_access_key": "..."}'
   ```
4. Run a real (non-`--dry-run`) `pipeline/publish.py` for at least one
   study so there's real data in the bucket to search/download.
5. Point MCP Inspector or the client snippet above at the real
   `mcp_function_url` Terraform output (path `/mcp`) instead of localhost.
