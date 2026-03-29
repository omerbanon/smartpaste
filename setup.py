"""py2app build configuration for SmartPaste.app.

Build with:
    pip install py2app
    rm -rf build dist
    python setup.py py2app
    open dist/SmartPaste.app
"""

from setuptools import setup

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
    "packages": [
        "smartpaste",
        "objc",
        "AppKit",
        "Foundation",
        "WebKit",
        "Quartz",
        "quickmachotkey",
        "anthropic",
        "httpx",
        "httpcore",
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
