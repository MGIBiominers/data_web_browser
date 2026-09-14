# Ambient RNA correction (DecontX)

Many single-cell/single-nucleus files have had ambient RNA contamination
corrected using DecontX (chosen over alternatives like CellBender/SoupX
because it doesn't require the original empty-droplet/raw barcode data,
which isn't always available for externally-sourced datasets).

- Applied per sequencing batch/capture, keyed on `sample_id` in most
  studies (a couple use a different batch column -- documented per-study).
- Output: `layers["decontx_corrected"]` and `obs["decontx_contamination"]`
  added alongside the original `layers["raw"]`, which is never overwritten.
- Not every file has had this applied -- check `explain_data_file` for a
  specific file's actual status.
