"""
iTero Support Toolbox — V1.2
Entry point. Launches PyWebView window loading the HTML frontend.
Do NOT run as Administrator — WebView2 refuses to create its data
directory when the host process is elevated (a Chromium security
restriction, not something this app controls), so the window never
opens at all under an elevated session.

Usage:
    python itero_toolbox.py
    OR double-click itero_toolbox.exe (built with build.bat)
"""

import sys
import os
import ctypes
import json
import threading
from pathlib import Path

# A --windowed/onefile build has no console, so PyInstaller leaves
# sys.stdout/sys.stderr genuinely UNSET (not just None — the attribute
# doesn't exist at all, so even `sys.stdout is None` raises AttributeError;
# has to be checked with getattr). Any print() anywhere in the app (there
# are plenty, e.g. the hotkey listener) then raises RuntimeError("lost
# sys.stdout") and kills whatever thread hit it, silently, with no console
# to ever show it. Redirecting to a log file instead of just swallowing it
# means a real trail exists next time something only breaks in the built
# exe and not when run from source.
if getattr(sys, 'stdout', None) is None or getattr(sys, 'stderr', None) is None:
    try:
        _log_dir = Path(os.environ.get('APPDATA', '.')) / 'iTeroToolBox'
        _log_dir.mkdir(parents=True, exist_ok=True)
        _log_file = open(_log_dir / 'app.log', 'a', encoding='utf-8', buffering=1)
        if getattr(sys, 'stdout', None) is None:
            sys.stdout = _log_file
        if getattr(sys, 'stderr', None) is None:
            sys.stderr = _log_file
    except Exception:
        # Last resort — a no-op stream so print() at least can't crash
        # anything, even if we can't get a log file for some reason.
        class _NullStream:
            def write(self, *a, **k): pass
            def flush(self, *a, **k): pass
        if getattr(sys, 'stdout', None) is None:
            sys.stdout = _NullStream()
        if getattr(sys, 'stderr', None) is None:
            sys.stderr = _NullStream()

# Force EdgeChromium backend — no pythonnet required
os.environ["PYWEBVIEW_GUI"] = "edgechromium"

import webview
import backend

_window = None  # global window reference for win control API


# ─────────────────────────────────────────────
# PYWEBVIEW API
# ─────────────────────────────────────────────

class ToolboxAPI:
    """
    Exposed to JavaScript via window.pywebview.api.*
    All methods must return JSON strings.
    """

    # ── Health ──────────────────────────────
    def health_check(self):
        return backend.health_check()

    # ── Networking ──────────────────────────
    def run_ipconfig(self):
        return backend.run_ipconfig()

    def run_ping(self, target="8.8.8.8"):
        return backend.run_ping(target)

    def get_wifi_details(self):
        return backend.get_wifi_details()

    def generate_network_report(self):
        return backend.generate_network_report()

    # ── Battery ─────────────────────────────
    def generate_battery_report(self):
        return backend.generate_battery_report()

    def read_battery_report(self, path):
        return backend.read_battery_report(path)

    def get_battery_events(self):
        return backend.get_battery_events()

    # ── Registry ────────────────────────────
    def open_regedit(self, key_path=None):
        return backend.open_regedit(key_path)

    # ── Kill iTero ──────────────────────────
    def kill_all_itero(self):
        return backend.kill_all_itero()

    # ── System tools ────────────────────────
    def open_device_manager(self):
        return backend.open_device_manager()

    def open_event_viewer(self):
        return backend.open_event_viewer()

    def open_log_collector(self, output_path=r"C:\Temp\Logs"):
        return backend.open_log_collector(output_path)

    def launch_slfdd_driver(self):
        return backend.launch_slfdd_driver()

    def launch_slfdd_utility(self):
        return backend.launch_slfdd_utility()

    def open_url_in_browser(self, url):
        return backend.open_url_in_browser(url)

    def open_html_file(self, path):
        return backend.open_html_file(path)

    def get_filter_events(self, event_ids="41,12,105", max_events=15):
        return backend.get_filter_events(event_ids, max_events)

    # ── Generic CMD (used by CMD panel) ─────
    def run_cmd(self, cmd):
        return backend.run_arbitrary_cmd(cmd)

    def open_woa_collage(self, agent_email=""):
        return backend.open_woa_collage(agent_email)

    def generate_link_unlink_excel(self, data):
        return backend.generate_link_unlink_excel(data)

    def esc_report_export(self, entries=None, agent_name=""):
        return backend.esc_report_export(entries or [], agent_name)

    def esc_report_sf_lookup(self, ticket_number="", close_after=True):
        return backend.esc_report_sf_lookup(ticket_number, close_after)

    def open_woa_collage_folder(self, path):
        return backend.open_woa_collage_folder(path)

    def open_collage_by_b64(self, collage_type, b64_data):
        return backend.open_collage_by_b64(collage_type, b64_data)

    def open_collage_file(self, collage_type):
        return backend.open_collage_file(collage_type)

    def get_catalog_parts(self, model=""):
        return backend.get_catalog_parts(model)

    # ── User Profile ────────────────────────
    def get_user_profile(self):
        return backend.get_user_profile()

    def save_user_profile(self, name="", role=""):
        return backend.save_user_profile(name, role)

    def clear_user_profile(self):
        return backend.clear_user_profile()

    # ── Hotkeys ──────────────────────────────
    def get_hotkeys(self):
        return backend.get_hotkeys()

    def save_hotkeys(self, data):
        return backend.save_hotkeys(data)

    def get_hotkey_status(self):
        return backend.get_hotkey_status()

    def test_type_text(self, delay_sec=2):
        return backend.test_type_text(delay_sec)

    # ── MAT (myaligntech.com) ────────────────
    def mat_save_credentials(self, email="", password="", show_browser=False, enabled=True):
        return backend.mat_save_credentials(email, password, show_browser, enabled)

    def mat_get_settings(self):
        return backend.mat_get_settings()

    def mat_set_enabled(self, enabled):
        return backend.mat_set_enabled(enabled)

    def mat_save_show_browser(self, show_browser):
        return backend.mat_save_show_browser(show_browser)

    def mat_scrape(self, serial=""):
        return backend.mat_scrape(serial)

    def mat_close_browser(self):
        return backend.mat_close_browser()

    def mat_logout(self):
        return backend.mat_logout()

    # ── Salesforce (SF) — ticket checker ────
    def sf_open_home(self):
        return backend.sf_open_home()

    def sf_open_ticket(self, ticket_number=""):
        return backend.sf_open_ticket(ticket_number)

    def sf_read_ticket(self):
        return backend.sf_read_ticket()

    def sf_close_browser(self):
        return backend.sf_close_browser()

    def sf_logout(self):
        return backend.sf_logout()

    def sf_load_settings(self):
        return backend.sf_load_settings()

    def sf_save_settings(self, show_browser=False):
        return backend.sf_save_settings(show_browser)

    def get_debug_mode(self):
        return backend.get_debug_mode()

    def set_debug_mode(self, enabled=False):
        return backend.set_debug_mode(enabled)

    def get_cmd_visible(self):
        return backend.get_cmd_visible()

    def set_cmd_visible(self, enabled=False):
        return backend.set_cmd_visible(enabled)

    # ── KB data (Subject Constructor) ───────
    def get_kb_data(self):
        return backend.get_kb_data()

    # ── Window chrome ────────────────────────
    def win_minimize(self):
        global _window
        try:
            if _window:
                _window.minimize()
        except Exception:
            pass
        return json.dumps({"status": "ok"})

    def win_maximize(self):
        global _window
        try:
            import win32gui, win32con
            hwnd = win32gui.FindWindow(None, _window.title)
            state = win32gui.GetWindowPlacement(hwnd)[1]
            if state == win32con.SW_SHOWMAXIMIZED:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            else:
                win32gui.ShowWindow(hwnd, win32con.SW_SHOWMAXIMIZED)
        except Exception:
            pass
        return json.dumps({"status": "ok"})

    def win_close(self):
        global _window
        try:
            if _window:
                _window.destroy()
        except Exception:
            pass
        return json.dumps({"status": "ok"})

    def win_tray(self):
        """'Run in background (Hotkeys only)' — hide the window and drop to
        a system tray icon. backend.start_hotkey_listener()'s thread keeps
        running untouched (it's independent of the window entirely); only
        the UI goes away. Restore via the tray icon's 'Open' item or a
        double-click; 'Exit' there fully quits, hotkeys included."""
        global _window
        try:
            _show_tray_icon()
            if _window:
                _window.hide()
        except Exception as e:
            return json.dumps({"status": "error", "msg": str(e)})
        return json.dumps({"status": "ok"})

    def win_lock_size(self, locked):
        global _window
        try:
            import win32gui, win32con
            hwnd = win32gui.FindWindow(None, _window.title)
            if hwnd:
                style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
                if locked:
                    new_style = style & ~win32con.WS_THICKFRAME
                else:
                    new_style = style | win32con.WS_THICKFRAME
                rect = win32gui.GetWindowRect(hwnd)
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
                topmost = win32con.HWND_TOPMOST if locked else win32con.HWND_NOTOPMOST
                win32gui.SetWindowPos(hwnd, topmost, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_FRAMECHANGED)
                if locked:
                    _lock_state["size"] = (rect[2] - rect[0], rect[3] - rect[1])
                    _start_lock_guard()
                else:
                    _lock_state["size"] = None
        except Exception:
            pass
        return json.dumps({"status": "ok"})

    def win_move(self, dx, dy):
        global _window
        try:
            import win32gui
            hwnd = win32gui.FindWindow(None, _window.title)
            if hwnd:
                rect = win32gui.GetWindowRect(hwnd)
                win32gui.MoveWindow(
                    hwnd,
                    rect[0] + int(dx), rect[1] + int(dy),
                    rect[2] - rect[0], rect[3] - rect[1],
                    True
                )
        except Exception:
            pass
        return json.dumps({"status": "ok"})


# ─────────────────────────────────────────────
# HTML PATH
# ─────────────────────────────────────────────

def get_html_path():
    """Resolve HTML file path — works both in dev and as frozen exe."""
    if getattr(sys, "frozen", False):
        # PyInstaller bundle
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "itero_toolbox_v1.html")


def get_icon_path():
    """Resolve the app icon path — works both in dev and as frozen exe."""
    if getattr(sys, "frozen", False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "Reference", "iterologo2.ico")


def _versioned_html_path(html_path):
    """Serve the HTML from a copy whose filename embeds a content hash.

    WebView2 keeps a persistent on-disk cache (storage_path below, needed
    so MAT/SF SSO sessions survive across launches). A plain file:// URL
    gets served stale from that cache after editing the source during
    dev; file:// URLs also don't reliably support cache-busting query
    strings. A version-stamped filename sidesteps both problems.

    Hashing the actual content (rather than using mtime) matters: mtime
    truncated to whole seconds means two edits saved within the same
    second produce the same filename, so the second edit would silently
    never get copied and the app would keep serving the first edit's
    snapshot even after a full restart.

    Kept next to the original (not in TEMP) so the HTML's relative asset
    paths (Reference/Mascot/...) still resolve.

    Never lets a failure here (locked file, AV scan, two instances
    launching close together and racing on the same filename, OneDrive
    sync, ...) crash the whole app before a window even exists — falls
    back to serving html_path directly, which just risks the original
    stale-cache symptom this function exists to avoid, instead of killing
    the launch outright.
    """
    try:
        import glob
        import hashlib
        base_dir = os.path.dirname(html_path)
        with open(html_path, "rb") as f:
            content = f.read()
        digest = hashlib.sha1(content).hexdigest()[:12]
        versioned = os.path.join(base_dir, f".itero_toolbox_v1_{digest}.html")
        if not os.path.exists(versioned):
            for stale in glob.glob(os.path.join(base_dir, ".itero_toolbox_v1_*.html")):
                try:
                    os.remove(stale)
                except OSError:
                    pass
            # Write to a per-process temp name and rename into place instead
            # of writing `versioned` directly — os.replace is atomic on the
            # same volume, so a process killed mid-write (or two instances
            # racing on this same digest) can never leave a truncated file
            # sitting at the hashed path, which `os.path.exists(versioned)`
            # above would otherwise trust forever on every later launch.
            tmp = versioned + f".tmp{os.getpid()}"
            with open(tmp, "wb") as f:
                f.write(content)
            os.replace(tmp, versioned)
        return versioned
    except Exception:
        return html_path


# ─────────────────────────────────────────────
# WINDOW CHROME
# ─────────────────────────────────────────────

def _enable_context_menu():
    """Re-enable WebView2's native right-click context menu (Cut/Copy/Paste
    and spelling suggestions on a misspelled word both live here).

    pywebview ties AreDefaultContextMenusEnabled to the same debug flag as
    AreDevToolsEnabled (see webview.platforms.edgechromium.on_webview_ready)
    — with debug off (the default here), WebView2 suppresses its whole
    native context menu. This flips just that one setting back on directly
    on the live CoreWebView2 instance, leaving AreDevToolsEnabled exactly
    as debug_mode set it.

    The write has to happen on the WinForms UI thread. pywebview's own
    webview.start() always runs the caller's func= (this whole call chain:
    _on_start -> _strip_caption -> here) on a plain background
    threading.Thread, never the thread that actually owns the WebView2
    COM control — writing the setting cross-thread doesn't raise (pythonnet
    property writes on a COM object don't get WinForms' usual
    cross-thread guard), so the assignment looked like it succeeded (no
    exception, logged as "Enabled") while never actually reaching the real
    browser. Control.Invoke() marshals it onto the right thread properly.

    Retries a few times with a short wait — the caller already waits 0.6s
    before the first attempt, but CoreWebView2 registering itself in
    BrowserView.instances is a separate async step that isn't guaranteed
    to have finished by then. Every attempt (and the final outcome) is
    logged rather than swallowed, since a silent failure here previously
    looked identical to "it just doesn't work" with no way to tell why.
    """
    import time
    for attempt in range(5):
        try:
            from webview.platforms.winforms import BrowserView
            inst = BrowserView.instances.get(_window.uid)
            browser = getattr(inst, "browser", None)
            web_view = getattr(browser, "web_view", None)
            core = web_view.CoreWebView2 if web_view else None
            if core and web_view:
                def _apply():
                    core.Settings.AreDefaultContextMenusEnabled = True
                if web_view.InvokeRequired:
                    from System.Windows.Forms import MethodInvoker
                    web_view.Invoke(MethodInvoker(_apply))
                else:
                    _apply()
                print(f'[CTXMENU] Enabled on attempt {attempt + 1} '
                      f'(marshaled={web_view.InvokeRequired})', flush=True)
                return
            print(f'[CTXMENU] attempt {attempt + 1}: CoreWebView2 not ready yet '
                  f'(inst={inst is not None}, browser={browser is not None})', flush=True)
        except Exception as e:
            print(f'[CTXMENU] attempt {attempt + 1} failed: {e}', flush=True)
        time.sleep(0.5)
    print('[CTXMENU] Gave up after 5 attempts — context menu / spellcheck '
          'suggestions may not work this session.', flush=True)


def _set_window_icon(hwnd):
    """Set the taskbar/title-bar icon directly on the live window.

    The frozen .exe already carries this icon as its own PE resource (see
    the .spec file's icon= setting), which Windows uses for the taskbar
    automatically. Running from source (`python itero_toolbox.py`) has no
    such resource — the taskbar would otherwise fall back to Python's own
    icon — so this loads the same .ico directly onto the window instead,
    covering both cases identically.
    """
    try:
        import win32gui, win32con
        icon_path = get_icon_path()
        if not os.path.exists(icon_path):
            return
        flags = win32con.LR_LOADFROMFILE
        hicon_big   = win32gui.LoadImage(0, icon_path, win32con.IMAGE_ICON, 32, 32, flags)
        hicon_small = win32gui.LoadImage(0, icon_path, win32con.IMAGE_ICON, 16, 16, flags)
        win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_BIG, hicon_big)
        win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_SMALL, hicon_small)
    except Exception:
        pass


_lock_state = {"size": None, "thread": None}


def _start_lock_guard():
    """Hold the window at its locked size.

    The caption/thickframe styles are stripped behind WinForms' back, so
    WinForms still believes the form has a full sizable caption frame.
    Whenever it re-applies its bounds — workstation lock/unlock, RDP
    reconnect, sleep/resume, docking, DPI or display changes — it re-adds
    that phantom caption + border on top of the real size, and the window
    grows a bit more each time. While locked, snap it back to the size it
    had when the lock was engaged.
    """
    t = _lock_state["thread"]
    if t and t.is_alive():
        return

    def _guard():
        import time
        import win32gui, win32con
        while _lock_state["size"] is not None:
            time.sleep(0.5)
            size = _lock_state["size"]
            if size is None:
                break
            try:
                hwnd = win32gui.FindWindow(None, _window.title)
                if not hwnd or win32gui.IsIconic(hwnd):
                    continue
                if win32gui.GetWindowPlacement(hwnd)[1] == win32con.SW_SHOWMAXIMIZED:
                    continue
                x, y, r, b = win32gui.GetWindowRect(hwnd)
                if (r - x, b - y) != size:
                    win32gui.SetWindowPos(hwnd, None, 0, 0, size[0], size[1],
                        win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE)
            except Exception:
                pass

    import threading
    t = threading.Thread(target=_guard, daemon=True)
    _lock_state["thread"] = t
    t.start()


def _strip_caption():
    """Remove native title bar; keep WS_THICKFRAME for resize. Fix DWM strip."""
    import time
    time.sleep(0.6)
    _enable_context_menu()
    try:
        import ctypes
        import win32gui, win32con

        hwnd = win32gui.FindWindow(None, _window.title)
        if not hwnd:
            return

        _set_window_icon(hwnd)

        # Remove caption, keep resize border
        style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        win32gui.SetWindowLong(
            hwnd, win32con.GWL_STYLE,
            (style & ~win32con.WS_CAPTION) | win32con.WS_THICKFRAME,
        )

        # DWM: color the leftover caption strip to match app background (#080b10 → 0x00100b08)
        try:
            DWMWA_CAPTION_COLOR = 35
            color = ctypes.c_int(0x00100b08)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_CAPTION_COLOR, ctypes.byref(color), 4)
        except Exception:
            pass

        # DWM: remove the Windows 11 accent border outline entirely (the thin
        # colored line that otherwise runs along the window edges, most visible
        # along the bottom on a captionless window) — resize via WS_THICKFRAME
        # keeps working, only the visible outline is hidden.
        try:
            DWMWA_BORDER_COLOR = 34
            DWMWA_COLOR_NONE = ctypes.c_int(0xFFFFFFFE - 0x100000000)  # signed repr of 0xFFFFFFFE
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_BORDER_COLOR, ctypes.byref(DWMWA_COLOR_NONE), 4)
        except Exception:
            pass

        # Force repaint
        win32gui.SetWindowPos(hwnd, None, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_FRAMECHANGED)

        # Micro-resize to force WebView2 child to fill the new client area
        time.sleep(0.15)
        rect = win32gui.GetWindowRect(hwnd)
        x, y, r, b = rect
        w, h = r - x, b - y
        win32gui.MoveWindow(hwnd, x, y, w + 1, h, True)
        time.sleep(0.05)
        win32gui.MoveWindow(hwnd, x, y, w, h, True)

    except Exception:
        pass


# ─────────────────────────────────────────────
# SYSTEM TRAY — "Run in background (Hotkeys only)"
# ─────────────────────────────────────────────

_tray_icon = None  # System.Windows.Forms.NotifyIcon, built once and reused


def _get_ui_control():
    """The live WebView2-hosting Control — the WinForms UI thread that owns
    pywebview's actual message loop. Every CLR call that has to land on
    that thread (not the background thread webview.start(func=...) itself
    runs on — see _enable_context_menu's docstring for why that
    distinction matters) is marshaled through this."""
    try:
        from webview.platforms.winforms import BrowserView
        inst = BrowserView.instances.get(_window.uid) if _window else None
        browser = getattr(inst, "browser", None)
        return getattr(browser, "web_view", None)
    except Exception:
        return None


def _run_on_ui_thread(fn):
    """Marshal fn onto the WinForms UI thread, retrying briefly while the
    control isn't ready yet — same BrowserView.instances-not-populated-yet
    race _enable_context_menu guards against with its own 5-attempt retry.
    Only falls back to calling fn() directly once those retries are
    exhausted: for _show_tray_icon's _build(), running off the UI thread
    leaves the NotifyIcon's Click/DoubleClick handlers dead, so reaching
    for that fallback immediately (instead of retrying first) defeated the
    whole point most of the time."""
    import time
    for attempt in range(5):
        web_view = _get_ui_control()
        if web_view is not None:
            try:
                if web_view.InvokeRequired:
                    from System.Windows.Forms import MethodInvoker
                    web_view.Invoke(MethodInvoker(fn))
                else:
                    fn()
                return
            except Exception:
                pass
        time.sleep(0.5)
    fn()


def _show_tray_icon():
    """Builds (once) and shows the tray icon behind "Run in background
    (Hotkeys only)" — win_tray() hides the main window right after this
    returns, leaving just this icon in the notification area while
    backend.start_hotkey_listener()'s thread (already running independent
    of the window) keeps firing hotkeys. Has to be built on the WinForms
    UI thread: NotifyIcon dispatches its own Click/DoubleClick events on
    whichever thread created it, so building it from webview.start()'s
    background thread would leave it sitting there dead to every click."""
    def _build():
        global _tray_icon
        if _tray_icon is not None:
            _tray_icon.Visible = True
            return
        from webview.platforms.winforms import BrowserView  # noqa: F401 — CLR assembly load side effect, see _enable_context_menu
        from System.Windows.Forms import NotifyIcon, ContextMenuStrip, ToolStripMenuItem
        from System.Drawing import Icon

        ni = NotifyIcon()
        try:
            icon_path = get_icon_path()
            if os.path.exists(icon_path):
                ni.Icon = Icon(icon_path)
        except Exception:
            pass
        ni.Text = "iTero Toolbox — Hotkeys running"

        menu = ContextMenuStrip()
        open_item = ToolStripMenuItem("Open iTero Toolbox")
        open_item.Click += lambda s, e: _tray_restore()
        exit_item = ToolStripMenuItem("Exit (stops hotkeys)")
        exit_item.Click += lambda s, e: _tray_exit()
        menu.Items.Add(open_item)
        menu.Items.Add(exit_item)
        ni.ContextMenuStrip = menu
        ni.DoubleClick += lambda s, e: _tray_restore()

        ni.Visible = True
        _tray_icon = ni

    _run_on_ui_thread(_build)


def _tray_restore():
    """'Open iTero Toolbox' / double-click on the tray icon — bring the
    window back and drop the tray icon (the usual "minimize to tray"
    convention: the icon only shows while the window is hidden)."""
    global _tray_icon
    try:
        if _window:
            _window.show()
            _window.restore()
    except Exception:
        pass
    try:
        if _tray_icon is not None:
            _tray_icon.Visible = False
    except Exception:
        pass


def _tray_exit():
    """'Exit' on the tray menu — a full quit, hotkeys included. destroy()
    unblocks webview.start() in main(), whose existing post-loop cleanup
    (backend.stop_hotkey_listener(), _dispose_tray_icon(), closing the SF/
    MAT Selenium browsers) already runs no matter which door the app
    leaves through, so nothing extra is needed here."""
    try:
        if _window:
            _window.destroy()
    except Exception:
        pass


def _dispose_tray_icon():
    """Called once webview.start() returns, regardless of which door the
    app left through (custom close button, Alt+F4, or Exit on the tray
    menu) — an undisposed NotifyIcon can leave a ghost icon sitting in the
    tray until the user mouses over it."""
    global _tray_icon
    try:
        if _tray_icon is not None:
            _tray_icon.Visible = False
            _tray_icon.Dispose()
    except Exception:
        pass
    _tray_icon = None


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    html_path = get_html_path()
    if not os.path.exists(html_path):
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "iTero Toolbox",
            f"UI file not found:\n{html_path}\n\n"
            "Make sure itero_toolbox_v1.html is in the same folder."
        )
        sys.exit(1)

    global _window
    api = ToolboxAPI()

    debug_mode = json.loads(backend.get_debug_mode()).get("data", {}).get("debug_mode", False)

    backend.start_hotkey_listener()

    serve_path = _versioned_html_path(html_path)

    # WebView2 initialization is asynchronous and can fail silently — e.g.
    # "resource in use" (0x800700AA) if the previous run's WebView2 process
    # or antivirus/EDR scanning of the freshly-touched profile folder
    # hasn't let go of it yet. Measured on this machine: a failure can take
    # 20-30+ seconds to clear on its own, not just a second or two. A
    # failed init doesn't raise in Python; it just leaves a blank window
    # sitting there forever with webview.start() never returning, which
    # looks exactly like a crash/hang with zero explanation. Detect it via
    # the 'loaded' event never firing, close that dead window, and retry
    # with backoff long enough to actually clear it before giving up.
    import time
    backoff_schedule = [2, 4, 6, 10, 15]  # seconds between attempts
    max_attempts = len(backoff_schedule) + 1
    load_failed = {"flag": False}

    for attempt in range(max_attempts):
        _window = webview.create_window(
            # Every win32 call finds the window by this title — the dev
            # copy needs its own or it would move/lock the exe's window.
            title="iTero Support Toolbox — V1.3.6" + (" [DEV]" if backend.IS_DEV else ""),
            url=Path(serve_path).as_uri(),
            js_api=api,
            width=700,
            height=725,
            min_size=(700, 725),
            resizable=True,
            text_select=False,
            background_color="#0e1117",
        )

        load_failed["flag"] = False

        def _on_start():
            if not _window.events.loaded.wait(8):
                load_failed["flag"] = True
                # window.destroy() is gated behind this same 'loaded' event
                # (pywebview's _loaded_call decorator waits on it for 20s
                # before raising) — since it never fires here, .destroy()
                # would just deadlock too and webview.start() would never
                # return. Close the native window directly instead.
                try:
                    import win32gui, win32con
                    hwnd = win32gui.FindWindow(None, _window.title)
                    if hwnd:
                        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                except Exception:
                    pass
                return
            _strip_caption()

        webview.start(
            func=_on_start,
            gui="edgechromium",
            debug=debug_mode,
            private_mode=False,
            storage_path=os.path.join(os.environ.get("TEMP", "C:\\Temp"),
                                      "itero_toolbox_cache" + backend.DEV_SUFFIX),
        )

        if not load_failed["flag"]:
            break
        if attempt < max_attempts - 1:
            print(f'[MAIN] Browser component busy, retrying ({attempt+1}/{max_attempts})...', flush=True)
            time.sleep(backoff_schedule[attempt])

    backend.stop_hotkey_listener()
    _dispose_tray_icon()

    if load_failed["flag"]:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "iTero Toolbox",
            "Could not start the app's browser component — it's still busy from "
            "a previous run or being scanned by antivirus.\n\n"
            "Wait about a minute and try again."
        )
        sys.exit(1)

    # Quit any Selenium-driven Edge windows (SF, MAT) gracefully instead of
    # leaving them orphaned — an abrupt kill can stop Chromium from flushing
    # the SSO session cookie to disk, forcing a fresh login next launch.
    try:
        backend.sf_close_browser()
    except Exception:
        pass
    try:
        backend.mat_close_browser()
    except Exception:
        pass


if __name__ == "__main__":
    main()
