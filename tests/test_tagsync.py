"""Tests for tagsync.py (v2: only find_similar_tag survives)."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "skills", "hbedit", "scripts"))

import tagsync


def test_exact_match_returns_none():
    assert tagsync.find_similar_tag("foo", ["foo", "bar"]) is None


def test_close_misspelling_returns_existing():
    assert tagsync.find_similar_tag("leetcod", ["leetcode", "other"]) == "leetcode"


def test_case_difference_is_caught():
    # Heptabase tags are case-sensitive; "Hbedit" vs "hbedit" would create
    # a near-duplicate, so we surface this.
    assert tagsync.find_similar_tag("Hbedit", ["hbedit"]) == "hbedit"


def test_far_returns_none():
    assert tagsync.find_similar_tag("xyz", ["completely-different-name"]) is None


def test_empty_existing():
    assert tagsync.find_similar_tag("anything", []) is None
