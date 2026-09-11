"""Covers the one executable line in __main__.py: the `from ... import main`
that makes `python -m meshcorectl` resolve to the same entry point as the
`meshcorectl` console script. The `if __name__ == "__main__":` guard below
it is excluded from coverage (see the module) since it only runs when
invoked as a script, which `main()`'s own behavior is already tested
directly in tests/commands/test_cli_root.py.
"""

from __future__ import annotations


def test_dunder_main_module_imports_cleanly():
    import meshcorectl.__main__ as entry

    assert callable(entry.main)
