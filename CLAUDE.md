# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

iTeroToolBox is a Windows-only desktop diagnostic and administration tool for iTero/Cadent dental scanners. It provides a GUI for field technicians to run network diagnostics, manage Windows services, clean installations, generate reports, and interact with scanner-specific workflows.

## Tech Stack

- **Language**: Python (backend), HTML/CSS/JavaScript (frontend UI)
- **GUI**: PyWebView 4.4.1 (embeds EdgeChromium browser in a native window)
- **Packaging**: PyInstaller (produces a single `.exe`)
- **Windows APIs**: `winreg`, `pywin32`, `psutil`, `subprocess` (cmd.exe, PowerShell, sc.exe, reg.exe)

## Development Setup

Install dependencies:
```bash
pip install pywebview==4.4.1 pywin32 psutil pyinstaller openpyxl
```

Run locally (requires Windows, admin rights recommended):
```bash
python itero_toolbox.py
```

Build the standalone EXE:
```bash
build.bat
# Output: dist/iTero_Toolbox_V1.exe
```

There are no automated tests.

## Architecture

The app has two layers that communicate via PyWebView's JS bridge:

### Backend (`itero_toolbox.py` + `backend.py`)

- **`itero_toolbox.py`** is the entry point. It initializes the PyWebView window, loads `itero_toolbox_v1.html`, and exposes `ToolboxAPI` to JavaScript as `window.pywebview.api`.
- **`ToolboxAPI`** (in `itero_toolbox.py`) is a thin dispatch layer: each method validates/extracts parameters from the JS call, then delegates to a function in `backend.py`.
- **`backend.py`** contains all business logic. Every public function returns the same JSON structure:
  ```python
  {"status": "ok"|"error", "data": ..., "msg": "", "ts": "HH:MM:SS"}
  ```
- **`backend._run()`** (line 24) is the core helper for all shell subprocess calls — always use it rather than calling `subprocess.run()` directly.

### Frontend (`itero_toolbox_v1.html`)

A single self-contained HTML file (~233KB) with all CSS and JavaScript embedded. No external dependencies, no bundler. JavaScript calls backend methods via `window.pywebview.api.<method>(args)`, which returns a Promise. Results update the DOM directly.

### Data Flow

```
User action in browser → JS handler → window.pywebview.api.method()
    → ToolboxAPI method (itero_toolbox.py) → backend.py function
    → subprocess / winreg / psutil call → JSON response
    → JS promise resolution → DOM update
```

## Key Backend Modules (backend.py)

| Area | Lines | What it does |
|---|---|---|
| `health_check()` | 76–189 | Full system diagnostics (network, services, processes) |
| Network functions | 196–275 | ping, ipconfig, WiFi info, DNS flush, IPv6 toggle |
| Battery | 276–336 | Generate Windows battery report, parse health |
| Service ops | 337–362 | Start/stop/query Windows services via `sc.exe` |
| Registry | 363–432 | Read/write Windows registry keys via `winreg` |
| Kill iTero | 434–468 | `taskkill` on 35+ iTero/Cadent process names |
| Clean install | 470–520 | Remove Cadent folders and registry keys |
| Transfer service | 522–548 | Configure folder sharing and passwordless access |
| Excel generation | 671–804 | Build `.xlsx` files for Link/Unlink SFDC requests |

## Important Conventions

- **Admin elevation**: Many operations require admin rights. The app can self-elevate via `ShellExecuteW(..., "runas", ...)`. Admin check is `is_admin()` in `itero_toolbox.py`.
- **EdgeChromium forced**: `os.environ["PYWEBVIEW_GUI"] = "edgechromium"` is set at startup — do not remove this.
- **Reference images**: Scanner wand diagrams live in `Reference/WOA/` and `Reference/Lumina/`. The `YUC_BLX/` subdirectory is currently empty/placeholder.
- **Generated files**: Link/Unlink Excel files are written to `LinkUnlink/` at runtime.
- **No config files**: There is no `pyproject.toml`, `setup.py`, or `.env`. All configuration is hardcoded or registry-based.
