#!/usr/bin/env python3
"""Shared helpers for compact RABET desktop application builds."""

import importlib.util
import shutil
import subprocess
import sys
import tarfile
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path

# The build scripts live in ``packaging/`` so the project root must be on
# ``sys.path`` for ``from version import __version__`` (and any other
# project-root imports) to resolve when this module is loaded.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from version import __version__

APP_NAME = "RABET"
APP_VERSION = __version__
APP_DESCRIPTION = "Real-time Animal Behavior Event Tagger"
# Project root (one level up from this packaging script).
ROOT_DIR = _PROJECT_ROOT

CORE_DEPENDENCIES = [
    "PySide6",
    # 1.3.1: python-vlc replaced by PyAV (FFmpeg python bindings). PyAV's
    # wheels ship a bundled FFmpeg build, so no system video runtime is
    # required at install or run time on Win/macOS/Linux.
    "av",
    "shiboken6",
]

RUNTIME_DEPENDENCIES = [
    "numpy",
    "pandas",
    "matplotlib",
    "Pillow",
]

BUILD_DEPENDENCIES = [
    "PyInstaller>=6.0.0",
]

PACKAGE_IMPORT_NAMES = {
    "av": "av",
    "Pillow": "PIL",
    "PyInstaller": "PyInstaller",
}

HIDDEN_DEPENDENCIES = [
    # PyAV exposes a top-level ``av`` plus several submodules that
    # PyInstaller's static analyser often misses (they're imported
    # dynamically when the user opens a video).
    "av",
    "av.video",
    "av.audio",
    "av.container",
    "av.codec",
    "av.error",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_svg",
    "matplotlib.backends.backend_pdf",
    "PIL",
    "PIL.Image",
    # 1.3.2: pingouin powers the in-app Reliability tab. It pulls in
    # scipy/statsmodels which were previously in the excludes list -
    # the excludes have been updated below to let them through.
    "pingouin",
    "scipy",
    "scipy.stats",
    "scipy.special",
    "statsmodels",
    "statsmodels.api",
    # Krippendorff's alpha is provided by the standalone krippendorff
    # package; pingouin 0.5.x no longer exposes it.
    "krippendorff",
    # 1.3.2: filetype is used by utils.video_detection for magic-number
    # sniffing of dropped video files whose extension is unusual.
    "filetype",
    # 1.3.3: scipy 1.13+ pulls in array_api_compat which iterates
    # ``dir(numpy)`` and triggers numpy's lazy loader for ``f2py``.
    # Even though RABET never calls f2py, the submodule must be in
    # the bundle or ``import pingouin`` fails at the Reliability tab.
    "numpy.f2py",
    # 1.3.2: pingouin's top-level ``__init__.py`` does
    # ``from .plotting import *`` (which loads seaborn) and several
    # helpers rely on pandas_flavor's @register_* decorators. Both are
    # listed here so PyInstaller pulls them into the bundle - excluding
    # them caused ``import pingouin`` to raise ImportError, which the
    # Reliability tab silently swallowed.
    "seaborn",
    "pandas_flavor",
]

COMMON_EXCLUDED_MODULES = [
    "PyQt5",
    "PyQt6",
    "tkinter",
    "wx",
    "gtk",
    # NOTE (1.3.2): scipy / statsmodels / sklearn were previously listed
    # here to keep the bundle small, but pingouin (used by the Reliability
    # tab) depends on scipy and statsmodels. They are now intentionally
    # NOT excluded so that the bundled pingouin can import them. sklearn
    # remains excluded because pingouin only uses it in functions we do
    # not call from the Reliability tab.
    "sklearn",
    # seaborn cannot be excluded: pingouin's __init__ pulls in
    # pingouin.plotting which imports seaborn at module load time.
    # If seaborn is excluded, the whole pingouin namespace fails to
    # import and the Reliability tab quietly falls back to None.
    "tensorflow",
    "torch",
    "keras",
    "xgboost",
    "lightgbm",
    "cv2",
    "opencv-python",
    "django",
    "flask",
    "fastapi",
    "tornado",
    "aiohttp",
    "requests",
    "urllib3",
    "boto3",
    "botocore",
    "azure",
    "google",
    "pytest",
    "nose",
    "sphinx",
    "IPython",
    "jupyter",
    "notebook",
    "ipykernel",
    "black",
    "flake8",
    "mypy",
    "pylint",
    "sqlalchemy",
    "alembic",
    "psycopg2",
    "pymongo",
    "mysql",
    "h5py",
    "sympy",
    "dask",
    "numba",
    "bokeh",
    "panel",
    "imageio",
    "docutils",
    "babel",
    # NOTE: ``distutils`` cannot be excluded because PyInstaller 6.x's
    # pre-safe-import hook ``hook-distutils.py`` aliases setuptools'
    # vendored copy to ``distutils`` and chokes if the name is already
    # marked as excluded.
    "lib2to3",
    "ensurepip",
    "venv",
    "turtledemo",
    "test",
    "tests",
    "testing",
    "pip",
    "wheel",
    # ---------------------------------------------------------------- #
    # 1.3.2: scipy sub-modules that pingouin's ICC path does NOT touch.
    # Excluding the rest shaves ~40 MB off the PyInstaller bundle.
    #
    # IMPORTANT: pingouin actually loads scipy.cluster, scipy.constants,
    # scipy.fft, scipy.integrate, scipy.interpolate, scipy.ndimage,
    # scipy.sparse.linalg and scipy.spatial through its
    # ``import pingouin`` chain (verified with
    # ``tools/probe_pingouin_imports.py``), so these are NOT in the
    # exclude list any more. Excluding them caused
    # ``import pingouin`` to raise inside the bundled exe and the
    # Reliability tab silently fell back to None for every metric.
    # ---------------------------------------------------------------- #
    "scipy.signal",
    "scipy.fftpack",
    "scipy.misc",
    "scipy.odr",
    "scipy.io",
    "scipy.datasets",
    "statsmodels.tsa",
    "statsmodels.graphics",
    "statsmodels.formula",
    "statsmodels.imputation",
    "statsmodels.duration",
    "statsmodels.discrete",
    "statsmodels.emplike",
    "statsmodels.gam",
    "statsmodels.multivariate",
    "statsmodels.nonparametric",
    "statsmodels.sandbox",
    "statsmodels.miscmodels",
    "statsmodels.othermod",
    "statsmodels.genmod",
    "statsmodels.distributions",
    "statsmodels.examples",
    "statsmodels.datasets",
    "statsmodels.stats.contingency_tables",
    "statsmodels.stats.libqsturng",
    # NOTE: pingouin.plotting and pingouin.datasets cannot be excluded
    # even though we never call into them at runtime, because
    # ``pingouin/__init__.py`` does ``from .plotting import *`` and
    # ``from .datasets import *`` unconditionally. Excluding them
    # raises ``ImportError`` on ``import pingouin``, which silently
    # kills every ICC computation in the Reliability tab.
    # ---------------------------------------------------------------- #
    # 1.3.2: pandas drags in pyarrow / lxml / tables / cryptography on
    # the conda anaconda channel, but RABET only uses pandas' core CSV
    # I/O and DataFrame operations. Strip the optional storage / parser
    # backends, ~25 MB saved.
    # ---------------------------------------------------------------- #
    "pyarrow",
    "tables",
    "lxml",
    "cryptography",
    "distributed",
    "zstandard",
    "xlrd",
    "openpyxl",
    "xlsxwriter",
    # ``numpy.distutils`` is build-time only and safe to exclude.
    # NOTE (1.3.3 fix): do NOT exclude ``numpy.f2py``. scipy 1.13+ uses
    # ``array_api_compat``, which iterates ``dir(numpy)`` at import time
    # and triggers numpy's lazy loader for every attribute. Excluding
    # ``numpy.f2py`` makes that getattr raise ModuleNotFoundError, which
    # crashes the whole ``import pingouin`` chain when the user opens
    # the Reliability tab in the bundled exe.
    "numpy.distutils",
]

PYSIDE_EXCLUDED_MODULES = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNetworkAuth",
    "PySide6.QtNfc",
    "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets",
    "PySide6.QtPdf",
    "PySide6.QtPdfWidgets",
    "PySide6.QtPositioning",
    "PySide6.QtQml",
    "PySide6.QtQuick",
    "PySide6.QtQuickControls2",
    "PySide6.QtQuickWidgets",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtSvgWidgets",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebChannel",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineQuick",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebSockets",
    "PySide6.QtWebView",
]

COMMON_BINARY_EXCLUDE_PATTERNS = [
    "Qt6Charts",
    "Qt6DataVisualization",
    "Qt6Designer",
    "Qt6Help",
    "Qt6HttpServer",
    "Qt6Location",
    "Qt6Multimedia",
    "Qt6NetworkAuth",
    "Qt6OpenGL",
    "Qt6Pdf",
    "Qt6Positioning",
    "Qt6Qml",
    "Qt6Quick",
    "Qt6QuickControls2",
    "Qt6QuickTemplates2",
    "Qt6RemoteObjects",
    "Qt6Scxml",
    "Qt6Sensors",
    "Qt6Serial",
    "Qt6Sql",
    "Qt6StateMachine",
    "Qt6Test",
    "Qt6TextToSpeech",
    "Qt6Web",
    "qmltooling",
    # ---------------------------------------------------------------- #
    # 1.3.2: Intel MKL is dragged in by the conda anaconda numpy build
    # and explodes the bundle by ~500 MB. ICC / kappa / alpha do not
    # require MKL - numpy / scipy fall back to their own portable BLAS.
    # Strip every mkl_*.dll. The patterns below match the actual file
    # names PyInstaller emits.
    # ---------------------------------------------------------------- #
    "mkl_",
    "libmkl_",
    # NumPy ships its own copies of these in pip wheels; the conda
    # build links against the MKL ones above, which we just dropped.
    "libiomp5md",
]


def get_import_name(package_name):
    """Return the importable module name for a pip package."""
    base_name = package_name.split(">=", 1)[0]
    return PACKAGE_IMPORT_NAMES.get(base_name, base_name.replace("-", "_"))


def is_package_available(package_name):
    """Check whether the import target for a package is available."""
    try:
        return importlib.util.find_spec(get_import_name(package_name)) is not None
    except ModuleNotFoundError:
        return False


def parse_version(version_text):
    """Parse a version into a tuple good enough for build-tool checks."""
    parts = []
    for raw_part in version_text.replace("-", ".").split("."):
        digits = ""
        for char in raw_part:
            if not char.isdigit():
                break
            digits += char
        parts.append(int(digits or 0))

    while len(parts) < 3:
        parts.append(0)

    return tuple(parts[:3])


def is_minimum_version_available(package_name, minimum_version):
    """Check an installed package version without adding a packaging dependency."""
    try:
        installed_version = package_version(package_name)
    except PackageNotFoundError:
        return False

    return parse_version(installed_version) >= parse_version(minimum_version)


def install_package(package_name):
    """Install a package into the current Python environment."""
    print(f"Installing dependency: {package_name}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])


def install_build_dependencies():
    """Install only dependencies that are missing from the active environment."""
    for dependency in BUILD_DEPENDENCIES:
        if ">=" in dependency:
            package_name, minimum_version = dependency.split(">=", 1)
            if is_minimum_version_available(package_name, minimum_version):
                print(f"Dependency available: {dependency}")
            else:
                install_package(dependency)
        elif is_package_available(dependency):
            print(f"Dependency available: {dependency}")
        else:
            install_package(dependency)

    for dependency in CORE_DEPENDENCIES + RUNTIME_DEPENDENCIES:
        if is_package_available(dependency):
            print(f"Dependency available: {dependency}")
        else:
            install_package(dependency)


def ensure_required_files():
    """Validate and create small runtime assets that the build expects."""
    if not (ROOT_DIR / "main.py").exists():
        raise FileNotFoundError("main.py was not found. Run this script from the RABET root.")

    try:
        sys.path.insert(0, str(ROOT_DIR))
        from utils.config_path_manager import ConfigPathManager

        ConfigPathManager().ensure_default_configs()
    except Exception as exc:
        print(f"Warning: could not validate default configs before build: {exc}")

    resources_dir = ROOT_DIR / "resources"
    if not resources_dir.exists():
        raise FileNotFoundError("resources directory was not found.")


def get_excluded_modules(extra_excludes=None, explicit_includes=None):
    """Build a stable module exclusion list with user overrides."""
    excluded = list(dict.fromkeys(COMMON_EXCLUDED_MODULES + PYSIDE_EXCLUDED_MODULES))

    for module in extra_excludes or []:
        if module not in excluded:
            excluded.append(module)

    for module in explicit_includes or []:
        if module in excluded:
            excluded.remove(module)

    return excluded


def get_data_files(include_ico=True, include_icns=True, include_png=True):
    """Return minimal PyInstaller data tuples for configs and app icons."""
    datas = []
    configs_dir = ROOT_DIR / "configs"
    if configs_dir.exists():
        datas.append((str(configs_dir), "configs"))

    resources_dir = ROOT_DIR / "resources"
    icon_names = []
    if include_ico:
        icon_names.append("RABET.ico")
    if include_icns:
        icon_names.append("RABET.icns")

    for icon_name in icon_names:
        icon_path = resources_dir / icon_name
        if icon_path.exists():
            datas.append((str(icon_path), "resources"))

    if include_png:
        png_icon = ROOT_DIR / "images" / "RABET.png"
        if png_icon.exists():
            datas.append((str(png_icon), "resources"))

    # Extra UI resources that aren't app icons but are loaded at runtime
    # (e.g. the Analysis-tab drop-zone CSV icon).
    for extra_name in ("csvicon.png",):
        extra_path = resources_dir / extra_name
        if extra_path.exists():
            datas.append((str(extra_path), "resources"))

    return datas


def prepare_build_dirs(skip_clean=False):
    """Prepare PyInstaller build and dist directories."""
    build_dir = ROOT_DIR / "build"
    dist_dir = ROOT_DIR / "dist"

    if not skip_clean:
        for path in (build_dir, dist_dir):
            if path.exists():
                print(f"Removing previous build output: {path}")
                shutil.rmtree(path)

    build_dir.mkdir(exist_ok=True)
    dist_dir.mkdir(exist_ok=True)
    return build_dir, dist_dir


def write_vlc_runtime_hook(path, platform_key):
    """Deprecated since 1.3.1.

    The legacy hook helped python-vlc find an externally installed VLC
    by setting ``VLC_PLUGIN_PATH`` / ``DYLD_LIBRARY_PATH`` at startup.
    The PyAV backend doesn't need anything similar: PyAV's wheel embeds
    its own FFmpeg shared libraries inside ``site-packages/av/`` and
    PyInstaller picks them up automatically via ``--collect-all=av``
    (or the equivalent ``--add-binary`` flags in each platform script).

    This function is kept as a stub so callers added before the
    migration don't break — it simply removes any previously generated
    hook file and returns the path.
    """
    _ = platform_key  # unused on purpose
    path = Path(path)
    if path.exists():
        try:
            path.unlink()
        except OSError:
            pass
    return path


def copy_runtime_assets(target_dir, include_ico=True, include_icns=True, include_png=True):
    """Copy tiny runtime assets next to the built app for robust path lookup."""
    target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    source_configs = ROOT_DIR / "configs"
    if source_configs.exists():
        destination = target_dir / "configs"
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(source_configs, destination)

    source_resources = ROOT_DIR / "resources"
    if source_resources.exists():
        destination = target_dir / "resources"
        destination.mkdir(exist_ok=True)
        icon_names = []
        if include_ico:
            icon_names.append("RABET.ico")
        if include_icns:
            icon_names.append("RABET.icns")

        for icon_name in icon_names:
            source_file = source_resources / icon_name
            if source_file.exists():
                shutil.copy2(source_file, destination / icon_name)

        if include_png:
            png_icon = ROOT_DIR / "images" / "RABET.png"
            if png_icon.exists():
                shutil.copy2(png_icon, destination / "RABET.png")

        # NOTE: csvicon.png is intentionally NOT copied here. It is
        # bundled *inside* the PyInstaller archive via get_data_files()
        # (extracted to sys._MEIPASS at runtime), so it must not also
        # appear as a loose file in the visible resources/ folder.


def write_readme(target_dir, platform_label):
    """Write user-facing runtime notes into a distribution folder."""
    platform_key = platform_label.lower()
    first_run_note = (
        "Important: When running for the first time, the application will create necessary\n"
        "folders and user configuration files in the standard application data directory\n"
        "for your operating system."
    )

    if platform_key == "linux":
        launch_notes = f"""How to launch on Linux:
- Run ./run_rabet.sh from this folder.
- To add an application-menu launcher with the RABET icon, run ./install_desktop_entry.sh.

Linux package notes:
- The release package contains a onefile {APP_NAME} executable plus the small
  configs/resources/scripts needed beside it. A visible _internal folder is not expected.
- Linux desktop environments do not reliably display a custom icon on the raw executable
  file itself. Use the installed desktop launcher for the app icon.

If the application fails with a Qt xcb platform plugin error on Ubuntu/Debian, install
the GUI runtime libraries below and launch again:

sudo apt update
sudo apt install \\
  libxcb-cursor0 \\
  libxcb-icccm4 \\
  libxcb-image0 \\
  libxcb-keysyms1 \\
  libxcb-render-util0 \\
  libxcb-xkb1 \\
  libxcb-randr0 \\
  libxcb-render0 \\
  libxcb-shape0 \\
  libxcb-shm0 \\
  libxcb-sync1 \\
  libxcb-xfixes0 \\
  libxkbcommon-x11-0 \\
  libxrender1 \\
  libx11-xcb1 \\
  libsm6 \\
  libice6 \\
  libglib2.0-0 \\
  libfontconfig1 \\
  libfreetype6"""
    elif platform_key in {"macos", "mac"}:
        launch_notes = f"""How to launch on macOS:
- Open {APP_NAME}.app.
- This build is unsigned. On first launch, macOS may require right-click > Open,
  or allowing the app from Privacy & Security settings.

macOS package notes:
- The app bundle uses resources/RABET.icns as the Finder/Dock icon.
- The release zip includes this README next to {APP_NAME}.app."""
    elif platform_key == "windows":
        launch_notes = f"""How to launch on Windows:
- Double-click {APP_NAME}.exe, or use Launch RABET.bat when it is included.

Windows package notes:
- Keep the configs and resources folders beside the executable."""
    else:
        launch_notes = "Launch the application from the executable or app bundle included in this package."

    readme = Path(target_dir) / "README.txt"
    readme.write_text(
        f"""{APP_NAME} - {APP_DESCRIPTION}
===========================================

Version: {APP_VERSION}
Platform build: {platform_label}

Thank you for using {APP_NAME}!

This application is designed for behavioral researchers who need to annotate
animal behaviors in videos with precise timing.

Features:
- Load and play video files with frame-by-frame navigation
- Create timed annotations via keyboard shortcuts using configurable key-to-behavior mappings
- Visualize annotations on an interactive timeline
- Conduct timed recording sessions with the ability to pause/resume
- Export annotations to CSV format with summary statistics
- Analyze multiple annotation files together to aggregate behavioral data
- Manage projects to organize research assets

Video runtime:
As of {APP_NAME} 1.3.1 the video pipeline is powered by PyAV (FFmpeg python
bindings) instead of python-vlc. The FFmpeg shared libraries are bundled inside
the application, so no system-wide VLC / FFmpeg install is required.

{launch_notes}

{first_run_note}

For more information, see the Help menu in the application.
""",
        encoding="utf-8",
    )


def remove_all_except(directory, keep_names, verbose=False):
    """Remove every direct child from a directory except selected file names."""
    directory = Path(directory)
    if not directory.exists() or not directory.is_dir():
        return

    keep_names = set(keep_names)
    for child in directory.iterdir():
        if child.name in keep_names:
            continue

        if verbose:
            print(f"  Removing {child}")

        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def remove_named_dirs(root, names, verbose=False):
    """Remove directories with exact names under a root."""
    root = Path(root)
    for child in sorted(root.rglob("*"), reverse=True):
        if child.is_dir() and child.name in names:
            if verbose:
                print(f"  Removing {child}")
            shutil.rmtree(child, ignore_errors=True)


def cleanup_qt_payload(root, platform_key, verbose=False):
    """Trim unused Qt/PySide files after PyInstaller finishes."""
    root = Path(root)
    if not root.exists():
        return

    remove_named_dirs(root, {"examples", "doc", "docs", "qml"}, verbose=verbose)

    for translations in root.rglob("translations"):
        if "PySide6" in translations.parts or "Qt" in translations.parts:
            keep = {
                item.name
                for item in translations.iterdir()
                if item.is_file() and (item.name.endswith("_en.qm") or item.name == "qt_en.qm")
            }
            remove_all_except(translations, keep, verbose=verbose)

    if platform_key == "macos":
        keep_by_plugin = {
            "platforms": {"libqcocoa.dylib"},
            "imageformats": {
                "libqgif.dylib",
                "libqicns.dylib",
                "libqico.dylib",
                "libqjpeg.dylib",
                "libqsvg.dylib",
            },
            "iconengines": {"libqsvgicon.dylib"},
            "styles": set(),
        }
    elif platform_key == "linux":
        keep_by_plugin = {
            "platforms": {"libqxcb.so"},
            "imageformats": {
                "libqgif.so",
                "libqico.so",
                "libqjpeg.so",
                "libqsvg.so",
            },
            "iconengines": {"libqsvgicon.so"},
            "styles": set(),
        }
    else:
        keep_by_plugin = {}

    remove_plugin_dirs = {
        "designer",
        "geoservices",
        "multimedia",
        "playlistformats",
        "printsupport",
        "qmltooling",
        "sqldrivers",
        "webview",
    }

    for plugins_dir in root.rglob("plugins"):
        if "PySide6" not in plugins_dir.parts and "Qt" not in plugins_dir.parts:
            continue

        for plugin_group in plugins_dir.iterdir():
            if not plugin_group.is_dir():
                continue

            if plugin_group.name in remove_plugin_dirs:
                if verbose:
                    print(f"  Removing {plugin_group}")
                shutil.rmtree(plugin_group, ignore_errors=True)
                continue

            if plugin_group.name in keep_by_plugin:
                remove_all_except(plugin_group, keep_by_plugin[plugin_group.name], verbose=verbose)


def cleanup_pyinstaller_output(root, platform_key, verbose=False):
    """Run conservative post-build cleanup for smaller distributions."""
    root = Path(root)
    print("Performing post-build cleanup...")
    cleanup_qt_payload(root, platform_key, verbose=verbose)
    remove_named_dirs(root, {"__pycache__"}, verbose=verbose)


def get_dir_size(path):
    """Return total bytes and file count under a path."""
    path = Path(path)
    if path.is_file():
        return path.stat().st_size, 1

    total = 0
    count = 0
    for file_path in path.rglob("*"):
        if file_path.is_file():
            total += file_path.stat().st_size
            count += 1
    return total, count


def format_size(num_bytes):
    """Format bytes as a human-readable MiB string."""
    return f"{num_bytes / (1024 * 1024):.2f} MB"


def display_size_summary(path, extra_paths=None):
    """Print size information for the built artifact."""
    path = Path(path)
    size, count = get_dir_size(path)
    print("\n===== Size Information =====")
    print(f"{path.name}: {format_size(size)} ({count} files)")

    for extra_path in extra_paths or []:
        extra_path = Path(extra_path)
        if extra_path.exists():
            extra_size, extra_count = get_dir_size(extra_path)
            print(f"{extra_path.name}: {format_size(extra_size)} ({extra_count} files)")

    largest = []
    if path.is_dir():
        for file_path in path.rglob("*"):
            if file_path.is_file():
                largest.append((file_path, file_path.stat().st_size))
    elif path.exists():
        largest.append((path, path.stat().st_size))

    largest.sort(key=lambda item: item[1], reverse=True)
    print("\nLargest files:")
    for file_path, file_size in largest[:8]:
        try:
            rel_path = file_path.relative_to(path)
        except ValueError:
            rel_path = file_path
        print(f"  {rel_path}: {format_size(file_size)}")


def create_tar_gz(source_dir, archive_path):
    """Create a gzip-compressed tar archive containing source_dir."""
    source_dir = Path(source_dir)
    archive_path = Path(archive_path)
    if archive_path.exists():
        archive_path.unlink()

    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(source_dir, arcname=source_dir.name)

    return archive_path


def run_pyinstaller(spec_path, verbose=False):
    """Run PyInstaller for a generated spec file."""
    cmd = [sys.executable, "-m", "PyInstaller", str(spec_path), "--noconfirm", "--clean"]
    print("\nRunning PyInstaller:")
    print(" ".join(cmd))

    if verbose:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
        process.wait()
        if process.returncode:
            raise subprocess.CalledProcessError(process.returncode, cmd)
    else:
        subprocess.check_call(cmd)
