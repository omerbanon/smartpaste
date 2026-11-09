# SmartPaste

macOS menu bar app that converts clipboard content between formats and rephrases text with AI.

**Cmd+Shift+V** to activate (change it from the menu bar icon > **Hotkey**).

## Install

```bash
# Clone and set up
git clone https://github.com/omerbanon/smartpaste.git
cd smartpaste

# Needs Python 3.10+. On macOS, plain `python3` is often Apple's Python 3.9,
# which builds fine but the app then dies on launch with a py2app "Launch error".
# py2app also needs a framework build, so use Homebrew (or python.org) Python:
brew install python@3.12
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"   # runtime deps + pytest, ruff, py2app, Pillow

# Build the app
python setup.py py2app

# Install
cp -R dist/SmartPaste.app /Applications/
open /Applications/SmartPaste.app
```

Grant **Accessibility** permission when prompted (System Settings > Privacy & Security > Accessibility).

## Usage

SmartPaste lives in the menu bar (CmdV icon, top-right of screen).

1. Copy any text
2. Press **Cmd+Shift+V** (or your own hotkey)
3. Pick a format or press **A** for AI rephrase
4. Press **Cmd+V** in your app. Or turn on **Paste Automatically** in the menu bar icon and SmartPaste
   pastes for you after you pick a format (needs Accessibility permission).

### Format Options

Detects content type automatically (Markdown, Code, Table, Terminal, Plain Text) and offers:

- **Google Docs / Confluence / Jira** — rich HTML paste
- **Gmail** — email-friendly HTML
- **Slack** — Slack-compatible formatting
- **CLI** — compact plain text
- **AI Rephrase** — rewrite with Claude (fix grammar, summarize, translate, etc.)

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1-6` | Quick-pick format |
| `A` | Open AI rephrase |
| `P` | Preview rendered output |
| `Enter` | Select highlighted option |
| `Esc` | Cancel / go back |

## Config

Settings are stored in `~/.smartpaste/config.json`. Edit directly or use **Settings...** from the menu bar icon.

The Anthropic API key is **not** in that file: it's saved in your login Keychain (item
`com.smartpaste.app`, viewable in Keychain Access). A key left in `config.json` by an older version
is moved to the Keychain on the next launch. To set it by hand, add `"api_key"` to the file and
relaunch; it will be moved the same way.

```json
{
  "model": "claude-haiku-5-5",
  "hotkey": "cmd+shift+v",
  "auto_paste": false,
  "system_prompt": "You are a text reformatting assistant...",
  "presets": [
    "Fix grammar and spelling",
    "Make more concise",
    "Summarize in 2-3 sentences",
    "Convert to bullet points",
    "Make more formal / professional",
    "Format as a Slack message"
  ]
}
```

Set `"debug": true` (or run with `SMARTPASTE_DEBUG=1`) for verbose logs. Logs default to INFO and
never contain clipboard text or AI prompts.

`hotkey` takes modifiers (`cmd`, `ctrl`, `option`, `shift`) and one key (`a`-`z`, `0`-`9`, `f1`-`f20`,
`space`), joined with `+`. Cmd+Shift+V is "Paste and Match Style" in Google Docs, Chrome, Slack and
Notion, so pick another one (Hotkey > Record Shortcut...) if you use that.

**First launch** opens a setup wizard (API key, system prompt, presets, model choice).

### Available Models

| Model | Description |
|-------|-------------|
| `claude-haiku-5-5` | Fast, cheap (default) |
| `claude-sonnet-5-5` | Balanced |
| `claude-opus-5-5` | Most capable, slower |

Settings also lists any other model your API key can use (from the Models API). A saved model
that is no longer in the list keeps working.

## Quit / Restart

- **Quit:** Click the menu bar icon > Quit SmartPaste
- **Force quit:** `pkill -9 -f SmartPaste`
- **Rebuild after changes:**

```bash
pkill -9 -f SmartPaste
cd /path/to/smartpaste
rm -rf build dist
source .venv/bin/activate
python setup.py py2app
rm -rf /Applications/SmartPaste.app
cp -R dist/SmartPaste.app /Applications/
open /Applications/SmartPaste.app
```

## Run from Source (development)

```bash
cd smartpaste
source .venv/bin/activate
python -m smartpaste
```

Tests and lint:

```bash
pytest
ruff check .
```

The version lives in one place, `smartpaste/__init__.py` (`__version__`). `setup.py` and
`pyproject.toml` both read it. Bump it there, then tag the release (`git tag v0.3.0`).

## Requirements

- macOS 13+
- Python 3.10+ as a framework build (Homebrew `python@3.12` or python.org). Apple's bundled Python 3.9 and uv-managed Pythons won't work with py2app.
- Anthropic API key (for AI features)

## Troubleshooting

**"Launch error – See the py2app website for debugging launch issues"** when opening the app:
run the binary directly to see the real traceback:

```bash
/Applications/SmartPaste.app/Contents/MacOS/SmartPaste
```

If it ends in `TypeError: unsupported operand type(s) for |: 'type' and 'NoneType'`, the app was
built with Python 3.9. Recreate the venv with Python 3.10+ (see Install) and rebuild.
