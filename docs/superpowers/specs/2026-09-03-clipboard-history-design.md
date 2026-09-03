# Clipboard history: design

Date: 2026-09-03. Status: draft, waiting for Omer's approval.

## What it does

SmartPaste remembers the last 15 things you copied. Press Cmd+Shift+V, then L,
and the popup shows that list. Pick one and it becomes the text the app is
working on: it goes onto the clipboard and the format list comes back for it.
From there you Esc and Cmd+V to paste it as is, or convert it to Slack, Docs,
AI and so on, exactly like text you just copied.

## Rules

- Text only. Images and files are ignored.
- 15 items, newest first. The 16th pushes the oldest out.
- Copying the same text again moves it to the top instead of adding a duplicate.
- Copies SmartPaste itself makes (converted output, AI results) are not recorded,
  so the list holds what you copied, not what the app produced.
- Anything a password manager marks as concealed or transient is skipped.
- Memory only. Nothing is written to disk. Quit the app and the list is empty.
- Whitespace-only copies are skipped.

## How the app notices a copy

macOS has no "clipboard changed" event. The standard way is to poll the
pasteboard change counter. A timer on the main thread checks it twice a second
(cheap: one integer read). When the counter moves and the content is text, the
item is pushed to the history.

## The list

Same panel, same dark style, same row height as the format list.

```
┌────────────────────────────────────────┐
│ Clipboard History              [x]     │
├────────────────────────────────────────┤
│ ▦  Name,Age,City  Alice,30,Paris   2m  │
│ M  # Report  Some text, with…      5m  │
│ >_ $ ls -la  total 8  drwxr…       9m  │
│ T  Hey, can you check the…        21m  │
│ …                                      │
├────────────────────────────────────────┤
│ ↑↓ Move   ↩ Use   ⌫ Delete   Esc Back  │
└────────────────────────────────────────┘
```

Each row: an icon for the detected type (table, markdown, code, terminal,
plain), the first line of the text trimmed to fit, and how long ago it was
copied. The item currently on the clipboard is marked so you know where you
are.

Keys inside the list:

| Key | Does |
|---|---|
| Up / Down, 1-9 | Move / jump |
| Enter, click | Use this item: write it to the clipboard, show the format list for it |
| Backspace / Delete | Remove the highlighted item from the list |
| P | Preview the highlighted item (same preview panel) |
| Esc | Back to the format list, nothing changes |

The footer of the format list gains "L History". If the list is empty, L shows
the panel with one line: "Nothing copied yet".

## Where the code goes

| Piece | File | Why |
|---|---|---|
| Watcher + ring buffer + rules | `smartpaste/history.py` (new) | Pure Python except the pasteboard read, so the rules are unit-testable |
| The list panel | `smartpaste/history_panel.py` (new) | popup.py is already 1,380 lines; the list gets its own module and reuses the row/close-button views from popup.py |
| Wiring | `app.py`, `popup.py` | Start the watcher at launch, add the L key and footer hint, hand the chosen text back to the popup |
| Own-write guard | `clipboard.py` | `write_clipboard` records the change counter it produced so the watcher can skip it |

## Testing

- Unit tests for the ring buffer: cap at 15, newest first, duplicate moves to
  top, whitespace skipped, own writes skipped, delete by index.
- Panel: manual check on the built app (open, navigate, use, delete, preview,
  empty state).

## Out of scope for now

Search box, pinning favourites, saving across restarts, images, a second hotkey.
Any of these can come later without changing the design above.
