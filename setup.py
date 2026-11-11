"""py2app build configuration for SmartPaste.app.

Build with:
    pip install -r requirements.txt py2app Pillow   (or: pip install ".[dev]")
    rm -rf build dist
    python setup.py py2app
    open dist/SmartPaste.app
"""

import importlib.util
import re
import sys
from pathlib import Path

from setuptools import setup

if sys.version_info < (3, 10):
    sys.exit(
        f"SmartPaste requires Python 3.10+ (found {sys.version.split()[0]} at {sys.executable}).\n"
        "On macOS, `python3` is often Apple's Python 3.9. Create the venv with a newer interpreter, e.g.:\n"
        "    brew install python@3.12 && python3.12 -m venv .venv"
    )

APP = ["smartpaste/__main__.py"]

# Single source of truth for the version: smartpaste/__init__.py
VERSION = re.search(
    r'^__version__ = "([^"]+)"', (Path(__file__).parent / "smartpaste" / "__init__.py").read_text(), re.M
).group(1)

DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,  # critical for rumps menu bar apps
    "plist": {
        "CFBundleName": "SmartPaste",
        "CFBundleDisplayName": "SmartPaste",
        "CFBundleIdentifier": "com.smartpaste.app",
        "CFBundleVersion": VERSION,
        "CFBundleShortVersionString": VERSION,
        "LSUIElement": True,  # no Dock icon
        "NSAppleEventsUsageDescription": "SmartPaste needs accessibility access for global hotkeys.",
    },
    # Top-level packages to bundle whole. Third-party HTTP deps are listed as
    # candidates because they differ across anthropic versions (0.x pulls in
    # httpx/httpcore/certifi, 1.x pulls in httpx2/httpcore2/truststore); only
    # the ones actually installed are included so the build never fails on a
    # package that isn't there.
    "packages": [
        pkg
        for pkg in [
            "smartpaste",
            "objc",
            "AppKit",
            "Foundation",
            "WebKit",
            "Quartz",
            "Security",
            "ServiceManagement",
            "quickmachotkey",
            "anthropic",
            "httpx",
            "httpx2",
            "httpcore",
            "httpcore2",
            "truststore",
            "anyio",
            "sniffio",
            "certifi",
            "idna",
            "h11",
            "markdown",
            "pymdownx",
            "pygments",
            "markdownify",
            "bs4",
            "soupsieve",
            "six",
            "rumps",
        ]
        if importlib.util.find_spec(pkg) is not None
    ],
    "includes": [
        "html",
        "html.parser",
        "importlib",
        "importlib.util",
        "markdown.extensions.tables",
        "markdown.extensions.fenced_code",
        "markdown.extensions.codehilite",
        "markdown.extensions.nl2br",
        "markdown.extensions.sane_lists",
        "markdown.extensions.smarty",
        "pymdownx.tilde",
    ],
    "excludes": [
        "tkinter",
        "unittest",
        "numpy",
        "scipy",
        "pandas",
        "matplotlib",
        "PIL",
        "test",
        "distutils",
        "setuptools",
    ],
}



def _py2app_cmdclass() -> dict:
    """Undo two things setuptools now fills from pyproject.toml, for py2app only:

    - install_requires (from [project.dependencies]): py2app refuses to run
      when it's set. The app bundles whatever is installed in the venv.
    - packages (from [tool.setuptools]): py2app would also put smartpaste into
      python312.zip, which is first on sys.path, so the app imports the zipped
      copy and can't open smartpaste/icon.png ("Launch error"). OPTIONS
      ["packages"] already copies smartpaste as a real folder.
    """
    try:
        from py2app.build_app import py2app as _py2app
    except ImportError:  # plain `pip install .` without py2app
        return {}

    class py2app(_py2app):
        def finalize_options(self):
            self.distribution.install_requires = []
            self.distribution.packages = []
            self.distribution.package_data = {}
            super().finalize_options()

    return {"py2app": py2app}


setup(
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    cmdclass=_py2app_cmdclass(),
)
