"""Allows `python -m meshcorectl` to behave like the `meshcorectl` console script."""

from meshcorectl.cli import main

if __name__ == "__main__":  # pragma: no cover - identical to cli.py's own entry-point guard
    main()
