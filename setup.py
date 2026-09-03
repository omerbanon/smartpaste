"""py2app build configuration for SmartPaste.app.

Build with:
    pip install py2app
    rm -rf build dist
    python setup.py py2app
    open dist/SmartPaste.app
"""

import importlib.util
import sys

from setuptools import setup

if sys.version_info < (3, 10):
    sys.exit(
        f"SmartPaste requires Python 3.10+ (found {sys.version.split()[0]} at {sys.executable}).\n"
        "On macOS, `python3` is often Apple's Python 3.9. Create the venv with a newer interpreter, e.g.:\n"
        "    brew install python@3.12 && python3.12 -m venv .venv"
    )

APP = ["smartpaste/__main__.py"]

DATA_FILES = []

OPTIONS = {
    "argv_emulation": False,  # critical for rumps menu bar apps
    "plist": {
        "CFBundleName": "SmartPaste",
        "CFBundleDisplayName": "SmartPaste",
        "CFBundleIdentifier": "com.smartpaste.app",
        "CFBundleVersion": "0.1.0",
        "CFBundleShortVersionString": "0.1.0",
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
            "rumps",
            "dotenv",
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

setup(
    app=APP,
    name="SmartPaste",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
