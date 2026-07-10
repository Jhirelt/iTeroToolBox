"""
iTero Support Toolbox — V1.0
Entry point. Launches PyWebView window loading the HTML frontend.
Must be run as Administrator.

Usage:
    python itero_toolbox.py
    OR double-click itero_toolbox.exe (built with build.bat)
"""

import sys
import os
import ctypes
import json
import threading

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

    def get_network_details(self):
        return backend.get_network_details()

    def disable_ipv6(self):
        return backend.disable_ipv6()

    def flush_dns(self):
        return backend.flush_dns()

    def generate_network_report(self):
        return backend.generate_network_report()

    # ── Battery ─────────────────────────────
    def generate_battery_report(self):
        return backend.generate_battery_report()

    def read_battery_report(self, path):
        return backend.read_battery_report(path)

    def get_battery_events(self):
        return backend.get_battery_events()

    # ── Services ────────────────────────────
    def check_service(self, name):
        return backend.check_service(name)

    def set_service_auto_start(self, name):
        return backend.set_service_auto_start(name)

    # ── Registry ────────────────────────────
    def query_registry(self, key_path):
        return backend.query_registry(key_path)

    def set_registry_value(self, key_path, value_name, value_data, value_type="REG_BINARY"):
        return backend.set_registry_value(key_path, value_name, value_data, value_type)

    def open_regedit(self, key_path=None):
        return backend.open_regedit(key_path)

    # ── Kill iTero ──────────────────────────
    def kill_all_itero(self):
        return backend.kill_all_itero()

    def kill_process(self, process_name):
        return backend.kill_process(process_name)

    # ── Clean install ───────────────────────
    def rename_cadent_folders(self):
        return backend.rename_cadent_folders()

    def clean_registry(self):
        return backend.clean_registry()

    def remove_leftover_files(self):
        return backend.remove_leftover_files()

    # ── Transfer service / folder ───────────
    def verify_export_folder(self):
        return backend.verify_export_folder()

    def share_export_folder(self):
        return backend.share_export_folder()

    def disable_password_sharing(self):
        return backend.disable_password_sharing()

    # ── System tools ────────────────────────
    def open_device_manager(self):
        return backend.open_device_manager()

    def open_event_viewer(self):
        return backend.open_event_viewer()

    def open_services(self):
        return backend.open_services()

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

    def open_woa_collage_folder(self, path):
        return backend.open_woa_collage_folder(path)

    def open_collage_by_b64(self, collage_type, b64_data):
        return backend.open_collage_by_b64(collage_type, b64_data)

    def open_collage_file(self, collage_type):
        return backend.open_collage_file(collage_type)

    def get_catalog_parts(self, model=""):
        return backend.get_catalog_parts(model)

    def fetch_sf_case_title(self, url=""):
        return backend.fetch_sf_case_title(url)

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

    def mat_get_credentials(self):
        return backend.mat_get_credentials()

    def mat_set_enabled(self, enabled):
        return backend.mat_set_enabled(enabled)

    def mat_scrape(self, serial=""):
        return backend.mat_scrape(serial)

    def mat_close_browser(self):
        return backend.mat_close_browser()

    # ── Salesforce (SF) — ticket checker ────
    def sf_open_home(self):
        return backend.sf_open_home()

    def sf_open_ticket(self, ticket_number=""):
        return backend.sf_open_ticket(ticket_number)

    def sf_read_ticket(self):
        return backend.sf_read_ticket()

    def sf_close_browser(self):
        return backend.sf_close_browser()

    def sf_load_settings(self):
        return backend.sf_load_settings()

    def sf_save_settings(self, show_browser=False):
        return backend.sf_save_settings(show_browser)

    # ── KB data (Subject Constructor) ───────
    def get_kb_data(self):
        return backend.get_kb_data()

# ── Utility ─────────────────────────────
    def get_hostname(self):
        import socket
        return json.dumps({"status": "ok", "data": socket.gethostname()})

    def get_os_info(self):
        out, _, _ = backend._run(
            'powershell -NoProfile -Command '
            '"(Get-WmiObject Win32_OperatingSystem).Caption + \' Build \' + '
            '(Get-WmiObject Win32_OperatingSystem).BuildNumber"'
        )
        return json.dumps({"status": "ok", "data": out.strip()})

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
                win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
                topmost = win32con.HWND_TOPMOST if locked else win32con.HWND_NOTOPMOST
                win32gui.SetWindowPos(hwnd, topmost, 0, 0, 0, 0,
                    win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_FRAMECHANGED)
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


# ─────────────────────────────────────────────
# WINDOW CHROME
# ─────────────────────────────────────────────

def _strip_caption():
    """Remove native title bar; keep WS_THICKFRAME for resize. Fix DWM strip."""
    import time
    time.sleep(0.6)
    try:
        import ctypes
        import win32gui, win32con

        hwnd = win32gui.FindWindow(None, _window.title)
        if not hwnd:
            return

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

    backend.start_hotkey_listener()

    _window = webview.create_window(
        title="iTero Support Toolbox — V1.1",
        url=f"file:///{html_path}",
        js_api=api,
        width=700,
        height=725,
        min_size=(700, 725),
        resizable=True,
        text_select=False,
        background_color="#0e1117",
    )

    webview.start(
        func=_strip_caption,
        gui="edgechromium",
        debug=False,
        private_mode=False,
        storage_path=os.path.join(os.environ.get("TEMP", "C:\\Temp"), "itero_toolbox_cache"),
    )

    backend.stop_hotkey_listener()


if __name__ == "__main__":
    main()
