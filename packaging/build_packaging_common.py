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
    "python-vlc",
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
    "python-vlc": "vlc",
    "Pillow": "PIL",
    "PyInstaller": "PyInstaller",
}

HIDDEN_DEPENDENCIES = [
    "vlc",
    "matplotlib.backends.backend_qtagg",
    "matplotlib.backends.backend_qt5agg",
    "PIL",
    "PIL.Image",
]

COMMON_EXCLUDED_MODULES = [
    "PyQt5",
    "PyQt6",
    "tkinter",
    "wx",
    "gtk",
    "scipy",
    "sklearn",
    "seaborn",
    "statsmodels",
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
    "distutils",
    "lib2to3",
    "ensurepip",
    "venv",
    "turtledemo",
    "test",
    "tests",
    "testing",
    "pip",
    "wheel",
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


def get_data_files(include_icns=True):
    """Return minimal PyInstaller data tuples for configs and app icons."""
    datas = []
    configs_dir = ROOT_DIR / "configs"
    if configs_dir.exists():
        datas.append((str(configs_dir), "configs"))

    resources_dir = ROOT_DIR / "resources"
    icon_names = ["RABET.ico"]
    if include_icns:
        icon_names.append("RABET.icns")

    for icon_name in icon_names:
        icon_path = resources_dir / icon_name
        if icon_path.exists():
            datas.append((str(icon_path), "resources"))

    png_icon = ROOT_DIR / "images" / "RABET.png"
    if png_icon.exists():
        datas.append((str(png_icon), "resources"))

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
    """Write a small runtime hook that helps python-vlc find external VLC."""
    if platform_key == "macos":
        hook = r'''
import os
from pathlib import Path

candidate_apps = [
    Path("/Applications/VLC.app"),
    Path.home() / "Applications" / "VLC.app",
]

for app_path in candidate_apps:
    macos_dir = app_path / "Contents" / "MacOS"
    plugin_dir = macos_dir / "plugins"
    lib_dir = macos_dir / "lib"
    if macos_dir.exists():
        if plugin_dir.exists():
            os.environ.setdefault("VLC_PLUGIN_PATH", str(plugin_dir))
        path_parts = [str(macos_dir)]
        if lib_dir.exists():
            path_parts.append(str(lib_dir))
            os.environ["DYLD_LIBRARY_PATH"] = (
                str(lib_dir) + os.pathsep + os.environ.get("DYLD_LIBRARY_PATH", "")
            )
        os.environ["PATH"] = os.pathsep.join(path_parts + [os.environ.get("PATH", "")])
        break
'''
    elif platform_key == "linux":
        hook = r'''
import os
from pathlib import Path

candidate_plugin_dirs = [
    Path("/usr/lib/x86_64-linux-gnu/vlc/plugins"),
    Path("/usr/lib/aarch64-linux-gnu/vlc/plugins"),
    Path("/usr/lib64/vlc/plugins"),
    Path("/usr/lib/vlc/plugins"),
]

for plugin_dir in candidate_plugin_dirs:
    if plugin_dir.exists():
        os.environ.setdefault("VLC_PLUGIN_PATH", str(plugin_dir))
        break
'''
    else:
        raise ValueError(f"Unsupported platform key: {platform_key}")

    path.write_text(hook.lstrip(), encoding="utf-8")
    return path


def copy_runtime_assets(target_dir):
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
        for icon_name in ("RABET.ico", "RABET.icns"):
            source_file = source_resources / icon_name
            if source_file.exists():
                shutil.copy2(source_file, destination / icon_name)

        png_icon = ROOT_DIR / "images" / "RABET.png"
        if png_icon.exists():
            shutil.copy2(png_icon, destination / "RABET.png")


def write_readme(target_dir, platform_label):
    """Write concise runtime notes into a distribution folder."""
    readme = Path(target_dir) / "README.txt"
    readme.write_text(
        f"""{APP_NAME} - {APP_DESCRIPTION}
===========================================

Version: {APP_VERSION}
Platform build: {platform_label}

VLC is required separately. Install VLC on the target machine before running RABET.
RABET stores user configuration and generated files in the platform-standard user
application data directory.

This package was built without bundling VLC to keep the file size small.
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
