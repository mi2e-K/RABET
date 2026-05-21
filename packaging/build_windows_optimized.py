# build_windows_optimized.py - Optimized script for building RABET with minimal dependencies

import os
import sys
import shutil
import subprocess
import platform
import argparse
import time
import json
import importlib.util
from pathlib import Path

# The build scripts live in ``packaging/`` so the project root must be on
# ``sys.path`` for ``from version import __version__`` to resolve when
# this script is invoked from the project root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from version import __version__ as APP_VERSION

# Core dependencies required by RABET based on dependency analysis
CORE_DEPENDENCIES = [
    "PySide6",         # Qt GUI framework
    # 1.3.1: python-vlc replaced by PyAV (FFmpeg python bindings).
    # PyAV ships pre-built wheels that bundle FFmpeg, so the resulting
    # PyInstaller bundle no longer needs a system-installed VLC runtime
    # on the target Windows machine.
    "av",
    "shiboken6"        # Required by PySide6
]

# Runtime dependencies imported by RABET features
RUNTIME_DEPENDENCIES = [
    "numpy",           # For numeric operations
    "pandas",          # For data analysis
    "matplotlib",      # For visualization/plotting
    "Pillow"           # Required by matplotlib for image handling
]

# Optional dependencies that are not required by the current code path
OPTIONAL_DEPENDENCIES = [
    "opencv-python"    # Reserved for future video processing features
]

PACKAGE_IMPORT_NAMES = {
    "av": "av",
    "Pillow": "PIL",
    "opencv-python": "cv2",
    "PyInstaller": "PyInstaller",
}

# Additional hidden dependencies needed for PyInstaller to work correctly
HIDDEN_DEPENDENCIES = [
    "setuptools",         # Provides pkg_resources functionality
    "jaraco.text",        # Required by setuptools
    "jaraco.classes",     # Often also required
    "jaraco.collections", # Often also required
    "importlib_metadata", # Required for package metadata
    "importlib_resources",# Required for resource files
    "more_itertools",     # Required by jaraco modules
    "packaging"           # Required for version handling
]

# Modules to exclude from the build. We import the cross-platform list
# from ``build_packaging_common`` so Windows / macOS / Linux builders
# share a single source of truth. Anything Windows-specific is appended
# below.
from build_packaging_common import (
    COMMON_BINARY_EXCLUDE_PATTERNS,
    COMMON_EXCLUDED_MODULES,
    PYSIDE_EXCLUDED_MODULES,
)

DEFAULT_EXCLUDED_MODULES = list(dict.fromkeys(
    COMMON_EXCLUDED_MODULES
    + PYSIDE_EXCLUDED_MODULES
    + [
        # Windows-specific extras (none currently — kept as a hook for
        # future per-platform pruning).
    ]
))

# Binaries commonly not needed that add significant size. The cross-
# platform list (COMMON_BINARY_EXCLUDE_PATTERNS) covers Qt6 sub-modules
# and the Intel MKL DLL family. Windows-specific extras are appended
# below.
DEFAULT_EXCLUDED_BINARIES = list(dict.fromkeys(
    COMMON_BINARY_EXCLUDE_PATTERNS
    + [
        # OpenGL and EGL
        'libEGL.dll',
        'opengl32sw.dll',

        # Unused Qt modules (kept here for the spec-file substring match;
        # mac/linux builders use the cross-platform patterns above).
        'Qt6DBus',
        'Qt6Designer',
        'Qt6DesignerComponents',
        'Qt6WebEngineCore',
        'qt6qml',
        'qt6quick',

        # Common unnecessary DLLs that add size
        'D3Dcompiler',
        'd3dcsx',

        # Keep VC runtime DLLs bundled by default; clean Windows
        # machines may need them. These might be removable on controlled
        # lab machines, but should not be excluded from general
        # distribution builds.
        # 'msvcp140_1',
        # 'vcruntime140_1',
        # 'api-ms-win-',
        # 'ucrtbase.dll',
        # 'vcruntime140.dll',

        # Unused optional encryption
        'libcrypto-',
        'libssl-',

        # Qt plugins that might not be needed
        'sqldrivers',
        'platformthemes',
        'webview',
        'multimedia',
        'playlistformats',
        'decorations',
        'printsupport',
    ]
))

def ensure_required_directories():
    """
    Ensure that all directories required for the build exist.
    Creates directories and default configuration files if they don't exist.
    Uses the centralized ConfigPathManager when available.
    
    Returns:
        bool: True if all directories were created/verified successfully
    """
    print("Ensuring required directories exist...")
    
    try:
        # List of required directories (excluding configs - handled by ConfigPathManager)
        required_dirs = [
            "resources",
            "logs",
            "projects"  # Directory for project files
        ]
        
        # Create each directory if it doesn't exist
        for dir_name in required_dirs:
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)
                print(f"Created missing directory: {dir_name}")
        
        # Create configs directory and default files using ConfigPathManager if available
        try:
            # Import here to avoid circular imports
            sys.path.insert(0, os.path.abspath("."))
            from utils.config_path_manager import ConfigPathManager
            
            # Initialize config path manager
            config_manager = ConfigPathManager()
            
            # Get or create configs directory
            configs_dir = config_manager.get_config_directory()
            print(f"Using configs directory: {configs_dir}")
            
            # Ensure default configs exist
            if config_manager.ensure_default_configs():
                print("Created or validated default configuration files")
            else:
                print("Warning: Failed to create some default configuration files")
        except ImportError:
            # Fall back to manual creation if ConfigPathManager is not available
            print("Warning: ConfigPathManager not available, using fallback method")
            
            # Create configs directory
            if not os.path.exists("configs"):
                os.makedirs("configs")
                print("Created missing directory: configs")
            
            # Create default action map
            default_action_map_path = os.path.join("configs", "default_action_map.json")
            if not os.path.exists(default_action_map_path):
                # Default key-to-behavior mappings
                default_mappings = {
                    "o": "Attack bites",
                    "j": "Sideways threats",
                    "p": "Tail rattles",
                    "q": "Chasing",
                    "a": "Social contact",
                    "e": "Self-grooming",
                    "t": "Locomotion",
                    "r": "Rearing"
                }
                
                # Create the file
                with open(default_action_map_path, 'w') as f:
                    json.dump(default_mappings, f, indent=2)
                
                print(f"Created default action map: {default_action_map_path}")
            
            # Create default metrics config
            default_metrics_path = os.path.join("configs", "default_metrics.json")
            if not os.path.exists(default_metrics_path):
                # Default metrics configuration
                default_metrics = {
                    "latency_metrics": [
                        {
                            "name": "Attack Latency",
                            "behavior": "Attack bites",
                            "enabled": True
                        }
                    ],
                    "total_time_metrics": [
                        {
                            "name": "Total Aggression",
                            "behaviors": ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"],
                            "enabled": True
                        },
                        {
                            "name": "Total Aggression(without tail-rattles)",
                            "behaviors": ["Attack bites", "Sideways threats", "Chasing"],
                            "enabled": True
                        }
                    ]
                }
                
                # Create the file
                with open(default_metrics_path, 'w') as f:
                    json.dump(default_metrics, f, indent=2)
                
                print(f"Created default metrics configuration: {default_metrics_path}")
        
        return True
    except Exception as e:
        print(f"Error ensuring required directories: {str(e)}")
        return False

def get_import_name(package_name):
    """Return the importable module name for a pip package."""
    return PACKAGE_IMPORT_NAMES.get(package_name, package_name.replace("-", "_"))

def is_package_available(package_name):
    """Check whether a package's import target is available."""
    try:
        return importlib.util.find_spec(get_import_name(package_name)) is not None
    except ModuleNotFoundError:
        return False

def install_package(package_name, install_spec=None):
    """Install a package using the current Python interpreter."""
    target = install_spec or package_name
    print(f"Installing dependency: {target}")
    subprocess.check_call([sys.executable, "-m", "pip", "install", target])

def ensure_package(package_name, install_spec=None):
    """Install a dependency only when its import target is missing."""
    if is_package_available(package_name):
        print(f"Dependency available: {package_name}")
        return

    install_package(package_name, install_spec=install_spec)

# NOTE (1.3.1): ``find_vlc_installation`` was removed when the video
# backend switched from python-vlc to PyAV. PyAV's wheel embeds
# FFmpeg directly, so the build no longer needs to locate a system
# VLC. The function is intentionally absent (rather than left as a
# stub) so any stale caller surfaces immediately as an
# ``AttributeError`` during a build.

def install_dependencies():
    """
    Install required dependencies for the build.
    
    Returns:
        bool: True if installation was successful
    """
    print("Checking and installing required dependencies...")
    
    try:
        # Install PyInstaller first if needed
        ensure_package("PyInstaller", install_spec="PyInstaller>=6.0.0")
        
        required_dependencies = CORE_DEPENDENCIES + RUNTIME_DEPENDENCIES + HIDDEN_DEPENDENCIES
        for dependency in required_dependencies:
            ensure_package(dependency)

        for dependency in OPTIONAL_DEPENDENCIES:
            if is_package_available(dependency):
                print(f"Optional dependency available: {dependency}")
            else:
                print(f"Optional dependency not installed, skipping: {dependency}")
            
        return True
    except Exception as e:
        print(f"Error installing dependencies: {str(e)}")
        return False

def main():
    """Build the RABET application for Windows distribution with optimized size."""
    parser = argparse.ArgumentParser(description="Build RABET for Windows distribution")
    parser.add_argument("--upx", action="store_true", help="Use UPX compression to reduce size")
    parser.add_argument("--onefile", action="store_true", help="Build a single executable file")
    parser.add_argument("--exclude-module", action="append", default=[], 
                       help="Exclude a module. Can be used multiple times.")
    parser.add_argument("--include-module", action="append", default=[],
                       help="Include a module that would otherwise be excluded. Can be used multiple times.")
    parser.add_argument("--spec-only", action="store_true",
                       help="Only generate the spec file without building")
    parser.add_argument("--skip-cleanup", action="store_true",
                       help="Skip post-build cleanup to preserve all files")
    parser.add_argument("--verbose", action="store_true",
                       help="Show verbose output during build")
    parser.add_argument("--console", action="store_true",
                       help="Show a console window in the built application")
    parser.add_argument("--strip", action="store_true",
                       help="Strip binaries to reduce size (not recommended for general Windows distribution)")
    parser.add_argument("--no-strip", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    strip_binaries = args.strip and not args.no_strip
    
    if platform.system() != "Windows":
        print("Error: This script is intended for Windows systems only.")
        sys.exit(1)
        
    print("===== Building RABET for Windows Distribution =====")
    print("Real-time Animal Behavior Event Tagger")
    
    # Record start time
    start_time = time.time()
    
    # Install dependencies unless only generating the spec file.
    if args.spec_only:
        print("Spec-only mode: skipping dependency installation.")
    elif not install_dependencies():
        print("Warning: Failed to install some dependencies. Build may fail.")

    # 1.3.1: PyAV bundles FFmpeg inside its wheel, so the previous
    # ``find_vlc_installation`` runtime check is gone.

    # Check for UPX if enabled
    upx_dir = None
    if args.upx:
        if os.path.exists("upx"):
            upx_dir = "upx"
            print(f"Using UPX from: {os.path.abspath(upx_dir)}")
        else:
            print("Warning: UPX directory not found. UPX compression will be disabled.")
            print("Download UPX from https://upx.github.io/ and extract to ./upx")
            args.upx = False
    
    if not args.spec_only:
        # Prepare build directory
        if os.path.exists("build"):
            print("Cleaning build directory...")
            shutil.rmtree("build")
        os.makedirs("build", exist_ok=True)
        
        # Prepare dist directory
        if os.path.exists("dist"):
            print("Cleaning dist directory...")
            shutil.rmtree("dist")
    
    # Ensure required directories exist before building
    if not ensure_required_directories():
        print("Warning: Failed to create some required directories. Build may fail.")
    
    # Find resources directory for both data inclusion and icon
    resource_paths = [
        'resources',
        os.path.join('..', 'resources'),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), 'resources')
    ]
    
    resource_dir = None
    for path in resource_paths:
        if os.path.exists(path) and os.path.isdir(path):
            resource_dir = path
            break
    
    if resource_dir:
        print(f"Found resources directory: {resource_dir}")
    else:
        print("Resources directory not found. Icons and resources may be missing in the build.")
        resource_dir = 'resources'  # Use default name even if not found
    
    # Find icon file in multiple potential locations
    icon_paths = [
        os.path.join(resource_dir, 'RABET.ico'),
        os.path.join(resource_dir, 'icon.ico'),
        'RABET.ico',
        'icon.ico'
    ]
    
    # For packaged app, also check relative to script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    for rel_path in ['RABET.ico', 'icon.ico', 
                    os.path.join('resources', 'RABET.ico'), 
                    os.path.join('resources', 'icon.ico')]:
        icon_paths.append(os.path.join(script_dir, rel_path))
    
    # Find the first valid icon path
    icon_path = None
    for path in icon_paths:
        if os.path.exists(path):
            icon_path = path
            print(f"Found icon at: {icon_path}")
            break
    
    if icon_path:
        # Use the found icon path
        icon_option = f", icon=r'{icon_path}'"
    else:
        print("Warning: Application icon not found")
        icon_option = ""
    
    # Combine excluded modules
    modules_to_exclude = DEFAULT_EXCLUDED_MODULES.copy()
    
    # Add user-specified excluded modules
    for module in args.exclude_module:
        if module not in modules_to_exclude:
            modules_to_exclude.append(module)
    
    # Remove explicitly included modules
    for module in args.include_module:
        if module in modules_to_exclude:
            modules_to_exclude.remove(module)
            print(f"Including module that would otherwise be excluded: {module}")
    
    # Ensure PySide6 and required dependencies are not excluded
    for dep in CORE_DEPENDENCIES:
        if dep in modules_to_exclude:
            modules_to_exclude.remove(dep)
            print(f"Warning: Critical dependency {dep} was in exclude list - keeping it.")
    
    # Print module exclusion info
    print(f"\nExcluding {len(modules_to_exclude)} modules to optimize size")
    if args.verbose:
        for module in sorted(modules_to_exclude):
            print(f"  - {module}")
    
    # Create hidden imports string. The base list is intentionally
    # narrow (top-level entry points that PyInstaller's static analyser
    # may miss). Everything else flows in from build_packaging_common's
    # HIDDEN_DEPENDENCIES so the macOS / Linux / Windows builders cannot
    # drift apart silently.
    from build_packaging_common import HIDDEN_DEPENDENCIES as _COMMON_HIDDEN

    hidden_imports_list = [
        'setuptools',    # Provides pkg_resources functionality
        'pkg_resources', # Will be found via setuptools
    ]
    for dep in _COMMON_HIDDEN:
        if dep not in hidden_imports_list:
            hidden_imports_list.append(dep)
    
    # Add setuptools submodules that might be needed
    hidden_imports_list.extend([
        'setuptools.extern',
        'setuptools._vendor',
        'setuptools._vendor.packaging',
        'setuptools._vendor.packaging.version',
        'setuptools._vendor.more_itertools',
    ])
    
    # Add the rest of our hidden dependencies
    hidden_imports_list.extend(HIDDEN_DEPENDENCIES)
    
    # Create spec file content with optimizations
    print("\nCreating optimized spec file...")
    
    # Generate different spec content based on onefile mode
    if args.onefile:
        # One-file mode spec
        spec_content = f"""
# -*- mode: python ; coding: utf-8 -*-
# RABET optimized spec file for onefile mode

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Modules explicitly excluded
excluded_modules = {repr(modules_to_exclude)}

# Binaries and DLLs to exclude from the build
excluded_binaries = {repr(DEFAULT_EXCLUDED_BINARIES)}

# Include required data files
datas = []

# Add Windows-specific resource files only. ``resources/`` also contains
# RABET.icns (macOS app bundle icon, ~1.7 MB) which is dead weight in a
# Windows distribution, so we list the files we actually want by name
# instead of adding the whole directory.
if os.path.exists('{resource_dir}'):
    for _resource_name in ('RABET.ico',):
        _resource_path = os.path.join('{resource_dir}', _resource_name)
        if os.path.exists(_resource_path):
            datas.append((_resource_path, 'resources'))

# Add configs directory
if os.path.exists('configs'):
    datas.append(('configs', 'configs'))
else:
    # Create configs directory if it doesn't exist
    os.makedirs('configs', exist_ok=True)
    # Create default configuration files using helper function
    def create_default_configs():
        # Create default action map
        default_map_path = os.path.join('configs', 'default_action_map.json')
        if not os.path.exists(default_map_path):
            import json
            with open(default_map_path, 'w') as f:
                json.dump({{"o": "Attack bites", "j": "Sideways threats", "p": "Tail rattles", 
                          "q": "Chasing", "a": "Social contact", "e": "Self-grooming", 
                          "t": "Locomotion", "r": "Rearing"}}, f, indent=2)
        
        # Create default metrics config
        metrics_path = os.path.join('configs', 'default_metrics.json')
        if not os.path.exists(metrics_path):
            import json
            with open(metrics_path, 'w') as f:
                json.dump({{"latency_metrics": [{{"name": "Attack Latency", "behavior": "Attack bites", "enabled": True}}], 
                          "total_time_metrics": [
                              {{"name": "Total Aggression", "behaviors": ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"], "enabled": True}},
                              {{"name": "Total Aggression(without tail-rattles)", "behaviors": ["Attack bites", "Sideways threats", "Chasing"], "enabled": True}}
                          ]}}, f, indent=2)
    
    create_default_configs()
    datas.append(('configs', 'configs'))

# Gather necessary binary hooks
binaries = []

# 1.3.1: collect PyAV's bundled FFmpeg DLLs. The wheel installs them
# inside ``site-packages/av/`` so PyInstaller's static analyser does
# not pick them up automatically — we walk the directory and pull in
# every ``.dll`` so frame decoding works inside the bundle.
try:
    import av as _av_for_binaries  # noqa: F401
    av_pkg_dir = os.path.dirname(_av_for_binaries.__file__)
    for entry in os.listdir(av_pkg_dir):
        if entry.lower().endswith(('.dll', '.pyd')):
            binaries.append((os.path.join(av_pkg_dir, entry), 'av'))
except Exception as exc:
    print(f'Warning: could not enumerate av/* binaries: {{exc}}')

# 1.3.2 fix: PyInstaller 6.x dropped ``_ctypes`` runtime dependencies on
# some conda Python builds. ``_ctypes.pyd`` is bundled, but the libffi
# DLL it loads at startup lives in ``<env>/Library/bin`` and is missed
# by the static analyser, which makes the bundled exe crash with
# ``DLL load failed while importing _ctypes`` before reaching main().
# Walk the conda Library/bin directory once and pull in the runtime
# DLLs that ship with the env. We only collect a small allow-list to
# avoid grabbing the entire conda Library tree.
try:
    import sys as _sys_for_libdlls
    _conda_bin = os.path.join(os.path.dirname(_sys_for_libdlls.executable), 'Library', 'bin')
    # PE-import-table analysis shows ``_ctypes.pyd`` from this conda
    # build asks for the BARE name ``ffi.dll`` - not ``ffi-7.dll`` or
    # ``ffi-8.dll``. So the prefix match has to include the un-suffixed
    # filename as well. We accept anything that starts with ``ffi`` or
    # ``libffi`` and ends with ``.dll`` - this catches ffi.dll,
    # ffi-7.dll, ffi-8.dll, libffi-7.dll, etc.
    _conda_runtime_prefixes = ('ffi', 'libffi')
    if os.path.isdir(_conda_bin):
        for entry in os.listdir(_conda_bin):
            entry_lower = entry.lower()
            if not entry_lower.endswith('.dll'):
                continue
            if entry_lower.startswith(_conda_runtime_prefixes):
                binaries.append((os.path.join(_conda_bin, entry), '.'))
except Exception as exc:
    print(f'Warning: could not enumerate conda runtime DLLs: {{exc}}')

# Explicitly include these modules to ensure they're available
hiddenimports = {repr(hidden_imports_list)}

# 1.3.2: krippendorff and filetype are imported lazily inside RABET
# helpers (models/reliability_model.py and utils/video_detection.py).
# PyInstaller's static analyser misses them via the import graph, and
# even the hiddenimports list above does not force their source files
# into the bundle on this build. Use collect_submodules / collect_data
# to pull every submodule and data file explicitly so the runtime
# import succeeds.
# NOTE (1.3.2): scipy 1.16+ ships a Cython-built private module
# ``scipy._cyutility`` that PyInstaller's stock scipy hook misses, which
# breaks ``import pingouin`` (pingouin imports scipy on init). The
# safest fix is to force-collect every scipy submodule. Adds ~30 MB to
# the bundle but guarantees the extension modules are present.
for _lazy_pkg in ('krippendorff', 'filetype', 'pingouin', 'scipy'):
    try:
        hiddenimports += collect_submodules(_lazy_pkg)
        datas += collect_data_files(_lazy_pkg)
    except Exception as _exc:
        print(f'Warning: could not collect {{_lazy_pkg}}: {{_exc}}')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out excluded binaries
a.binaries = TOC([x for x in a.binaries if not any(excluded in x[0] for excluded in excluded_binaries)])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='RABET',
    debug=False,
    bootloader_ignore_signals=False,
    strip={strip_binaries},
    upx={"True" if args.upx else "False"},
    console={args.console},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None{icon_option},
)
"""
    else:
        # One-folder mode spec (default)
        spec_content = f"""
# -*- mode: python ; coding: utf-8 -*-
# RABET optimized spec file for onedir mode

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Modules explicitly excluded
excluded_modules = {repr(modules_to_exclude)}

# Binaries and DLLs to exclude from the build
excluded_binaries = {repr(DEFAULT_EXCLUDED_BINARIES)}

# Include required data files
datas = []

# Add Windows-specific resource files only. ``resources/`` also contains
# RABET.icns (macOS app bundle icon, ~1.7 MB) which is dead weight in a
# Windows distribution, so we list the files we actually want by name
# instead of adding the whole directory.
if os.path.exists('{resource_dir}'):
    for _resource_name in ('RABET.ico',):
        _resource_path = os.path.join('{resource_dir}', _resource_name)
        if os.path.exists(_resource_path):
            datas.append((_resource_path, 'resources'))

# Add configs directory
if os.path.exists('configs'):
    datas.append(('configs', 'configs'))
else:
    # Create configs directory if it doesn't exist
    os.makedirs('configs', exist_ok=True)
    # Create default configuration files using helper function
    def create_default_configs():
        # Create default action map
        default_map_path = os.path.join('configs', 'default_action_map.json')
        if not os.path.exists(default_map_path):
            import json
            with open(default_map_path, 'w') as f:
                json.dump({{"o": "Attack bites", "j": "Sideways threats", "p": "Tail rattles", 
                          "q": "Chasing", "a": "Social contact", "e": "Self-grooming", 
                          "t": "Locomotion", "r": "Rearing"}}, f, indent=2)
        
        # Create default metrics config
        metrics_path = os.path.join('configs', 'default_metrics.json')
        if not os.path.exists(metrics_path):
            import json
            with open(metrics_path, 'w') as f:
                json.dump({{"latency_metrics": [{{"name": "Attack Latency", "behavior": "Attack bites", "enabled": True}}], 
                          "total_time_metrics": [
                              {{"name": "Total Aggression", "behaviors": ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"], "enabled": True}},
                              {{"name": "Total Aggression(without tail-rattles)", "behaviors": ["Attack bites", "Sideways threats", "Chasing"], "enabled": True}}
                          ]}}, f, indent=2)
    
    create_default_configs()
    datas.append(('configs', 'configs'))

# Gather necessary binary hooks
binaries = []

# 1.3.1: collect PyAV's bundled FFmpeg DLLs. The wheel installs them
# inside ``site-packages/av/`` so PyInstaller's static analyser does
# not pick them up automatically — we walk the directory and pull in
# every ``.dll`` so frame decoding works inside the bundle.
try:
    import av as _av_for_binaries  # noqa: F401
    av_pkg_dir = os.path.dirname(_av_for_binaries.__file__)
    for entry in os.listdir(av_pkg_dir):
        if entry.lower().endswith(('.dll', '.pyd')):
            binaries.append((os.path.join(av_pkg_dir, entry), 'av'))
except Exception as exc:
    print(f'Warning: could not enumerate av/* binaries: {{exc}}')

# 1.3.2 fix: PyInstaller 6.x dropped ``_ctypes`` runtime dependencies on
# some conda Python builds. ``_ctypes.pyd`` is bundled, but the libffi
# DLL it loads at startup lives in ``<env>/Library/bin`` and is missed
# by the static analyser, which makes the bundled exe crash with
# ``DLL load failed while importing _ctypes`` before reaching main().
# Walk the conda Library/bin directory once and pull in the runtime
# DLLs that ship with the env. We only collect a small allow-list to
# avoid grabbing the entire conda Library tree.
try:
    import sys as _sys_for_libdlls
    _conda_bin = os.path.join(os.path.dirname(_sys_for_libdlls.executable), 'Library', 'bin')
    # PE-import-table analysis shows ``_ctypes.pyd`` from this conda
    # build asks for the BARE name ``ffi.dll`` - not ``ffi-7.dll`` or
    # ``ffi-8.dll``. So the prefix match has to include the un-suffixed
    # filename as well. We accept anything that starts with ``ffi`` or
    # ``libffi`` and ends with ``.dll`` - this catches ffi.dll,
    # ffi-7.dll, ffi-8.dll, libffi-7.dll, etc.
    _conda_runtime_prefixes = ('ffi', 'libffi')
    if os.path.isdir(_conda_bin):
        for entry in os.listdir(_conda_bin):
            entry_lower = entry.lower()
            if not entry_lower.endswith('.dll'):
                continue
            if entry_lower.startswith(_conda_runtime_prefixes):
                binaries.append((os.path.join(_conda_bin, entry), '.'))
except Exception as exc:
    print(f'Warning: could not enumerate conda runtime DLLs: {{exc}}')

# Explicitly include these modules to ensure they're available
hiddenimports = {repr(hidden_imports_list)}

# 1.3.2: krippendorff and filetype are imported lazily inside RABET
# helpers (models/reliability_model.py and utils/video_detection.py).
# PyInstaller's static analyser misses them via the import graph, and
# even the hiddenimports list above does not force their source files
# into the bundle on this build. Use collect_submodules / collect_data
# to pull every submodule and data file explicitly so the runtime
# import succeeds.
# NOTE (1.3.2): scipy 1.16+ ships a Cython-built private module
# ``scipy._cyutility`` that PyInstaller's stock scipy hook misses, which
# breaks ``import pingouin`` (pingouin imports scipy on init). The
# safest fix is to force-collect every scipy submodule. Adds ~30 MB to
# the bundle but guarantees the extension modules are present.
for _lazy_pkg in ('krippendorff', 'filetype', 'pingouin', 'scipy'):
    try:
        hiddenimports += collect_submodules(_lazy_pkg)
        datas += collect_data_files(_lazy_pkg)
    except Exception as _exc:
        print(f'Warning: could not collect {{_lazy_pkg}}: {{_exc}}')

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=excluded_modules,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out excluded binaries
a.binaries = TOC([x for x in a.binaries if not any(excluded in x[0] for excluded in excluded_binaries)])

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='RABET',
    debug=False,
    bootloader_ignore_signals=False,
    strip={strip_binaries},
    upx={"True" if args.upx else "False"},
    console={args.console},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None{icon_option},
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip={strip_binaries},
    upx={"True" if args.upx else "False"},
    upx_exclude=[],
    name='RABET',
)
"""
    
    # Write spec file
    with open("RABET.spec", "w") as f:
        f.write(spec_content)
    
    # If spec-only mode, exit here
    if args.spec_only:
        print("Spec file 'RABET.spec' created successfully. Exiting without building.")
        return
    
    # Build command
    cmd = [sys.executable, "-m", "PyInstaller", "RABET.spec", "--noconfirm", "--clean"]
    
    # Print build command
    print("\nRunning PyInstaller with command:")
    print(" ".join(cmd))
    
    # Run PyInstaller
    try:
        if args.verbose:
            print("Running with verbose output...")
            # For verbose mode, we'll capture and print the output
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in process.stdout:
                print(line, end='')
            process.wait()
            if process.returncode != 0:
                print(f"Error: PyInstaller failed with exit code {process.returncode}")
                sys.exit(1)
        else:
            # For normal mode, just run the command
            subprocess.check_call(cmd)
    except subprocess.CalledProcessError as e:
        print(f"Error: PyInstaller failed with exit code {e.returncode}")
        print("Please check the build logs for more information.")
        sys.exit(1)
    except FileNotFoundError:
        print("Error: PyInstaller executable not found. Try installing it with:")
        print("pip install pyinstaller")
        sys.exit(1)
    
    # Post-build processing
    if not args.skip_cleanup:
        perform_post_build_cleanup(args.verbose)
    
    # Additional post-processing for onefile mode
    if args.onefile:
        print("\nPerforming post-processing for single-file executable...")
        
        # In onefile mode, we need to ensure runtime directories still exist
        os.makedirs(os.path.join("dist", "configs"), exist_ok=True)
        # NOTE (1.3.2): ``logs/`` and ``projects/`` are created lazily by
        # the running app the first time they are needed. We no longer
        # ship empty placeholder directories in the distribution.
        
        # Copy only specific files from resources directory, not everything
        dist_resources_dir = os.path.join("dist", "resources")
        if not os.path.exists(dist_resources_dir) and os.path.exists(resource_dir):
            print(f"Creating resources directory in distribution")
            os.makedirs(dist_resources_dir, exist_ok=True)
            
            # Only copy icon and specific resource files
            for file_name in os.listdir(resource_dir):
                file_path = os.path.join(resource_dir, file_name)
                # Skip directories, JSON files, and the macOS-only .icns icon
                # (it is ~1.7 MB and serves no purpose in a Windows bundle).
                if file_name.endswith(('.json', '.icns')) or os.path.isdir(file_path):
                    continue
                # Copy other files (icons, images, etc.)
                print(f"Copying resource file: {file_name}")
                shutil.copy2(file_path, os.path.join(dist_resources_dir, file_name))
        
        # Create a default action map in configs
        action_map_path = os.path.join("dist", "configs", "default_action_map.json")
        if not os.path.exists(action_map_path):
            print("Creating default action map configuration...")
            with open(action_map_path, "w") as f:
                f.write("""
{
  "o": "Attack bites",
  "j": "Sideways threats",
  "p": "Tail rattles",
  "q": "Chasing",
  "a": "Social contact",
  "e": "Self-grooming",
  "t": "Locomotion",
  "r": "Rearing"
}
""")
        
        # Create default metrics configuration in configs
        metrics_path = os.path.join("dist", "configs", "default_metrics.json")
        if not os.path.exists(metrics_path):
            print("Creating default metrics configuration...")
            with open(metrics_path, "w") as f:
                f.write("""
{
  "latency_metrics": [
    {
      "name": "Attack Latency",
      "behavior": "Attack bites",
      "enabled": true
    }
  ],
  "total_time_metrics": [
    {
      "name": "Total Aggression",
      "behaviors": ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"],
      "enabled": true
    },
    {
      "name": "Total Aggression(without tail-rattles)",
      "behaviors": ["Attack bites", "Sideways threats", "Chasing"],
      "enabled": true
    }
  ]
}
""")
        
        # Create a README file
        with open(os.path.join("dist", "README.txt"), "w") as f:
            f.write(f"""RABET - Real-time Animal Behavior Event Tagger
===========================================

Version: {APP_VERSION}

Thank you for using RABET!

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

For more information, see the Help menu in the application.

Important: When running for the first time, the application will create necessary
folders (configs, projects, logs) in the same directory as the executable.
Do not delete these folders while using the application.
""")
        
        # Create a simple batch file for launching
        with open(os.path.join("dist", "Launch RABET.bat"), "w") as f:
            f.write("@echo off\nstart RABET.exe\n")
    else:
        # Additional post-processing for folder mode
        print("\nPerforming post-processing...")
        
        # Create necessary directories
        print("Creating application directories...")
        os.makedirs(os.path.join("dist", "RABET", "configs"), exist_ok=True)
        # NOTE (1.3.2): ``logs/`` and ``projects/`` are created lazily by
        # the running app the first time they are needed. We no longer
        # ship empty placeholder directories in the distribution.
        
        # Copy only specific files from resources directory, not everything
        dist_resources_dir = os.path.join("dist", "RABET", "resources")
        if not os.path.exists(dist_resources_dir) and os.path.exists(resource_dir):
            print(f"Creating resources directory in distribution")
            os.makedirs(dist_resources_dir, exist_ok=True)
            
            # Only copy icon and specific resource files
            for file_name in os.listdir(resource_dir):
                file_path = os.path.join(resource_dir, file_name)
                # Skip directories, JSON files, and the macOS-only .icns icon
                # (it is ~1.7 MB and serves no purpose in a Windows bundle).
                if file_name.endswith(('.json', '.icns')) or os.path.isdir(file_path):
                    continue
                # Copy other files (icons, images, etc.)
                print(f"Copying resource file: {file_name}")
                shutil.copy2(file_path, os.path.join(dist_resources_dir, file_name))
        
        # Create a default action map if none exists
        action_map_path = os.path.join("dist", "RABET", "configs", "default_action_map.json")
        if not os.path.exists(action_map_path):
            print("Creating default action map configuration...")
            with open(action_map_path, "w") as f:
                f.write("""
{
  "o": "Attack bites",
  "j": "Sideways threats",
  "p": "Tail rattles",
  "q": "Chasing",
  "a": "Social contact",
  "e": "Self-grooming",
  "t": "Locomotion",
  "r": "Rearing"
}
""")
        
        # Create default metrics configuration
        metrics_path = os.path.join("dist", "RABET", "configs", "default_metrics.json")
        if not os.path.exists(metrics_path):
            print("Creating default metrics configuration...")
            with open(metrics_path, "w") as f:
                f.write("""
{
  "latency_metrics": [
    {
      "name": "Attack Latency",
      "behavior": "Attack bites",
      "enabled": true
    }
  ],
  "total_time_metrics": [
    {
      "name": "Total Aggression",
      "behaviors": ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"],
      "enabled": true
    },
    {
      "name": "Total Aggression(without tail-rattles)",
      "behaviors": ["Attack bites", "Sideways threats", "Chasing"],
      "enabled": true
    }
  ]
}
""")
        
        # Create a README file
        with open(os.path.join("dist", "RABET", "README.txt"), "w") as f:
            f.write(f"""RABET - Real-time Animal Behavior Event Tagger
===========================================

Version: {APP_VERSION}

Thank you for using RABET!

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

For more information, see the Help menu in the application.
""")
        
        # Create a simple batch file for launching
        with open(os.path.join("dist", "RABET", "Launch RABET.bat"), "w") as f:
            f.write("@echo off\nstart RABET.exe\n")
    
    # Calculate size
    calculate_and_display_size_info(args.onefile)
    
    # Calculate build time
    end_time = time.time()
    build_time = end_time - start_time
    print(f"\nBuild completed in {build_time:.2f} seconds ({build_time/60:.2f} minutes)")
    
    print("\n===== Build Complete =====")
    if args.onefile:
        print(f"Single executable created: {os.path.abspath('dist/RABET.exe')}")
        print("You can distribute this executable file along with the configs folder.")
    else:
        print(f"Application built in: {os.path.abspath('dist/RABET')}")
        print("You can distribute the entire RABET folder.")

def perform_post_build_cleanup(verbose=False):
    """
    Performs additional cleanup on the built distribution to further reduce size.
    """
    print("\nPerforming post-build cleanup...")
    
    # Get the dist path
    dist_path = os.path.join("dist", "RABET", "_internal")
    if not os.path.exists(dist_path):
        print("  Skipping cleanup - dist path not found")
        return
    
    # Post-build cleanup tasks
    cleanup_tasks = [
        # Remove translation files we don't need
        {
            "path": os.path.join(dist_path, "PySide6", "translations"),
            "keep": ["qt_en.qm"],  # Keep only English translations
            "desc": "Removing unused translation files"
        },
        
        # Remove example code
        {
            "path": os.path.join(dist_path, "PySide6", "examples"),
            "keep": [],
            "desc": "Removing example code"
        },
        
        # Clean unnecessary Qt plugins
        {
            "path": os.path.join(dist_path, "PySide6", "plugins", "iconengines"),
            "keep": ["qsvgicon.dll"],
            "desc": "Cleaning icon engines"
        },
        {
            "path": os.path.join(dist_path, "PySide6", "plugins", "imageformats"),
            "keep": ["qjpeg.dll", "qsvg.dll", "qgif.dll", "qico.dll"],
            "desc": "Cleaning image formats"
        },
        {
            "path": os.path.join(dist_path, "PySide6", "plugins", "platforms"),
            "keep": ["qwindows.dll"],
            "desc": "Cleaning platforms"
        },
        {
            "path": os.path.join(dist_path, "PySide6", "plugins", "styles"),
            "keep": ["qwindowsvistastyle.dll"],
            "desc": "Cleaning styles"
        }
    ]
    
    # Process each cleanup task
    for task in cleanup_tasks:
        path = task["path"]
        keep_files = task["keep"]
        
        if os.path.exists(path):
            print(f"  {task['desc']}...")
            
            if os.path.isdir(path):
                # For directories with keep files, remove all except the keep files
                if keep_files:
                    for item in os.listdir(path):
                        item_path = os.path.join(path, item)
                        if os.path.isfile(item_path) and item not in keep_files:
                            if verbose:
                                print(f"    Removing: {item_path}")
                            os.remove(item_path)
                else:
                    # For directories with no keep files, remove the entire directory
                    if verbose:
                        print(f"    Removing directory: {path}")
                    shutil.rmtree(path)
            elif os.path.isfile(path):
                # For individual files
                if verbose:
                    print(f"    Removing file: {path}")
                os.remove(path)

def calculate_and_display_size_info(onefile=False):
    """Calculate and display detailed size information about the build."""
    if onefile:
        dist_path = "dist"
        exe_path = os.path.join(dist_path, "RABET.exe")
        
        if not os.path.exists(exe_path):
            print("\nCannot calculate size: executable not found")
            return
            
        print("\n===== Size Information =====")
        
        # Get executable size
        exe_size = os.path.getsize(exe_path)
        print(f"Executable size: {exe_size / (1024 * 1024):.2f} MB")
        
        # Calculate total distribution size including folders
        total_size = 0
        file_count = 0
        for dirpath, dirnames, filenames in os.walk(dist_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
                file_count += 1
        
        print(f"Total distribution size: {total_size / (1024 * 1024):.2f} MB ({file_count} files)")
    else:
        dist_path = os.path.join("dist", "RABET")
        if not os.path.exists(dist_path):
            print("\nCannot calculate size: distribution path not found")
            return
        
        print("\n===== Size Information =====")
        
        # Function to get directory sizes
        def get_dir_size(path):
            total_size = 0
            file_count = 0
            for dirpath, dirnames, filenames in os.walk(path):
                for f in filenames:
                    fp = os.path.join(dirpath, f)
                    total_size += os.path.getsize(fp)
                    file_count += 1
            return total_size, file_count
        
        # Get main distribution size
        total_size, total_files = get_dir_size(dist_path)
        print(f"Total size: {total_size / (1024 * 1024):.2f} MB ({total_files} files)")
        
        # Get _internal size (typically the largest part)
        internal_path = os.path.join(dist_path, "_internal")
        if os.path.exists(internal_path):
            internal_size, internal_files = get_dir_size(internal_path)
            print(f"_internal directory: {internal_size / (1024 * 1024):.2f} MB ({internal_files} files) - {internal_size / total_size * 100:.1f}% of total")
            
            # Check PySide6 size (often a large contributor)
            pyside_path = os.path.join(internal_path, "PySide6")
            if os.path.exists(pyside_path):
                pyside_size, pyside_files = get_dir_size(pyside_path)
                print(f"PySide6 directory: {pyside_size / (1024 * 1024):.2f} MB ({pyside_files} files) - {pyside_size / total_size * 100:.1f}% of total")
        
        # Find the 5 largest files
        largest_files = []
        for dirpath, dirnames, filenames in os.walk(dist_path):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                size = os.path.getsize(fp)
                # Keep track of the 5 largest files
                largest_files.append((fp, size))
                largest_files.sort(key=lambda x: x[1], reverse=True)
                if len(largest_files) > 5:
                    largest_files.pop()
        
        print("\nLargest files:")
        for filepath, size in largest_files:
            rel_path = os.path.relpath(filepath, dist_path)
            print(f"  {rel_path}: {size / (1024 * 1024):.2f} MB")

if __name__ == "__main__":
    main()
