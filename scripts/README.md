# Developer scripts

Small utilities used during development and release. They are **not**
part of the installed application and are deliberately excluded from
`pyproject.toml`'s `py-modules` list.

| Script | Purpose |
| --- | --- |
| `bump_version.py` | Read or update the project version in `version.py`. The Zenodo / pyproject metadata pull from that single file. |

## `bump_version.py`

```bash
# Show the current version
python scripts/bump_version.py

# Bump SemVer components in place
python scripts/bump_version.py --patch   # 1.2.0 -> 1.2.1
python scripts/bump_version.py --minor   # 1.2.0 -> 1.3.0
python scripts/bump_version.py --major   # 1.2.0 -> 2.0.0

# Set an explicit version (e.g. for release candidates)
python scripts/bump_version.py --set 1.2.3
```

The script writes to `version.py` at the project root and prints the
old → new transition. Downstream code (`controllers/app_controller.py`,
`packaging/build_*_optimized.py`, exported CSV provenance, the dynamic
``version`` in `pyproject.toml`, etc.) reads `version.__version__` so
nothing else needs to be touched manually.
