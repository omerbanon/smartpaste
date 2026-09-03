# SmartPaste

macOS menu bar app that converts clipboard content between formats and rephrases text with AI.

**Cmd+Shift+V** to activate.

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
pip install -r requirements.txt

# Build the app
pip install py2app Pillow
python setup.py py2app

# Install
cp -R dist/SmartPaste.app /Applications/
open /Applications/SmartPaste.app
```

Grant **Accessibility** permission when prompted (System Settings > Privacy & Security > Accessibility).

## Usage

SmartPaste lives in the menu bar (CmdV icon, top-right of screen).

1. Copy any text
2. Press **Cmd+Shift+V**
3. Pick a format or press **A** for AI rephrase

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

All settings are stored in `~/.smartpaste/config.json`. Edit directly or use **Settings...** from the menu bar icon.

```json
{
  "api_key": "sk-ant-api03-...",
  "model": "claude-haiku-4-5-20251001",
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

**First launch** opens a setup wizard (API key, system prompt, presets, model choice).

### Available Models

| Model | Description |
|-------|-------------|
| `claude-haiku-4-5-20251001` | Fast, cheap (default) |
| `claude-sonnet-4-5-20250929` | Balanced |

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
