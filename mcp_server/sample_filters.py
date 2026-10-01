"""Shared sample-matching logic for search_samples.py and build_cohort.py.

Case-insensitive, and prefers a field's canonical vocabulary column (when
one exists and is populated for a given sample) over its raw counterpart.
Fixes two real reported bugs, not hypothetical ones:

1. `sex` mixes "Male"/"male" and "Female"/"female" casing in the raw data
   (confirmed directly: 468 "Male" + 234 "male", 375 "Female" + 126
   "female" in the real collection) -- a case-sensitive exact match on a
   single casing silently misses roughly a third of the matching samples.
2. `tissue_or_cell_type` has ~90 raw spelling variants for a much smaller
   set of real anatomical regions -- e.g. "motor cortex", "lateral motor
   cortex", "Cortex_Motor_BA4", "Cortex Motor Lateral", and
   "post-mortem tissue; Motor Cortex (Lateral)" all describe real, already-
   distinguished motor cortex regions. HTCF's own vocabulary pass already
   collapses these into a clean ~35-value `tissue` column (e.g.
   "Motor Cortex (BA4)", "Motor Cortex (Lateral)") -- this was simply never
   queried by search_samples before now. Querying the canonical column
   directly fixes this with no new vocabulary work of our own.

The raw-field fallback matters because not every sample has a populated
canonical value -- e.g. cell-culture entries like "iPSC-derived motor
neuron cultures" have no anatomical `tissue` bucket at all. Falling back to
the raw field only when the canonical one is null keeps those samples
reachable rather than silently dropping them from every tissue-filtered
search.
"""
from __future__ import annotations


def _norm(value: object) -> str | None:
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def matches(sample: dict, query: str | None, field: str, fallback_field: str | None = None) -> bool:
    """True if `query` case-insensitively equals `sample[field]`, or --
    only when that canonical value is missing/empty -- `sample[fallback_field]`.
    An unset query (None, empty, or whitespace-only) always matches, same as
    every filter param's existing "don't filter on this" semantics.
    """
    q = _norm(query)
    if q is None:
        return True
    value = _norm(sample.get(field))
    if value is None and fallback_field:
        value = _norm(sample.get(fallback_field))
    return value == q
