"""Quick environment sanity probe for the build process."""
import sys
print("python:", sys.version.split()[0], sys.executable)
for name in ("numpy", "scipy", "pingouin", "krippendorff", "filetype", "av", "PySide6", "pandas", "matplotlib", "statsmodels"):
    try:
        mod = __import__(name)
        ver = getattr(mod, "__version__", "?")
        print(f"  [OK]   {name} {ver}")
    except Exception as exc:
        print(f"  [MISS] {name}: {exc!r}")
