// Fetches catalog/sample metadata directly from S3/CloudFront at runtime --
// deliberately NOT bundled at build time. See ../../DESIGN.md: this is the
// mechanism behind "uploading new data updates the site right away" without
// any rebuild/redeploy. cache: 'no-store' plus a cache-busting query param
// means the browser never serves a stale copy out of its own HTTP cache
// even if the CloudFront invalidation is momentarily still in flight.

const METADATA_BASE = import.meta.env.VITE_METADATA_BASE_URL || '/data'

async function fetchJson(path) {
  const url = `${METADATA_BASE}/${path}?t=${Date.now()}`
  const res = await fetch(url, { cache: 'no-store' })
  if (!res.ok) {
    throw new Error(`Failed to fetch ${path}: ${res.status} ${res.statusText}`)
  }
  return res.json()
}

export function fetchCatalog() {
  return fetchJson('catalog.json')
}

export function fetchSamples() {
  return fetchJson('samples.json')
}
