# ALS Dataset Browser (data_web_browser)

Searchable web browser over the ALS pipeline's dataset collection at
`/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS`, plus the pipeline
that publishes processed data + metadata to S3. See `DESIGN.md` for the
full architecture and file-by-file guide.

## Quickstart

All commands below run on HTCF (`/lts` is only mounted on the login node).
Use the project's own Python — the system `python3` is too old (3.6.8):

```
PY=/ref/rmlab/software/azamat/als_pipeline_env/bin/python3
ROOT=/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS
COORD=/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination
```

### Build the catalog (read-only, no AWS needed)

```
cd pipeline
$PY build_catalog.py --root $ROOT --coordination-root $COORD --out-dir /tmp/dwb_out
```

Writes `catalog.json`, `samples.json`, `last_updated.json` to `/tmp/dwb_out`.

### Preview what would be synced to S3 (dry run, no AWS calls)

```
$PY s3_sync.py --root $ROOT --coordination-root $COORD \
    --bucket <bucket-name> --out-dir /tmp/dwb_out --dry-run
```

Check `/tmp/dwb_out/s3_sync_skip_log.json` for exactly why any study was
excluded.

### Run the pipeline's own tests

```
cd pipeline
python3 -m pytest tests/ -q
```

### Publish for real (needs a provisioned bucket + AWS credentials)

```
$PY publish.py --root $ROOT --coordination-root $COORD \
    --bucket <bucket-name> --distribution-id <cloudfront-id> \
    --out-dir /tmp/dwb_out
```

### Run the web app locally

```
cd web
npm install
npm run build      # or: npm run dev
```

The app fetches `catalog.json`/`samples.json` from `VITE_METADATA_BASE_URL`
(set it to your CloudFront URL's `/metadata` path once deployed). For local
testing without a real bucket, copy generated JSON into `web/public/data/`
and it'll be served at the default `/data` path.

### Provision AWS infrastructure

```
cd infra
terraform init
terraform apply -var="bucket_name=<your-globally-unique-name>"
```

**Not yet done** — see `DESIGN.md`'s "Not yet done" section. Requires
choosing a real bucket name/region first.
