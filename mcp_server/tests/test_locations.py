"""Tests for locations.py"""
from locations import HTCF_ROOT_DEFAULT, RIS_ROOT_DEFAULT, get_roots, processed_dirs, roots_note


def test_get_roots_uses_catalog_roots():
    roots = get_roots({"roots": {"htcf": "/a", "ris": "/b"}})
    assert roots == {"htcf": "/a", "ris": "/b"}


def test_get_roots_old_catalog_uses_source_root_and_default_ris():
    roots = get_roots({"source_root": "/old/htcf"})
    assert roots == {"htcf": "/old/htcf", "ris": RIS_ROOT_DEFAULT}


def test_get_roots_empty_catalog_uses_defaults():
    assert get_roots({}) == {"htcf": HTCF_ROOT_DEFAULT, "ris": RIS_ROOT_DEFAULT}


def test_processed_dirs_same_relative_layout_and_no_double_slash():
    dirs = processed_dirs({"htcf": "/a/", "ris": "/b"}, "S1")
    assert dirs == {"htcf": "/a/studies/S1/processed/", "ris": "/b/studies/S1/processed/"}


def test_roots_note_mentions_every_root():
    note = roots_note({"htcf": "/a", "ris": "/b"})
    assert "/a" in note and "/b" in note and "identical layout" in note
