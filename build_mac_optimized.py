# build_mac_optimized.py - Optimized script for building RABET for macOS

import os
import sys
import shutil
import subprocess
import platform
import argparse
import time
import json
from pathlib import Path

# Core dependencies required by RABET
CORE_DEPENDENCIES = [
    "PySide6",         # Qt GUI framework
    "python-vlc",      # Video playback
    "shiboken6"        # Required by PySide6
]

# Optional dependencies based on feature usage
OPTIONAL_DEPENDENCIES = [
    "numpy",           # For numeric operations
    "pandas",          # For data analysis
    "opencv-python",   # For video processing
    "matplotlib",      # For visualization/plotting
    "Pillow"          # Required by matplotlib
]

# Additional hidden dependencies for PyInstaller
HIDDEN_DEPENDENCIES = [
    "setuptools",
    "jaraco.text",
    "jaraco.classes",
    "jaraco.collections",
    "importlib_metadata",
    "importlib_resources",
    "more_itertools",
    "packaging"
]

# Modules to exclude from the build (same as Windows)
DEFAULT_EXCLUDED_MODULES = [
    # GUI frameworks that conflict with PySide6
    "PyQt5", "PyQt6", "wx", "tkinter", "gtk",
    
    # Data science and ML libraries (except what we need)
    "scipy", "sklearn", "seaborn", "statsmodels",
    "tensorflow", "torch", "keras", "theano", "xgboost", "lightgbm",
    
    # Web frameworks
    "django", "flask", "fastapi", "tornado", "aiohttp", "requests", "urllib3",
    "httplib2", "boto3", "botocore", "aws", "azure", "google",
    
    # Development tools
    "pytest", "unittest", "nose", "sphinx", "jinja2", "IPython", "jupyter",
    "notebook", "ipykernel", "black", "flake8", "mypy", "pylint",
    
    # Database libraries
    "sqlite3", "psycopg2", "mysql", "pymongo", "sqlalchemy", "alembic",
    
    # Image processing (keeping only PIL/Pillow)
    "imageio",
    
    # Other large libraries
    "h5py", "sympy", "dask", "numba", "distributed", "bokeh", "panel",
    
    # Documentation
    "doc", "pydoc_data", "docutils", "alabaster", "babel",
    
    # Unused standard library
    "distutils", "lib2to3", "ensurepip", "venv", "turtledemo",
    
    # Python internals
    "test", "tests", "testing", "pip", "wheel", "easy_install"
]

# Mac-specific binaries to exclude (equivalent to Windows DLLs)
DEFAULT_EXCLUDED_BINARIES_MAC = [
    # Qt modules not needed
    'QtDBus',
    'QtDesigner',
    'QtHelp',
    'Qt3D',
    'QtBluetooth',
    'QtLocation',
    'QtNfc',
    'QtPositioning',
    'QtQuick3D',
    'QtRemoteObjects',
    'QtSensors',
    'QtSerialPort',
    'QtWebChannel',
    'QtWebEngine',
    'QtWebSockets',
    
    # Unused Qt plugins
    'sqldrivers',
    'sceneparsers',
    'geometryloaders',
    'webview',
    
    # Development/debug libraries
    '_debug',
    'd.dylib',  # Debug versions
    
    # Unused frameworks
    'Tcl.framework',
    'Tk.framework',
]

def ensure_required_directories():
    """Ensure required directories exist."""
    print("Ensuring required directories exist...")
    
    required_dirs = ["resources", "logs", "projects", "configs"]
    
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
            print(f"Created missing directory: {dir_name}")
    
    # Create default configs if they don't exist
    create_default_configs()
    
    return True

def create_default_configs():
    """Create default configuration files."""
    # Default action map
    action_map_path = os.path.join("configs", "default_action_map.json")
    if not os.path.exists(action_map_path):
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
        with open(action_map_path, 'w') as f:
            json.dump(default_mappings, f, indent=2)
        print(f"Created default action map: {action_map_path}")
    
    # Default metrics config
    metrics_path = os.path.join("configs", "default_metrics.json")
    if not os.path.exists(metrics_path):
        default_metrics = {
            "latency_metrics": [
                {"name": "Attack Latency", "behavior": "Attack bites", "enabled": True}
            ],
            "total_time_metrics": [
                {
                    "name": "Total Aggression",
                    "behaviors": ["Attack bites", "Sideways threats", "Tail rattles", "Chasing"],
                    "enabled": True
                }
            ]
        }
        with open(metrics_path, 'w') as f:
            json.dump(default_metrics, f, indent=2)
        print(f"Created default metrics configuration: {metrics_path}")

def install_dependencies():
    """Install required dependencies."""
    print("Installing required dependencies...")
    
    try:
        # Install PyInstaller
        subprocess.check_call([sys.executable, "-m", "pip", "install", "PyInstaller>=6.0.0"])
        
        # Install hidden dependencies
        for dep in HIDDEN_DEPENDENCIES:
            print(f"Installing {dep}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
        
        return True
    except Exception as e:
        print(f"Error installing dependencies: {str(e)}")
        return False

def create_mac_spec_content(args, icon_path=None):
    """Create optimized spec file content for macOS."""
    
    # Prepare excluded modules list
    modules_to_exclude = DEFAULT_EXCLUDED_MODULES.copy()
    
    # Hidden imports
    hidden_imports_list = [
        'vlc',
        'setuptools',
        'pkg_resources',
        'matplotlib.backends.backend_qt5agg',
        'PIL',
        'PIL.Image',
    ] + HIDDEN_DEPENDENCIES
    
    # Icon option for EXE
    icon_option = f", icon='{icon_path}'" if icon_path and os.path.exists(icon_path) else ""
    
    # Icon value for BUNDLE (must be a string literal or None)
    bundle_icon = f"'{icon_path}'" if icon_path and os.path.exists(icon_path) else "None"
    
    spec_content = f"""
# -*- mode: python ; coding: utf-8 -*-
# RABET optimized spec file for macOS

import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Modules to exclude
excluded_modules = {repr(modules_to_exclude)}

# Mac-specific binaries to exclude
excluded_binaries_mac = {repr(DEFAULT_EXCLUDED_BINARIES_MAC)}

# Data files
datas = []
if os.path.exists('resources'):
    datas.append(('resources', 'resources'))
if os.path.exists('configs'):
    datas.append(('configs', 'configs'))

# Hidden imports
hiddenimports = {repr(hidden_imports_list)}

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
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

# Filter out excluded binaries (Mac-specific)
def should_exclude_binary(binary_tuple):
    name = binary_tuple[0]
    for excluded in excluded_binaries_mac:
        if excluded in name:
            return True
    # Also exclude debug symbols and test files
    if name.endswith('_debug.dylib') or '_test' in name or '/test/' in name:
        return True
    return False

a.binaries = TOC([x for x in a.binaries if not should_exclude_binary(x)])

# Remove unnecessary data files
a.datas = TOC([x for x in a.datas if not any(exc in x[0] for exc in ['test/', 'tests/', 'examples/', 'docs/'])])

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
    strip=True,  # Strip symbols on Mac
    upx=False,   # UPX often causes issues on Mac
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,  # Important for Mac
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None{icon_option},
)

# Create .app bundle
app = BUNDLE(
    exe,
    name='RABET.app',
    icon={bundle_icon},
    bundle_identifier='com.rabet.app',
    info_plist={{
        'NSHighResolutionCapable': 'True',
        'LSMinimumSystemVersion': '10.15.0',
    }},
)
"""
    return spec_content

def perform_post_build_cleanup(verbose=False):
    """Perform post-build cleanup specific to macOS."""
    print("\nPerforming post-build cleanup...")
    
    if os.path.exists("dist/RABET.app"):
        app_contents = "dist/RABET.app/Contents"
        
        # Clean up unnecessary files in the app bundle
        cleanup_paths = [
            f"{app_contents}/MacOS/PySide6/examples",
            f"{app_contents}/MacOS/PySide6/translations",  # Keep only English
            f"{app_contents}/MacOS/matplotlib/mpl-data/sample_data",
            f"{app_contents}/Resources/test",
            f"{app_contents}/Resources/tests",
        ]
        
        for path in cleanup_paths:
            if os.path.exists(path):
                if os.path.isdir(path):
                    shutil.rmtree(path)
                    print(f"  Removed: {path}")
                else:
                    os.remove(path)
                    print(f"  Removed: {path}")
        
        # Keep only essential Qt translations
        trans_dir = f"{app_contents}/MacOS/PySide6/Qt/translations"
        if os.path.exists(trans_dir):
            for file in os.listdir(trans_dir):
                if not file.startswith('qt_en'):
                    file_path = os.path.join(trans_dir, file)
                    if os.path.isfile(file_path):
                        os.remove(file_path)

def main():
    """Build RABET for macOS distribution."""
    parser = argparse.ArgumentParser(description="Build RABET for macOS distribution")
    parser.add_argument("--no-cleanup", action="store_true", help="Skip post-build cleanup")
    parser.add_argument("--verbose", action="store_true", help="Show verbose output")
    args = parser.parse_args()
    
    if platform.system() != "Darwin":
        print("Warning: This script is optimized for macOS. Running on", platform.system())
    
    print("===== Building RABET for macOS =====")
    start_time = time.time()
    
    # Install dependencies
    if not install_dependencies():
        print("Warning: Some dependencies failed to install")
    
    # Ensure directories exist
    ensure_required_directories()
    
    # Clean build directories
    for dir_name in ["build", "dist"]:
        if os.path.exists(dir_name):
            print(f"Cleaning {dir_name} directory...")
            shutil.rmtree(dir_name)
    
    # Find icon
    icon_path = None
    for path in ["resources/RABET.icns", "resources/RABET.ico", "RABET.icns"]:
        if os.path.exists(path):
            icon_path = path
            break
    
    # Create spec file
    spec_content = create_mac_spec_content(args, icon_path)
    with open("RABET_mac.spec", "w") as f:
        f.write(spec_content)
    
    print("\nBuilding with PyInstaller...")
    
    # Build command
    cmd = ["pyinstaller", "RABET_mac.spec", "--noconfirm", "--clean"]
    
    try:
        if args.verbose:
            subprocess.check_call(cmd)
        else:
            subprocess.check_call(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        print(f"Error: PyInstaller failed with exit code {e.returncode}")
        sys.exit(1)
    
    # Post-build cleanup
    if not args.no_cleanup:
        perform_post_build_cleanup(args.verbose)
    
    # Calculate final size
    if os.path.exists("dist/RABET.app"):
        size = sum(os.path.getsize(os.path.join(dirpath, filename))
                  for dirpath, dirnames, filenames in os.walk("dist/RABET.app")
                  for filename in filenames)
        print(f"\nFinal app size: {size / (1024*1024):.1f} MB")
    
    end_time = time.time()
    print(f"\nBuild completed in {end_time - start_time:.1f} seconds")
    print("App bundle created at: dist/RABET.app")

if __name__ == "__main__":
    main()
