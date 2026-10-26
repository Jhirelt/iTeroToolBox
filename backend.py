"""
iTero Support Toolbox - Backend
All functions run as the current user (app must be launched as Administrator).
"""

import subprocess
import os
import sys
import json
import re
import time
import ctypes
import ctypes.wintypes
import winreg
import socket
import threading
from datetime import datetime, timedelta, time as dt_time
from pathlib import Path


# Running from source (python itero_toolbox.py) rather than the built exe.
# The dev copy has to coexist with the installed exe running at the same
# time, so anything one process locks exclusively — Edge profiles,
# WebView2 cache, global hotkeys, window title lookups — gets its own
# "_dev" variant. Plain JSON settings stay shared on purpose, so dev runs
# with the same configuration.
IS_DEV = not getattr(sys, "frozen", False)
DEV_SUFFIX = "_dev" if IS_DEV else ""


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _run(cmd, shell=True, timeout=30):
    """Run a command, return (stdout, stderr, returncode)."""
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace"
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except Exception as e:
        return "", str(e), 1


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def ok(data=None, msg=""):
    return json.dumps({"status": "ok", "data": data, "msg": msg, "ts": _ts()})


def err(msg):
    return json.dumps({"status": "error", "data": None, "msg": msg, "ts": _ts()})


# ─────────────────────────────────────────────
# HEALTH CHECK
# ─────────────────────────────────────────────

def health_check():
    """Run all health checks and return results dict."""
    results = {}

    # Ping gateway
    try:
        gw_out, _, _ = _run("ipconfig | findstr /i \"Default Gateway\"")
        gw = None
        for line in gw_out.splitlines():
            parts = line.split(":")
            if len(parts) == 2:
                ip = parts[1].strip()
                if ip and ip != "":
                    gw = ip
                    break
        if gw:
            ping_out, _, rc = _run(f"ping -n 2 -w 1000 {gw}")
            if rc == 0:
                match = re.search(r"Average = (\d+)ms", ping_out)
                ms = match.group(1) if match else "OK"
                results["ping"] = {"status": "ok", "val": f"{ms} ms", "detail": gw}
            else:
                results["ping"] = {"status": "error", "val": "No reply", "detail": gw}
        else:
            results["ping"] = {"status": "warn", "val": "No gateway", "detail": ""}
    except Exception as e:
        results["ping"] = {"status": "error", "val": "Error", "detail": str(e)}

    # DNS
    try:
        out, _, rc = _run("ping -n 1 -w 2000 google.com")
        if rc == 0:
            results["dns"] = {"status": "ok", "val": "OK", "detail": "google.com resolved"}
        else:
            results["dns"] = {"status": "error", "val": "Failed", "detail": "Cannot resolve google.com"}
    except Exception as e:
        results["dns"] = {"status": "error", "val": "Error", "detail": str(e)}

    # iTero service
    try:
        out, _, rc = _run("sc query ITeroTransferService")
        if "RUNNING" in out:
            results["svc"] = {"status": "ok", "val": "Running", "detail": "ITeroTransferService"}
        elif "STOPPED" in out:
            results["svc"] = {"status": "warn", "val": "Stopped", "detail": "ITeroTransferService"}
        else:
            results["svc"] = {"status": "warn", "val": "Not found", "detail": "Service missing"}
    except Exception as e:
        results["svc"] = {"status": "warn", "val": "Unknown", "detail": str(e)}

    # IPv6
    try:
        out, _, _ = _run("netsh int ipv6 show global")
        if "disabled" in out.lower():
            results["ipv6"] = {"status": "ok", "val": "Disabled", "detail": "IPv6 off"}
        else:
            results["ipv6"] = {"status": "warn", "val": "Enabled", "detail": "Consider disabling"}
    except Exception as e:
        results["ipv6"] = {"status": "warn", "val": "Unknown", "detail": str(e)}

    # Battery
    try:
        out, _, rc = _run(
            'powershell -NoProfile -Command '
            '"(Get-WmiObject -Class Win32_Battery).EstimatedChargeRemaining"'
        )
        if rc == 0 and out.strip().isdigit():
            pct = int(out.strip())
            status = "ok" if pct > 30 else ("warn" if pct > 15 else "error")
            results["bat"] = {"status": status, "val": f"{pct}%", "detail": "Battery charge"}
        else:
            results["bat"] = {"status": "warn", "val": "N/A", "detail": "No battery / AC only"}
    except Exception as e:
        results["bat"] = {"status": "warn", "val": "Error", "detail": str(e)}

    # Disk — use Python shutil for reliable C: free space
    try:
        import shutil as _shutil
        _total, _used, _free = _shutil.disk_usage("C:\\")
        _val = round(_free / (1024**3), 1)
        _status = "ok" if _val > 10 else ("warn" if _val > 5 else "error")
        results["disk"] = {"status": _status, "val": f"{_val} GB free", "detail": "C: drive"}
    except Exception as e:
        results["disk"] = {"status": "warn", "val": "Error", "detail": str(e)}

    # RAM
    try:
        out, _, _ = _run(
            'powershell -NoProfile -Command '
            '"$os=Get-WmiObject Win32_OperatingSystem; '
            '[Math]::Round(($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/$os.TotalVisibleMemorySize*100)"'
        )
        pct = out.strip()
        try:
            val = int(pct)
            status = "ok" if val < 80 else ("warn" if val < 90 else "error")
            results["ram"] = {"status": status, "val": f"{pct}% used", "detail": "RAM usage"}
        except Exception:
            results["ram"] = {"status": "warn", "val": pct or "?", "detail": "RAM usage"}
    except Exception as e:
        results["ram"] = {"status": "warn", "val": "Error", "detail": str(e)}

    # OS
    try:
        out, _, _ = _run(
            'powershell -NoProfile -Command '
            '"(Get-WmiObject Win32_OperatingSystem).Caption + \' \' + '
            '(Get-WmiObject Win32_OperatingSystem).BuildNumber"'
        )
        results["os2"] = {"status": "ok", "val": out.strip() or "Windows", "detail": "OS version"}
    except Exception as e:
        results["os2"] = {"status": "ok", "val": "Windows", "detail": str(e)}

    return json.dumps({"status": "ok", "data": results, "ts": _ts()})


# ─────────────────────────────────────────────
# NETWORKING
# ─────────────────────────────────────────────

def run_ipconfig():
    out, stderr, rc = _run("ipconfig /all", timeout=15)
    if rc == 0:
        # Chunk output — pywebview has a JS string size limit
        return ok(out[:8000] if len(out) > 8000 else out)
    return err(stderr)


def run_ping(target="8.8.8.8"):
    # Run as an argv list (shell=False) rather than interpolating target into
    # a shell string — target is exposed straight through to this API from
    # the webview's JS context, and shell=True would let a value like
    # "8.8.8.8 & calc.exe" execute as a second command.
    out, stderr, rc = _run(["ping", "-n", "4", target], shell=False)
    return ok(out) if rc == 0 else err(out or stderr)


def get_wifi_details():
    out, stderr, rc = _run("netsh wlan show interfaces")
    return ok(out) if rc == 0 else err(stderr)


def generate_network_report():
    """Generate netsh network report and return path."""
    path = r"C:\Users\Public\network-report.html"
    out, stderr, rc = _run(f'netsh wlan show wlanreport output-file="{path}"')
    if os.path.exists(path):
        return ok({"path": path, "output": out})
    # fallback: netsh trace
    return ok({"path": "", "output": out or stderr})


# ─────────────────────────────────────────────
# BATTERY
# ─────────────────────────────────────────────

def generate_battery_report():
    path = r"C:\Users\iTero\Documents\battery-report.html"
    out, stderr, rc = _run(
        f'powercfg /batteryreport /duration 14 /output "{path}"'
    )
    if os.path.exists(path):
        return ok({"path": path, "output": out})
    # Try public path as fallback
    path2 = r"C:\Users\Public\battery-report.html"
    out2, _, _ = _run(f'powercfg /batteryreport /duration 14 /output "{path2}"')
    if os.path.exists(path2):
        return ok({"path": path2, "output": out2})
    return err(f"Report not found. {stderr}")


def read_battery_report(path):
    """Read battery report HTML and extract design/full capacity."""
    try:
        if not os.path.exists(path):
            return err("File not found")
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            html = f.read()
        design = re.search(r"DESIGN CAPACITY.*?(\d[\d,]+)\s*mWh", html, re.IGNORECASE)
        full = re.search(r"FULL CHARGE CAPACITY.*?(\d[\d,]+)\s*mWh", html, re.IGNORECASE)
        cycle = re.search(r"CYCLE COUNT.*?(\d+)", html, re.IGNORECASE)
        d_cap = design.group(1).replace(",", "") if design else None
        f_cap = full.group(1).replace(",", "") if full else None
        cycles = cycle.group(1) if cycle else None
        health = None
        if d_cap and f_cap:
            try:
                health = round(int(f_cap) / int(d_cap) * 100, 1)
            except Exception:
                pass
        return ok({
            "design_capacity": d_cap,
            "full_capacity": f_cap,
            "cycle_count": cycles,
            "health_pct": health,
            "path": path
        })
    except Exception as e:
        return err(str(e))


def get_battery_events():
    cmd = (
        'powershell -NoProfile -Command '
        '"Get-WinEvent -FilterHashtable @{LogName=\'System\'; Id=41,12,105} '
        '-MaxEvents 15 -ErrorAction SilentlyContinue | '
        'Select-Object TimeCreated,Id,Message | ConvertTo-Json"'
    )
    out, stderr, rc = _run(cmd, timeout=20)
    return ok(out) if out else err(stderr or "No events found")


# ─────────────────────────────────────────────
# REGISTRY
# ─────────────────────────────────────────────

def open_regedit(key_path=None):
    """Open regedit, optionally pre-navigated to a key."""
    if key_path:
        try:
            reg_key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Applets\Regedit"
            )
            winreg.SetValueEx(reg_key, "LastKey", 0, winreg.REG_SZ, key_path)
            winreg.CloseKey(reg_key)
        except Exception:
            pass
    subprocess.Popen(["regedit.exe"])
    return ok("Registry Editor opened")


# ─────────────────────────────────────────────
# KILL iTERO
# ─────────────────────────────────────────────

ITERO_PROCESSES = [
    "Cadent.iTero.Shell.iTeroScannerShell.exe",
    "Cadent.iTero.iTeroDesktopApplication.exe",
    "Cadent.iTero.UI.Application.exe",
    "RxManager.WinFormHostApp.exe",
    "RxManager.TrayIconApplication.exe",
    "Aligntech.RTH.MatServerInterface.exe",
    "CaseAdmin.exe",
    "Cadent.CaseAdmin.Application.exe",
    "loguploader.exe",
    "HwDiagnosticsApplicationUI.exe",
    "RunHwDiagnosticsApplication.exe",
    "Cadent.Utilities.KeyMonitor.exe",
    "Cadent.Infra.Legacy.minidump.exe",
    "Cadent.Shared.Util.Watchdog.exe",
    "EnableKbFilter.exe",
    "Align.Utilities.UserActivityDetection.exe",
    "Cadent.Shared.Util.DrawingToolWeb.exe",
    "Cadent.iTero.UI.SplashScreen.exe",
    "Align.iTero.Packaging.Util.Packager.exe",
    "RxManager.WpfHostApp.exe",
    "CefSharp.BrowserSubprocess.exe",
    "ITeroTransferService.exe",
    "InstallationApp.exe",
    "OutcomeSimulator.exe",
    "JarvisClient.exe",
    "DotNetRuntimeSetup.exe",
    "Angie.BG.Application.exe",
    "angie.tools.minidump_service.exe",
    "Scanapp.UI.Application.exe",
    "Cadent.Utilities.AngieBackgroundMock.exe",
    "Cadent.Utilities.AngieMock.exe",
    "Cadent.Utilities.SystemSnapshot.exe",
    "IAStorIcon.exe",
    "RAVCpl64.exe",
    "MageSystemMetricsService.exe",
]

def kill_all_itero():
    """Kill all iTero/Cadent processes and stop services."""
    killed = []
    failed = []
    for proc in ITERO_PROCESSES:
        out, _, rc = _run(f'taskkill /F /IM "{proc}"')
        if "SUCCESS" in out or rc == 0:
            killed.append(proc)
        else:
            failed.append(proc)
    # Stop services
    _run("sc stop winlogbeat")
    _run("sc stop filebeat")
    _run("sc stop MageSystemMetricsService")
    # PowerShell fallback for anything Cadent-pathed
    _run(
        'powershell -NoProfile -Command '
        '"Get-Process | ForEach-Object { try { if($_.Path -like \'*Cadent*\')'
        '{ Stop-Process -Id $_.Id -Force } } catch {} }"'
    )
    return ok({
        "killed": killed,
        "not_found": failed,
        "msg": f"Terminated {len(killed)} processes"
    })


# ─────────────────────────────────────────────
# SYSTEM TOOLS
# ─────────────────────────────────────────────

def open_device_manager():
    subprocess.Popen(["devmgmt.msc"], shell=True)
    return ok("Device Manager opened")


def open_event_viewer():
    subprocess.Popen(["eventvwr.msc"], shell=True)
    return ok("Event Viewer opened")


def open_log_collector(output_path=r"C:\Temp\Logs"):
    exe = r"C:\Program Files\Cadent\LogCollector\log_collector.exe"
    if not os.path.exists(exe):
        return err(f"Log collector not found: {exe}")
    subprocess.Popen([exe, output_path, "5", "0"])
    return ok(f"Log Collector launched → {output_path}")


def launch_slfdd_driver():
    inf = r"C:\Program Files\Cadent\SLFDD\Driver Installer\cyusb3.inf"
    if not os.path.exists(inf):
        return err(f"Driver not found: {inf}")
    out, stderr, rc = _run(f'pnputil /add-driver "{inf}" /install')
    return ok(out) if rc == 0 else err(stderr or out)


def launch_slfdd_utility():
    exe = r"C:\Program Files\Cadent\SLFDD\Utility\SlfddCSharp.exe"
    if not os.path.exists(exe):
        return err(f"SLFDD utility not found: {exe}")
    subprocess.Popen([exe])
    return ok("SLFDD utility launched")


def open_url_in_browser(url):
    import webbrowser
    webbrowser.open(url)
    return ok(f"Opened: {url}")


def open_html_file(path):
    if not os.path.exists(path):
        return err(f"File not found: {path}")
    import webbrowser
    webbrowser.open(f"file:///{path}")
    return ok(f"Opened: {path}")


def get_filter_events(event_ids="41,12,105", max_events=15):
    cmd = (
        f'powershell -NoProfile -Command '
        f'"Get-WinEvent -FilterHashtable @{{LogName=\'System\'; '
        f'Id={event_ids}}} -MaxEvents {max_events} -ErrorAction SilentlyContinue | '
        f'Select-Object TimeCreated,Id,LevelDisplayName,Message | '
        f'Format-List"'
    )
    out, stderr, rc = _run(cmd, timeout=20)
    return ok(out) if out else err(stderr or "No matching events found")


def run_arbitrary_cmd(cmd):
    """Execute any command and return output. App must run as admin."""
    out, stderr, rc = _run(cmd, timeout=60)
    combined = out + ("\n" + stderr if stderr else "")
    return json.dumps({
        "status": "ok" if rc == 0 else "error",
        "data": combined,
        "rc": rc,
        "ts": _ts()
    })


def open_woa_collage(agent_email=""):
    """Save WOA reference collage to known path and open File Explorer there."""
    import shutil, sys

    try:
        if getattr(sys, 'frozen', False):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).parent

        src = base / "Reference" / "WOA" / "wand_reference_WOA.png"
        dest_dir = Path(r"C:\iTeroToolbox\Reference\WOA")
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "wand_reference_WOA.png"

        if not src.exists():
            alt = Path(__file__).parent / "Reference" / "WOA" / "wand_reference_WOA.png"
            if alt.exists():
                src = alt

        if src.exists():
            shutil.copy2(str(src), str(dest))

        if not dest.exists():
            return err(f"Collage not found. Place wand_reference_WOA.png in {dest_dir}")

        if agent_email:
            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.open(str(dest))
                draw = ImageDraw.Draw(img)
                try:
                    font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 18)
                except Exception:
                    font = ImageFont.load_default()
                text = f"Sent by: {agent_email}"
                draw.rectangle([8, img.height-34, 520, img.height-4], fill=(20,22,30))
                draw.text((12, img.height-30), text, fill=(100,200,255), font=font)
                img.save(str(dest))
            except Exception:
                pass

        subprocess.Popen(f'explorer /select,"{dest}"', shell=True)
        return ok({"path": str(dest), "msg": f"File Explorer opened → {dest}"})
    except Exception as e:
        return err(str(e))


def generate_link_unlink_excel(data):
    """Generate compact Link/Unlink Excel — MAT, Unlink, Link only."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
        from openpyxl.utils import get_column_letter
        from datetime import datetime

        mat    = data.get('mat', '')
        unlink = data.get('unlink', '')
        link   = data.get('link', '')
        agent  = data.get('agent', '') or 'Agent'
        date_s = datetime.now().strftime('%Y-%m-%d')
        ts     = datetime.now().strftime('%Y%m%d_%H%M%S')

        dest_dir = Path(r'C:\iTeroToolbox\LinkUnlink')
        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = f'LinkUnlink_{ts}.xlsx'
        dest  = dest_dir / fname

        wb = Workbook()
        ws = wb.active
        ws.title = 'Link-Unlink'

        thin   = Side(style='thin', color='CCCCCC')
        border = Border(left=thin, right=thin, top=thin, bottom=thin)
        center = Alignment(horizontal='center', vertical='center')
        left   = Alignment(horizontal='left',   vertical='center')

        # Title
        ws.merge_cells('A1:C1')
        ws['A1'].value     = f'iTero Link/Unlink Request — {agent} — {date_s}'
        ws['A1'].font      = Font(name='Arial', bold=True, size=12, color='1F3A6E')
        ws['A1'].alignment = center

        # Headers
        headers = ['MAT Person', 'SFDC Contact ID', 'Action']
        hdr_font = Font(name='Arial', bold=True, color='FFFFFF', size=11)
        hdr_fill = PatternFill('solid', start_color='1F3A6E')
        for col, h in enumerate(headers, 1):
            c = ws.cell(row=3, column=col, value=h)
            c.font = hdr_font; c.fill = hdr_fill
            c.alignment = center; c.border = border

        # Unlink row
        unlink_fill = PatternFill('solid', start_color='FFDCDC')
        for col, val in enumerate([mat, unlink, 'Unlink'], 1):
            c = ws.cell(row=4, column=col, value=val)
            c.fill = unlink_fill; c.border = border; c.alignment = left
            c.font = Font(name='Arial', bold=(col==3), color='C0392B' if col==3 else '000000', size=11)

        # Link row
        link_fill = PatternFill('solid', start_color='DCFFE4')
        for col, val in enumerate([mat, link, 'Link'], 1):
            c = ws.cell(row=5, column=col, value=val)
            c.fill = link_fill; c.border = border; c.alignment = left
            c.font = Font(name='Arial', bold=(col==3), color='1E7E34' if col==3 else '000000', size=11)

        # Column widths
        for i, w in enumerate([20, 24, 14], 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.row_dimensions[1].height = 24
        ws.row_dimensions[3].height = 20

        wb.save(str(dest))
        subprocess.Popen(f'explorer /select,"{dest}"', shell=True)
        return ok({'path': str(dest), 'filename': fname})

    except Exception as e:
        return err(f'Failed to generate Excel: {e}')


def esc_report_export(entries, agent_name=""):
    """Export the Escalations Report log using report.py's format: a single
    'Summary' sheet with Key Figures, Closed Tickets, Breakdown by Category,
    Case Handlers/Origin/Validity, and (when there are any) an Open Tickets
    section — all computed from `entries`, nothing written by hand.
    """
    try:
        from report import make_report
        from datetime import datetime

        entries = entries or []
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        dest_dir = Path(r'C:\iTeroToolbox\EscalationReports')
        dest_dir.mkdir(parents=True, exist_ok=True)
        fname = f'EscReport_{ts}.xlsx'
        dest  = dest_dir / fname

        # Open tickets aren't resolved yet — Key Figures/Closed Tickets/
        # Breakdown/Handlers below are all about what's ALREADY closed in
        # the period, so only actually-closed entries feed them. Missing
        # 'status' (entries saved before Open Tickets existed) defaults to
        # closed, same as the frontend does.
        closed_entries = [e for e in entries if (e.get('status') or 'closed') != 'open']
        open_entries   = [e for e in entries if (e.get('status') or 'closed') == 'open']

        tickets = [{
            'ticket':      e.get('ticket', ''),
            'model':       e.get('model', ''),
            'ticket_type': e.get('ticketType', ''),
            'issue_type':  e.get('issueType', ''),
            'sub_issue':   e.get('subIssueType', ''),
            'outcome':     e.get('solution', ''),
            'csat':        e.get('csat', ''),
            'resolution_hours': e.get('resolutionHours') or 0,
        } for e in closed_entries]

        handlers = [{
            'ticket':   e.get('ticket', ''),
            'handler':  e.get('previousHandler', ''),
            # The UI's Validity control is a Valid/Avoidable toggle that
            # always displays "Avoidable" for an untouched ticket — the
            # export has to agree, or an untouched ticket would silently
            # drop out of both KPI counts instead of counting as Avoidable.
            'validity': e.get('validity') or 'Avoidable',
            'origin':   e.get('origin', ''),
        } for e in closed_entries]

        open_tickets = [{
            'ticket':      e.get('ticket', ''),
            'model':       e.get('model', ''),
            'ticket_type': e.get('ticketType', ''),
            'issue_type':  e.get('issueType', ''),
            'sub_issue':   e.get('subIssueType', ''),
            'comment':     e.get('comment', ''),
            'handler':     e.get('previousHandler', ''),
            'validity':    e.get('validity') or 'Avoidable',
            'origin':      e.get('origin', ''),
        } for e in open_entries]

        # Excel-only fields (never shown in the app) — every logged ticket,
        # open or closed, in the same order as the sections above.
        details = [{
            'ticket':             e.get('ticket', ''),
            'status':             'Open' if (e.get('status') or 'closed') == 'open' else 'Closed',
            'priority':           e.get('priority', ''),
            'internal_requestor': e.get('internalRequestor', ''),
            'date_opened':        _parse_sf_datetime(e.get('dateOpened')) or e.get('dateOpened', ''),
            'date_closed':        _parse_sf_datetime(e.get('dateClosed')) or e.get('dateClosed', ''),
            'days_open':          e.get('daysOpen', ''),
        } for e in closed_entries + open_entries]

        month_year = datetime.now().strftime('%B %Y')
        n = len(closed_entries)
        period = f'{month_year}  -  {n} closed escalation{"s" if n != 1 else ""}'
        title = '  |  '.join(p for p in ['CSC Escalations', month_year, agent_name] if p)

        make_report(tickets, handlers, period=period, title=title, out=str(dest),
                    open_tickets=open_tickets, details=details)
        subprocess.Popen(f'explorer /select,"{dest}"', shell=True)
        return ok({'path': str(dest), 'filename': fname})

    except Exception as e:
        return err(f'Failed to generate report: {e}')


def open_woa_collage_folder(path):
    """Open File Explorer selecting the given file path."""
    try:
        if os.path.exists(path):
            subprocess.Popen(f'explorer /select,"{path}"', shell=True)
        else:
            folder = str(Path(path).parent)
            subprocess.Popen(f'explorer "{folder}"', shell=True)
        return ok(f'Explorer opened: {path}')
    except Exception as e:
        return err(str(e))


def open_collage_by_b64(collage_type, b64_data):
    """Save a base64 collage image to disk and open in Explorer."""
    import base64, shutil
    try:
        # Strip data URI prefix if present
        if ',' in b64_data:
            b64_data = b64_data.split(',', 1)[1]
        img_bytes = base64.b64decode(b64_data)
        dest_dir = Path(r'C:\iTeroToolbox\LinkUnlink')
        dest_dir.mkdir(parents=True, exist_ok=True)
        names = {
            'yucblx': 'wand_reference_YUC_BLX.png',
            'lumina': 'wand_reference_LUMINA.png',
            'woa':    'wand_reference_WOA.png',
        }
        fname = names.get(collage_type, f'wand_reference_{collage_type}.png')
        dest = dest_dir / fname
        with open(str(dest), 'wb') as f:
            f.write(img_bytes)
        subprocess.Popen(f'explorer /select,"{dest}"', shell=True)
        return ok({'path': str(dest), 'msg': f'Explorer opened → {dest}'})
    except Exception as e:
        return err(str(e))


def open_collage_file(collage_type):
    """Open a pre-saved collage PNG from Reference\\subfolder in Explorer."""
    import sys
    config = {
        'yucblx': (r'C:\iTeroToolbox\Reference\YUC_BLX', 'YUC_BLX', 'wand_reference_YUC_BLX.png'),
        'lumina':  (r'C:\iTeroToolbox\Reference\Lumina',  'Lumina',  'wand_reference_LUMINA.png'),
        'woa':     (r'C:\iTeroToolbox\Reference\WOA',     'WOA',     'wand_reference_WOA.png'),
    }
    if collage_type not in config:
        return err(f'Unknown collage type: {collage_type}')
    folder, subdir, fname = config[collage_type]
    dest = Path(folder) / fname
    try:
        # If not already in the persistent Reference subfolder, copy it there
        # from the bundled copy (sys._MEIPASS when frozen, else the source
        # tree next to this file) so it's easy to find/attach next time too.
        if not dest.exists():
            if getattr(sys, 'frozen', False):
                base = Path(sys._MEIPASS)
            else:
                base = Path(__file__).parent
            alt = base / "Reference" / subdir / fname
            if alt.exists():
                import shutil
                Path(folder).mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(alt), str(dest))
            else:
                return err(f'Collage not found: {fname}. Place PNG in {folder}\\')
        subprocess.Popen(f'explorer /select,"{dest}"', shell=True)
        return ok({'path': str(dest), 'msg': f'Explorer opened -> {dest}'})
    except Exception as e:
        return err(str(e))


def get_catalog_parts(model=""):
    """Return list of parts from the bundled Catalog/ folder as base64-encoded images."""
    import base64
    import sys
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    catalog_dir = base / "Catalog"
    if not catalog_dir.exists():
        return err(f"Catalog folder not found: {catalog_dir}")

    image_exts = {".jpg", ".jpeg", ".png", ".webp"}
    parts = []
    for f in sorted(catalog_dir.iterdir()):
        if f.suffix.lower() not in image_exts:
            continue
        stem = f.stem  # e.g. "Element Wand- 108540"
        # Parse "Part Name- CODE" or "Part Name - CODE" or just use full stem
        m = re.match(r'^(.+?)\s*[-–]\s*(\d+)\s*$', stem)
        if m:
            part_name = m.group(1).strip()
            part_code = m.group(2).strip()
        else:
            part_name = stem
            part_code = ""
        try:
            b64 = base64.b64encode(f.read_bytes()).decode("utf-8")
            parts.append({
                "part_name": part_name,
                "part_code": part_code,
                "filename": f.name,
                "path": str(f),
                "b64": b64,
                "error": False
            })
        except Exception as e:
            parts.append({
                "part_name": part_name,
                "part_code": part_code,
                "filename": f.name,
                "path": str(f),
                "b64": "",
                "error": True
            })

    return ok(parts)


# ─────────────────────────────────────────────
# USER PROFILE
# ─────────────────────────────────────────────

_PROFILE_PATH = os.path.join(os.path.expandvars('%APPDATA%'), 'iTeroToolBox', 'profile.json')

def get_user_profile():
    try:
        if os.path.exists(_PROFILE_PATH):
            with open(_PROFILE_PATH, 'r') as f:
                return ok(json.load(f))
        return ok(None)
    except Exception as e:
        return err(str(e))

def save_user_profile(name="", role=""):
    try:
        os.makedirs(os.path.dirname(_PROFILE_PATH), exist_ok=True)
        data = {"name": name, "role": role}
        with open(_PROFILE_PATH, 'w') as f:
            json.dump(data, f)
        return ok(data)
    except Exception as e:
        return err(str(e))

def clear_user_profile():
    try:
        if os.path.exists(_PROFILE_PATH):
            os.remove(_PROFILE_PATH)
        return ok(True)
    except Exception as e:
        return err(str(e))


# ─────────────────────────────────────────────
# KB DATA (Subject Constructor — KB suggestions)
# ─────────────────────────────────────────────

_KB_DATA_CACHE = None

def get_kb_data():
    """Load data/kb_data.json once and cache it. Matching itself happens in JS."""
    global _KB_DATA_CACHE
    if _KB_DATA_CACHE is not None:
        return ok(_KB_DATA_CACHE)
    try:
        if getattr(sys, 'frozen', False):
            base = Path(sys._MEIPASS)
        else:
            base = Path(__file__).parent
        kb_path = base / "data" / "kb_data.json"
        with open(kb_path, 'r', encoding='utf-8') as f:
            _KB_DATA_CACHE = json.load(f)
        return ok(_KB_DATA_CACHE)
    except Exception as e:
        return err(str(e))


# ─────────────────────────────────────────────
# HOTKEYS  (global keyboard shortcuts via Win32 RegisterHotKey)
# ─────────────────────────────────────────────

_HK_PATH = os.path.join(os.path.expandvars('%APPDATA%'), 'iTeroToolBox', 'hotkeys.json')

_VK_MAP = {
    'F1':0x70,'F2':0x71,'F3':0x72,'F4':0x73,'F5':0x74,'F6':0x75,
    'F7':0x76,'F8':0x77,'F9':0x78,'F10':0x79,'F11':0x7A,'F12':0x7B,
    'F13':0x7C,'F14':0x7D,'F15':0x7E,'F16':0x7F,'F17':0x80,'F18':0x81,
    'F19':0x82,'F20':0x83,'F21':0x84,'F22':0x85,'F23':0x86,'F24':0x87,
    'A':0x41,'B':0x42,'C':0x43,'D':0x44,'E':0x45,'F':0x46,'G':0x47,
    'H':0x48,'I':0x49,'J':0x4A,'K':0x4B,'L':0x4C,'M':0x4D,'N':0x4E,
    'O':0x4F,'P':0x50,'Q':0x51,'R':0x52,'S':0x53,'T':0x54,'U':0x55,
    'V':0x56,'W':0x57,'X':0x58,'Y':0x59,'Z':0x5A,
    '0':0x30,'1':0x31,'2':0x32,'3':0x33,'4':0x34,
    '5':0x35,'6':0x36,'7':0x37,'8':0x38,'9':0x39,
}
_MOD_MAP      = {'ctrl': 0x0002, 'alt': 0x0001, 'shift': 0x0004}
_MOD_NOREPEAT = 0x4000
_WM_HOTKEY    = 0x0312
_INPUT_KBD    = 1
_KF_UNICODE   = 0x0004
_KF_KEYUP     = 0x0002
_VK_RETURN    = 0x0D
_VK_SHIFT     = 0x10
_VK_CONTROL   = 0x11
_VK_MENU      = 0x12  # Alt

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ('wVk',         ctypes.c_ushort),
        ('wScan',       ctypes.c_ushort),
        ('dwFlags',     ctypes.c_uint),
        ('time',        ctypes.c_uint),
        ('dwExtraInfo', ctypes.c_size_t),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [('ki', _KEYBDINPUT), ('_pad', ctypes.c_byte * 32)]

class _INPUT(ctypes.Structure):
    _fields_ = [('type', ctypes.c_uint), ('_', _INPUT_UNION)]

class _MSG(ctypes.Structure):
    _fields_ = [
        ('hwnd',    ctypes.c_size_t),
        ('message', ctypes.c_uint),
        ('wParam',  ctypes.c_size_t),
        ('lParam',  ctypes.c_ssize_t),
        ('time',    ctypes.c_uint),
        ('ptX',     ctypes.c_long),
        ('ptY',     ctypes.c_long),
    ]

def _ahk_paths():
    """Resolve the bundled AutoHotkey interpreter + typing script — works
    both in dev (Vendor/ next to this file) and as the frozen exe
    (sys._MEIPASS when frozen), same pattern used for Reference/Catalog/
    data elsewhere in this file."""
    base = Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).parent
    return base / "Vendor" / "AutoHotkey64.exe", base / "Vendor" / "type_text.ahk"


def _type_text_ahk(text):
    """Type text by shelling out to the bundled real AutoHotkey interpreter
    (Vendor/AutoHotkey64.exe running Vendor/type_text.ahk) instead of our
    own hand-rolled SendInput calls.

    Why: hand-rolled SendInput — even switched to real VK-code keystrokes,
    even with delays and modifier-holding added — kept typing unreliably
    once a TeamViewer remote-control session was in the loop (spaces
    dropped, then irregular duplicated/missing letters). AutoHotkey's own
    Send engine is built on the same underlying Win32 API but has ~20
    years of refinement against exactly this class of problem, and was
    directly confirmed reliable in this environment. Delegating to the
    real thing beats re-deriving whatever subtlety it gets right that our
    reimplementation doesn't.

    The text is written to a temp file and the (fixed, never-templated)
    .ahk script reads it from there — no user text ever gets embedded
    into AHK script source, so there's no escaping/injection surface at
    all for quotes, backticks, or anything else a hotkey's text might
    contain.

    Returns True on success, False if AutoHotkey isn't available (e.g. a
    dev checkout missing Vendor/, or something failed) — the caller falls
    back to the ctypes-based implementation below when this is False.
    """
    try:
        ahk_exe, ahk_script = _ahk_paths()
        if not ahk_exe.exists() or not ahk_script.exists():
            return False
        tmp_dir = Path(os.environ.get('TEMP', 'C:\\Temp')) / 'iTeroToolBox'
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = tmp_dir / f'hk_text_{os.getpid()}_{int(time.time() * 1000)}.txt'
        try:
            tmp_path.write_text(text, encoding='utf-8', newline='')
            result = subprocess.run([str(ahk_exe), str(ahk_script), str(tmp_path)],
                                     capture_output=True, timeout=15)
            return result.returncode == 0
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        print(f'[HK] AHK typing failed, falling back to SendInput: {e}', flush=True)
        return False


def _type_text(text, multiline=True):
    """Type text — via the bundled real AutoHotkey interpreter when it's
    available (see _type_text_ahk, the reliable path confirmed to survive
    a TeamViewer remote session), falling back to a hand-rolled SendInput
    implementation of our own otherwise.

    The SendInput fallback below: one character at a time with a short
    delay between each keystroke, preferring a REAL virtual-key keystroke
    over raw Unicode injection whenever the current keyboard layout can
    produce the character.

    Used to send every character (space included) via KEYEVENTF_UNICODE —
    wVk=0, the character rides in wScan, Windows synthesizes it as
    VK_PACKET. That's a comparatively exotic delivery path: plenty of
    local software handles it fine, but a remote-control tool's own
    keyboard hook (TeamViewer's, controlling a customer's machine) can
    mishandle it once it's forwarding those events into a remote session
    — observed specifically dropping every space and gluing words
    together, while ordinary letters mostly survived. Adding a delay
    between characters alone didn't fix it, which rules out a rate/
    coalescing problem and points at VK_PACKET delivery itself being the
    weak link.

    VkKeyScanW(ch) asks the active layout "what real key (+ Shift/Ctrl/
    Alt) produces this character?" — for every plain ASCII letter, digit,
    punctuation mark and space, the answer is a normal VK code, so it can
    be sent as an ordinary keystroke: exactly the kind of event every
    application (including a remote-control tool's input hook) already
    expects and handles correctly. Only characters the layout genuinely
    can't produce (accented letters outside it, non-Latin scripts, emoji,
    ...) fall back to the old Unicode-injection path.
    """
    if not multiline:
        text = text.replace('\r', '').replace('\n', ' ')

    if _type_text_ahk(text):
        return len(text)

    user32 = ctypes.windll.user32
    user32.VkKeyScanW.restype = ctypes.c_short
    user32.VkKeyScanW.argtypes = [ctypes.c_wchar]

    def _key(vk, keyup=False):
        flags = _KF_KEYUP if keyup else 0
        return _INPUT(type=_INPUT_KBD, _=_INPUT_UNION(
            ki=_KEYBDINPUT(wVk=vk, wScan=0, dwFlags=flags, time=0, dwExtraInfo=0)))

    def _send(pair):
        arr = (_INPUT * len(pair))(*pair)
        n = user32.SendInput(len(pair), arr, ctypes.sizeof(_INPUT))
        time.sleep(0.03)
        return n

    sent_total = 0
    # Modifiers are held across a whole run of same-case/shifted characters
    # (like a human typist holding Shift through a capitalized word)
    # instead of tapping them per character — a real capital-letter run
    # used to press+release Shift around every single letter, several
    # events each; over a genuinely latency-bearing network hop (TeamViewer
    # controlling a customer's machine, not a purely local keyboard) that
    # much modifier traffic landing out of order is exactly the kind of
    # thing that produces irregular results — sometimes fine, sometimes a
    # duplicated or dropped letter, sometimes a whole word wrong — rather
    # than a clean, repeatable failure. Fewer modifier transitions overall,
    # plus a longer per-character delay (30ms, up from 12ms) to give the
    # remote side real breathing room, both cut down that risk.
    held_mods = set()

    for ch in text:
        if ch == '\r':
            continue

        if ch == '\n':
            if held_mods:
                sent_total += _send([_key(m, keyup=True) for m in held_mods])
                held_mods.clear()
            sent_total += _send([_key(_VK_RETURN), _key(_VK_RETURN, keyup=True)])
            continue

        code = ord(ch)
        if code > 0xFFFF:
            continue
        vkscan = user32.VkKeyScanW(ch)
        if vkscan != -1:
            vk = vkscan & 0xFF
            shift_state = (vkscan >> 8) & 0xFF
            needed = set(m for bit, m in ((0x1, _VK_SHIFT), (0x2, _VK_CONTROL), (0x4, _VK_MENU))
                         if shift_state & bit)
            to_release = held_mods - needed
            to_press   = needed - held_mods
            pair = [_key(m, keyup=True) for m in to_release] + [_key(m) for m in to_press]
            held_mods = needed
            pair += [_key(vk), _key(vk, keyup=True)]
        else:
            # Not reachable from the active layout — fall back to raw
            # Unicode injection, same as before. Release any held
            # modifiers first; they have nothing to do with this path.
            if held_mods:
                sent_total += _send([_key(m, keyup=True) for m in held_mods])
                held_mods.clear()
            pair = [
                _INPUT(type=_INPUT_KBD, _=_INPUT_UNION(
                    ki=_KEYBDINPUT(wVk=0, wScan=code, dwFlags=_KF_UNICODE, time=0, dwExtraInfo=0))),
                _INPUT(type=_INPUT_KBD, _=_INPUT_UNION(
                    ki=_KEYBDINPUT(wVk=0, wScan=code, dwFlags=_KF_UNICODE | _KF_KEYUP, time=0, dwExtraInfo=0))),
            ]

        sent_total += _send(pair)

    if held_mods:
        sent_total += _send([_key(m, keyup=True) for m in held_mods])

    return sent_total

_hk_thread_ref = None
_hk_stop_evt   = threading.Event()
_hk_status     = {'registered': 0, 'failed': [], 'fired': 0, 'thread_alive': False, 'crash': ''}

def _hk_thread_func(hotkeys):
    global _hk_status
    # The whole body used to run with no top-level exception handling — if
    # anything unexpected threw here (e.g. a restricted/AV-locked-down PC
    # blocking these Win32 calls), the daemon thread just died silently and
    # _hk_status was stuck at its all-zero default forever, with no way to
    # tell "nothing configured" apart from "listener crashed on startup".
    # Now any such crash is captured and surfaced in get_hotkey_status().
    try:
        user32   = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        # Force creation of this thread's Win32 message queue BEFORE RegisterHotKey.
        # Without this, RegisterHotKey may succeed but WM_HOTKEY is never delivered.
        _init_msg = _MSG()
        user32.PeekMessageW(ctypes.byref(_init_msg), None, 0, 0, 0)  # PM_NOREMOVE

        tid = kernel32.GetCurrentThreadId()
        print(f'[HK] Thread started (tid={tid})', flush=True)

        registered = []
        hk_map   = {}
        failed   = []
        reg_id   = 1

        for hk in hotkeys:
            if not hk.get('enabled', True):
                continue
            vk = _VK_MAP.get((hk.get('key') or '').upper())
            if not vk:
                continue
            mods = _MOD_NOREPEAT
            for m in (hk.get('mods') or []):
                mods |= _MOD_MAP.get(m, 0)
            label = hk.get('label') or hk.get('key', '?')
            # Retry up to 5 times — Win32 may still hold the handle briefly after
            # the previous thread's UnregisterHotKey if the thread restart is fast.
            ok_reg = False
            for attempt in range(5):
                ok_reg = user32.RegisterHotKey(None, reg_id, mods, vk)
                if ok_reg:
                    break
                err_code = kernel32.GetLastError()
                if err_code == 1409 and attempt < 4:  # ERROR_HOTKEY_ALREADY_REGISTERED
                    print(f'[HK] retry {attempt+1} for {label} (err=1409)…', flush=True)
                    time.sleep(0.1)
                else:
                    break
            if ok_reg:
                registered.append(reg_id)
                hk_map[reg_id] = hk
                reg_id += 1
                print(f'[HK] OK registered: {label} (win_id={reg_id-1})', flush=True)
            else:
                err_code = kernel32.GetLastError()
                entry = f'{label} (err={err_code})'
                failed.append(entry)
                print(f'[HK] FAILED register: {entry}', flush=True)

        _hk_status = {'registered': len(registered), 'failed': failed, 'fired': 0, 'thread_alive': True, 'crash': ''}
        print(f'[HK] Thread alive — {len(registered)} registered, {len(failed)} failed', flush=True)

        msg = _MSG()
        while not _hk_stop_evt.is_set():
            if user32.PeekMessageW(ctypes.byref(msg), None, _WM_HOTKEY, _WM_HOTKEY, 1):
                if msg.message == _WM_HOTKEY:
                    hk = hk_map.get(msg.wParam)
                    print(f'[HK] WM_HOTKEY fired: wParam={msg.wParam} → {hk.get("label") if hk else "unknown"}', flush=True)
                    if hk:
                        _hk_status['fired'] += 1
                        try:
                            time.sleep(0.08)
                            if hk.get('source') == 'cmd' and hk.get('cmd'):
                                # CMD-snippet hotkeys used to run the command silently via
                                # subprocess with output discarded — nothing was ever visible,
                                # so it looked like the hotkey simply didn't work. Instead, type
                                # the command's text into whatever window currently has focus
                                # (same mechanism as a Type-text hotkey), so the technician sees
                                # it land in their open CMD window and can run it themselves.
                                sent = _type_text(hk['cmd'], multiline=hk.get('multiline', True))
                                print(f'[HK] typed cmd snippet, SendInput sent {sent} events', flush=True)
                            else:
                                sent = _type_text(hk.get('text') or '', multiline=hk.get('multiline', True))
                                print(f'[HK] SendInput sent {sent} events', flush=True)
                        except Exception as fire_err:
                            # One bad keystroke/command must not kill the
                            # listener for every hotkey after it.
                            print(f'[HK] Error firing {hk.get("label")}: {fire_err}', flush=True)
            else:
                time.sleep(0.02)

        _hk_status['thread_alive'] = False
        for hk_id in registered:
            result = user32.UnregisterHotKey(None, hk_id)
            if not result:
                ue = kernel32.GetLastError()
                print(f'[HK] UnregisterHotKey({hk_id}) FAILED err={ue}', flush=True)
            else:
                print(f'[HK] UnregisterHotKey({hk_id}) OK', flush=True)
        print('[HK] Thread stopped', flush=True)
    except Exception as e:
        _hk_status = {
            'registered': 0, 'failed': [], 'fired': 0,
            'thread_alive': False, 'crash': str(e)
        }
        print(f'[HK] Thread crashed: {e}', flush=True)

def start_hotkey_listener():
    global _hk_thread_ref, _hk_stop_evt
    stop_hotkey_listener()
    # A global hotkey belongs to whichever process registers it first, so
    # a dev copy opened before the exe would silently steal them for the
    # exe's whole session. Off in dev unless explicitly asked for.
    if IS_DEV and os.environ.get("ITERO_DEV_HOTKEYS") != "1":
        print("[HK] Dev run - hotkeys left to the installed exe "
              "(set ITERO_DEV_HOTKEYS=1 to test them here).", flush=True)
        return
    try:
        hotkeys = json.loads(open(_HK_PATH, encoding='utf-8').read()) if os.path.exists(_HK_PATH) else []
    except Exception:
        hotkeys = []
    if not any(h.get('enabled', True) and _VK_MAP.get((h.get('key') or '').upper()) for h in hotkeys):
        return
    _hk_stop_evt = threading.Event()
    _hk_thread_ref = threading.Thread(target=_hk_thread_func, args=(hotkeys,), daemon=True)
    _hk_thread_ref.start()

def stop_hotkey_listener():
    global _hk_thread_ref
    if _hk_thread_ref and _hk_thread_ref.is_alive():
        _hk_stop_evt.set()
        _hk_thread_ref.join(timeout=2.0)
        if _hk_thread_ref.is_alive():
            # The thread only checks the stop event between hotkey fires —
            # a long multiline snippet typed via SendInput (30ms/char) can
            # still be mid-flight well past 2s. Starting a new listener
            # while this one still owns the RegisterHotKey registrations
            # makes every hotkey in the new thread fail with
            # ERROR_HOTKEY_ALREADY_REGISTERED (1409), so give it more room
            # before giving up instead of silently discarding the reference.
            print('[HK] Thread still alive after 2s, waiting up to 8s more before giving up…', flush=True)
            _hk_thread_ref.join(timeout=8.0)
            if _hk_thread_ref.is_alive():
                print('[HK] Thread did not stop in time — new hotkeys may fail to register until it does.', flush=True)
    _hk_thread_ref = None
    # Give Win32 time to release hotkey handles before next RegisterHotKey call.
    time.sleep(0.15)

def get_hotkeys():
    try:
        if os.path.exists(_HK_PATH):
            with open(_HK_PATH, 'r', encoding='utf-8') as f:
                return ok(json.load(f))
        return ok([])
    except Exception as e:
        return err(str(e))

def save_hotkeys(data):
    try:
        hotkeys = json.loads(data) if isinstance(data, str) else data
        os.makedirs(os.path.dirname(_HK_PATH), exist_ok=True)
        with open(_HK_PATH, 'w', encoding='utf-8') as f:
            json.dump(hotkeys, f, ensure_ascii=False, indent=2)
        start_hotkey_listener()
        active = sum(1 for h in hotkeys if h.get('enabled', True))
        return ok(active)
    except Exception as e:
        return err(str(e))

def get_hotkey_status():
    running = _hk_thread_ref is not None and _hk_thread_ref.is_alive()
    return ok({
        'thread_running': running,
        'registered':     _hk_status.get('registered', 0),
        'failed':         _hk_status.get('failed', []),
        'fired':          _hk_status.get('fired', 0),
        'crash':          _hk_status.get('crash', ''),
        'input_struct_size': ctypes.sizeof(_INPUT),
    })

def test_type_text(delay_sec=2):
    """Type a test string after a delay so the user can switch focus."""
    def _do():
        time.sleep(float(delay_sec))
        sent = _type_text('iTero_HK_TEST_OK')
        print(f'[HK] test_type_text: SendInput returned {sent}', flush=True)
    threading.Thread(target=_do, daemon=True).start()
    return ok(f'Will type test string in {delay_sec}s — switch focus to a text field now')


# ─────────────────────────────────────────────
# APP SETTINGS (general, non-feature-specific)
# ─────────────────────────────────────────────

_APP_CFG_PATH = os.path.join(os.environ.get("APPDATA", "C:\\Users"), "iTeroToolBox", "app_config.json")


def _load_app_cfg():
    try:
        if os.path.exists(_APP_CFG_PATH):
            with open(_APP_CFG_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def get_debug_mode():
    return ok({"debug_mode": bool(_load_app_cfg().get("debug_mode", False))})


def set_debug_mode(enabled=False):
    try:
        cfg = _load_app_cfg()
        cfg["debug_mode"] = bool(enabled)
        os.makedirs(os.path.dirname(_APP_CFG_PATH), exist_ok=True)
        with open(_APP_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return ok(None, msg="Saved. Restart the app for this to take effect.")
    except Exception as e:
        return err(f"Could not save: {e}")


def get_cmd_visible():
    return ok({"cmd_visible": bool(_load_app_cfg().get("cmd_visible", False))})


def set_cmd_visible(enabled=False):
    """Unlike debug_mode, this applies live — the CMD panel is already in
    the DOM, just hidden/shown by the frontend, no relaunch needed."""
    try:
        cfg = _load_app_cfg()
        cfg["cmd_visible"] = bool(enabled)
        os.makedirs(os.path.dirname(_APP_CFG_PATH), exist_ok=True)
        with open(_APP_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return ok(bool(enabled))
    except Exception as e:
        return err(f"Could not save: {e}")


# ─────────────────────────────────────────────
# MAT (myaligntech.com) SCRAPER
# ─────────────────────────────────────────────
# Unlike Salesforce, MAT's login page (_MAT_LOGIN_URL, note "auth=false")
# always forces the login form regardless of any existing session cookie
# — so unattended scraping genuinely needs the password resubmitted on
# every call, not just once. It's stored on disk, DPAPI-encrypted
# (CryptProtectData) rather than in plaintext/base64 — DPAPI ties
# decryption to this specific Windows user account, so the file is
# useless to anyone without that account's login, unlike a reversible
# encoding.

import base64
import win32crypt

def _mat_dpapi_encrypt(plain_text):
    blob = win32crypt.CryptProtectData(plain_text.encode("utf-8"), "iTeroToolBox MAT credential", None, None, None, 0)
    return base64.b64encode(blob).decode("ascii")

def _mat_dpapi_decrypt(enc_b64):
    blob = base64.b64decode(enc_b64)
    _, decrypted = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return decrypted.decode("utf-8")

_MAT_CFG_PATH     = os.path.join(os.environ.get("APPDATA", "C:\\Users"), "iTeroToolBox", "mat_config.json")
_MAT_PROFILE_DIR  = os.path.join(os.environ.get("APPDATA", "C:\\Users"), "iTeroToolBox", "mat_profile" + DEV_SUFFIX)
_mat_driver = None  # kept alive between calls — same window/session reused
_mat_driver_lock = threading.Lock()  # guards the check-then-launch below so two overlapping calls can't both launch a driver

_SCANNER_PANEL_ID = "ctl00_body_tabsContainer_scannerTab"
# aria-controls lives on the <li role="tab">, not the <a> inside it — the
# anchor is what jQuery UI actually binds the click handler to, so select
# through the stable li and click its child anchor.
_SCANNER_TAB_CSS  = f"li[aria-controls='{_SCANNER_PANEL_ID}'] a"
_SCANNER_SN_ID   = "ctl00_body_tabsContainer_scannerTab_txtScanner"
_SCANNER_OK_ID   = "ctl00_body_tabsContainer_scannerTab_btnScanner"
_WAND_SN_ID      = "ctl00_body_txtEmbeddedHeadSerialIdentifier"
_SCANNER_SN_CONFIRMED_ID = "ctl00_body_txtSerialIdentifier"
_REG_ID          = "ctl00_body_txtRegToReadOnly"
_STATUS_ID       = "ctl00_body_ddlStatus"
_MODEL_PAGE_ID   = "ctl00_body_txtScannerModel"
_NOTES_ID        = "ctl00_body_txtNotes"
_SW_ROW_CSS      = "tr[class*='report-row']"


def mat_save_credentials(email, password_plain, show_browser=False, enabled=True):
    try:
        cfg = {
            "email":        email,
            "password_enc": _mat_dpapi_encrypt(password_plain),
            "show_browser": bool(show_browser),
            "enabled":      bool(enabled),
        }
        os.makedirs(os.path.dirname(_MAT_CFG_PATH), exist_ok=True)
        with open(_MAT_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return ok("Credentials saved.")
    except Exception as e:
        return err(str(e))


def mat_get_settings():
    """MAT's visible/enabled flags plus whether credentials are already
    configured — deliberately never echoes the email/password themselves
    back to the renderer, only a boolean, so the saved password can't be
    read back out through this call. Self-heals: any credential saved by
    an older, less-secure version of this app (plain base64, no DPAPI) is
    re-encrypted with DPAPI the first time it's read.
    """
    try:
        if not os.path.exists(_MAT_CFG_PATH):
            return ok({"show_browser": False, "enabled": False, "has_credentials": False})
        with open(_MAT_CFG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("password_b64") and not cfg.get("password_enc"):
            try:
                plain = base64.b64decode(cfg["password_b64"]).decode("utf-8")
                cfg["password_enc"] = _mat_dpapi_encrypt(plain)
            except Exception:
                pass
            cfg.pop("password_b64", None)
            try:
                with open(_MAT_CFG_PATH, "w", encoding="utf-8") as f:
                    json.dump(cfg, f)
            except Exception:
                pass
        return ok({
            "show_browser":    cfg.get("show_browser", False),
            "enabled":         cfg.get("enabled", False),
            "has_credentials": bool(cfg.get("email") and cfg.get("password_enc")),
        })
    except Exception as e:
        return err(str(e))


def mat_set_enabled(enabled):
    """Toggle MAT auto-scrape on/off."""
    try:
        cfg = {}
        if os.path.exists(_MAT_CFG_PATH):
            with open(_MAT_CFG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["enabled"] = bool(enabled)
        os.makedirs(os.path.dirname(_MAT_CFG_PATH), exist_ok=True)
        with open(_MAT_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return ok(bool(enabled))
    except Exception as e:
        return err(str(e))


def mat_save_show_browser(show_browser):
    """Toggle MAT's browser visibility."""
    try:
        cfg = {}
        if os.path.exists(_MAT_CFG_PATH):
            with open(_MAT_CFG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["show_browser"] = bool(show_browser)
        os.makedirs(os.path.dirname(_MAT_CFG_PATH), exist_ok=True)
        with open(_MAT_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return ok(bool(show_browser))
    except Exception as e:
        return err(str(e))


_edge_binary_cache = None


def _find_edge_binary():
    """Locate the real msedge.exe. msedgedriver's own guess assumes the
    consumer install layout (Program Files\\Microsoft Edge\\Application\\
    msedge.exe) -- enterprise-managed installs commonly put it one level
    deeper instead (Program Files\\Microsoft\\Edge\\Application\\msedge.exe),
    which makes that guess point at a file that doesn't exist and produces
    a "DevToolsActivePort file doesn't exist" crash on every launch. The
    registry's App Paths entry is authoritative regardless of layout."""
    global _edge_binary_cache
    if _edge_binary_cache is not None:
        return _edge_binary_cache or None

    path = None
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\msedge.exe",
        ) as key:
            reg_path, _ = winreg.QueryValueEx(key, None)
            if reg_path and os.path.exists(reg_path):
                path = reg_path
    except Exception:
        pass

    if not path:
        for candidate in (
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files (x86)\Microsoft Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft Edge\Application\msedge.exe",
        ):
            if os.path.exists(candidate):
                path = candidate
                break

    _edge_binary_cache = path or ""
    return path


_MAT_LOGIN_URL = "https://myaligntech.com/login.aspx?auth=false&ReturnUrl=%2f"


def _mat_prep_profile():
    """Same 'exited abnormally' patch as the SF profile — stops headless
    Chromium from wedging on an unshowable 'Restore pages?' prompt."""
    prefs_path = os.path.join(_MAT_PROFILE_DIR, "Default", "Preferences")
    try:
        if os.path.exists(prefs_path):
            with open(prefs_path, encoding="utf-8") as f:
                prefs = json.load(f)
            prefs.setdefault("profile", {})["exit_type"] = "Normal"
            prefs["profile"]["exited_cleanly"] = True
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f)
    except Exception:
        pass


def _mat_launch_driver(show):
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options

    os.makedirs(_MAT_PROFILE_DIR, exist_ok=True)
    _mat_prep_profile()

    opts = Options()
    edge_binary = _find_edge_binary()
    if edge_binary:
        opts.binary_location = edge_binary
    opts.add_argument(f"--user-data-dir={_MAT_PROFILE_DIR}")
    opts.add_argument("--profile-directory=Default")
    if not show:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-first-run")
    opts.add_argument("--disable-session-crashed-bubble")
    opts.add_argument("--disable-infobars")
    opts.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Edge(options=opts)


def _mat_get_driver(show):
    """Reuse the persistent MAT driver across calls — same profile dir as
    always, so a manually-completed SSO login survives past this one call
    instead of being thrown away before its cookie is on disk."""
    global _mat_driver
    with _mat_driver_lock:
        if _mat_driver is not None:
            try:
                _ = _mat_driver.window_handles  # liveness check
                return _mat_driver
            except Exception:
                _mat_driver = None
        _mat_driver = _mat_launch_driver(show)
        return _mat_driver


def _mat_close_if_headless():
    """Mirror of _sf_close_if_headless — quit the driver after use so we
    don't leave an orphaned msedge.exe around, unless the technician has
    'Show browser' on and is presumably looking at it."""
    global _mat_driver
    show_browser = False
    try:
        if os.path.exists(_MAT_CFG_PATH):
            with open(_MAT_CFG_PATH, encoding="utf-8") as f:
                show_browser = bool(json.load(f).get("show_browser", False))
    except Exception:
        pass
    if show_browser or _mat_driver is None:
        return
    try:
        _mat_driver.quit()
    except Exception:
        pass
    _mat_driver = None


def mat_scrape(serial):
    global _mat_driver
    try:
        if not os.path.exists(_MAT_CFG_PATH):
            return err("No MAT credentials. Configure in Settings → MAT.")
        with open(_MAT_CFG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        email = cfg.get("email", "")
        try:
            password = _mat_dpapi_decrypt(cfg["password_enc"]) if cfg.get("password_enc") else ""
        except Exception:
            password = ""
        show = cfg.get("show_browser", False)
        if not email or not password:
            return err("MAT credentials incomplete. Configure in Settings → MAT.")
        # One-shot override left behind by mat_logout() — the freshly wiped
        # profile needs a human to see the login page once; every call
        # after this one goes back to the normal show_browser setting.
        if cfg.get("force_visible_once"):
            show = True
            cfg["force_visible_once"] = False
            try:
                with open(_MAT_CFG_PATH, "w", encoding="utf-8") as f:
                    json.dump(cfg, f)
            except Exception:
                pass
    except Exception as e:
        return err(f"Config read error: {e}")

    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException
    except ImportError:
        return err("selenium not installed. Run: pip install selenium")

    driver = None
    try:
        driver = _mat_get_driver(show)
        # Ignore stale refs — elements go stale during ASP.NET postbacks
        wait = WebDriverWait(driver, 25,
                             ignored_exceptions=[StaleElementReferenceException,
                                                 NoSuchElementException])

        # ── Login ──────────────────────────────────────────────
        driver.get(_MAT_LOGIN_URL)
        time.sleep(1.0)

        def _on_mat():
            u = driver.current_url.lower()
            return "myaligntech.com" in u and "login.aspx" not in u

        if not _on_mat():
            # Either the local login form, or the site bounced us out to a
            # Microsoft/Okta SSO page instead. This login URL forces the
            # form regardless of any existing session (see _MAT_LOGIN_URL),
            # so this runs on every call, not just the first.
            has_local_form = False
            try:
                driver.find_element(By.ID, "LoginControl_UserName")
                has_local_form = True
            except Exception:
                pass

            if has_local_form:
                driver.find_element(By.ID, "LoginControl_UserName").clear()
                driver.find_element(By.ID, "LoginControl_UserName").send_keys(email)
                driver.find_element(By.ID, "LoginControl_Password").clear()
                driver.find_element(By.ID, "LoginControl_Password").send_keys(password)
                driver.execute_script(
                    "document.getElementById('LoginControl_LoginButton').click();"
                )
                wait.until(lambda d: "login.aspx" not in d.current_url)
                time.sleep(0.8)

            if not _on_mat():
                # SSO gate (or the local form failed) — needs a human. If
                # we're headless there's nothing for them to look at, so
                # relaunch visibly and hand it back for a one-time manual
                # pass; the session then persists in the profile on disk
                # for every call after this one, headless or not.
                if not show:
                    try:
                        driver.quit()
                    except Exception:
                        pass
                    _mat_driver = None
                    driver = _mat_get_driver(True)
                    driver.get(_MAT_LOGIN_URL)
                return ok({"status_text": "login_required"},
                          msg="Log in on the MAT window that opened, then try again.")

        # ── Click Scanner tab via JS (jQuery UI anchor with tabindex=-1) ──
        # Target by aria-controls (tied to the stable scannerTab panel id)
        # rather than the tab anchor's own id — jQuery UI assigns those as
        # "ui-id-N" in page order, which silently points at a different tab
        # (e.g. Wand) if MAT ever adds/reorders a tab ahead of Scanner.
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, _SCANNER_TAB_CSS)))
        driver.execute_script(
            "var a = document.querySelector(arguments[0]); if (a) a.click();",
            _SCANNER_TAB_CSS
        )
        # Wait for the scanner SN input to become visible inside the tab panel
        wait.until(EC.visibility_of_element_located((By.ID, _SCANNER_SN_ID)))
        time.sleep(0.4)

        # ── Fill scanner SN and click OK via JS ────────────────
        driver.execute_script(
            "var f=document.getElementById(arguments[0]);f.value=arguments[1];",
            _SCANNER_SN_ID, serial
        )
        driver.execute_script(
            "document.getElementById(arguments[0]).click();", _SCANNER_OK_ID
        )

        # ── Wait for postback / UpdatePanel to finish ──────────
        # Strategy: poll until wand SN field has a non-empty value.
        # StaleElementReferenceException is ignored by our wait instance,
        # so we safely re-find the element on every poll tick.
        time.sleep(1.5)

        def wand_ready(d):
            el = d.find_element(By.ID, _WAND_SN_ID)
            return bool(el.get_attribute("value").strip())

        wand_sn = ""
        try:
            wait.until(wand_ready)
            wand_sn = driver.find_element(By.ID, _WAND_SN_ID).get_attribute("value").strip()
        except Exception as wait_err:
            # Postback may have completed but field is genuinely empty (SN not found).
            # Try reading anyway before giving up.
            try:
                wand_sn = driver.find_element(By.ID, _WAND_SN_ID).get_attribute("value").strip()
            except Exception:
                wand_sn = ""

        # ── Confirmed scanner S/N (as MAT itself reports it back, not just
        #    an echo of what we searched with — used for the S/N cross-check
        #    against the ticket and the Salesforce Subject) ────────────────
        scanner_sn = ""
        try:
            scanner_sn = driver.find_element(By.ID, _SCANNER_SN_CONFIRMED_ID).get_attribute("value").strip()
        except Exception:
            pass

        reg_to = ""
        try:
            reg_to = driver.find_element(By.ID, _REG_ID).get_attribute("value").strip()
        except Exception:
            pass

        # ── Status (Active / Inactive) ─────────────────────────
        status = ""
        try:
            from selenium.webdriver.support.ui import Select as SeleniumSelect
            sel_el  = driver.find_element(By.ID, _STATUS_ID)
            sel_val = SeleniumSelect(sel_el).first_selected_option.get_attribute("value")
            status  = "Active" if sel_val == "0" else "Inactive"
        except Exception:
            pass

        # ── Scanner model ──────────────────────────────────────
        scanner_model = ""
        try:
            scanner_model = driver.find_element(By.ID, _MODEL_PAGE_ID).get_attribute("value").strip()
        except Exception:
            pass

        # ── Notes ──────────────────────────────────────────────
        notes = ""
        try:
            notes = driver.find_element(By.ID, _NOTES_ID).get_attribute("value").strip()
        except Exception:
            pass

        # ── SW Package (first report-row: pkg=td[2], expiry=td[4]) ──
        sw_package = ""
        sw_expiry  = ""
        try:
            rows = driver.find_elements(By.CSS_SELECTOR, _SW_ROW_CSS)
            for row in rows:
                tds = row.find_elements(By.TAG_NAME, "td")
                if len(tds) < 5:
                    continue
                # td[1] holds the row code — individual SW options are
                # "SOP-xxxxx" (empty dates), the actual package/bundle
                # row is "BUN-xxxxx" and is the only one with real dates.
                code = (tds[1].get_attribute("textContent") or "").strip()
                if not code.upper().startswith("BUN"):
                    continue
                # Use textContent, not .text — the row's container may be
                # hidden (display:none) until the user clicks "editar" in
                # the real UI, and .text returns "" for hidden elements.
                sw_package = (tds[2].get_attribute("textContent") or "").strip()
                sw_expiry  = (tds[4].get_attribute("textContent") or "").strip()
                break
        except Exception:
            pass

        # ── Company info (click "Reg. To" → Business Partner page) ──
        company_id      = ""
        company_name    = ""
        company_address = ""
        try:
            reg_link = driver.find_element(By.CSS_SELECTOR, "a[href*='BusinessPartnerPage.aspx']")
            driver.execute_script("arguments[0].click();", reg_link)
            wait.until(EC.presence_of_element_located((By.ID, "ctl00_body_EntityNameLabel")))
            name_text = driver.find_element(By.ID, "ctl00_body_EntityNameLabel").text.strip()
            company_address = driver.find_element(By.ID, "ctl00_body_EntityDescriptionLabel").text.strip()
            # name_text looks like "[Company ID: 112940] Dr. Sepideh Badri"
            m = re.search(r"\[Company ID:\s*(\d+)\]\s*(.*)", name_text)
            if m:
                company_id   = m.group(1)
                company_name = m.group(2).strip()
            else:
                company_name = name_text
        except Exception:
            pass

        _mat_close_if_headless()

        result = {
            "serial":          serial,
            "scanner_sn":      scanner_sn,
            "wand_sn":         wand_sn,
            "reg_to":          reg_to,
            "status":          status,
            "scanner_model":   scanner_model,
            "notes":           notes,
            "sw_package":      sw_package,
            "sw_expiry":       sw_expiry,
            "company_id":      company_id,
            "company_name":    company_name,
            "company_address": company_address,
        }
        if not wand_sn:
            result["debug"] = "Wand field empty — check the S/N or the MAT flow"
        return ok(result)

    except Exception as e:
        if driver:
            try: driver.quit()
            except Exception: pass
        _mat_driver = None
        return err(f"MAT scrape error: {e}")


def mat_close_browser():
    global _mat_driver
    if _mat_driver is not None:
        try:
            _mat_driver.quit()
        except Exception:
            pass
        _mat_driver = None
    return ok("Browser closed.")


def mat_logout():
    """A real logout, unlike mat_close_browser() (which only closes the
    window and leaves the session cookie on disk for next time): quits the
    driver, wipes the persisted profile so the saved session is actually
    gone, and flags the next mat_scrape() call to launch visibly — the
    freshly logged-out account needs a human to log back in (local form or
    SSO) once; every call after that reuses the newly saved session and
    goes back to the normal show_browser setting, headless or not."""
    global _mat_driver
    if _mat_driver is not None:
        try:
            _mat_driver.quit()
        except Exception:
            pass
        _mat_driver = None

    import shutil
    try:
        shutil.rmtree(_MAT_PROFILE_DIR, ignore_errors=True)
    except Exception:
        pass

    try:
        cfg = {}
        if os.path.exists(_MAT_CFG_PATH):
            with open(_MAT_CFG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["force_visible_once"] = True
        os.makedirs(os.path.dirname(_MAT_CFG_PATH), exist_ok=True)
        with open(_MAT_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except Exception:
        pass

    return ok("Logged out of MAT.")


# ─────────────────────────────────────────────
# SALESFORCE (SF) — TICKET CHECKER
# ─────────────────────────────────────────────
# Unlike MAT, this doesn't store credentials — the technician is already
# logged into Salesforce via corporate SSO on this machine. We drive a
# dedicated, always-visible Edge window with its own persistent profile:
# the first use requires a manual SSO login in that window, and every call
# after that reuses the saved session cookies automatically.

_SF_HOME_URL    = "https://aligntech.lightning.force.com/lightning/page/home"
_SF_PROFILE_DIR = os.path.join(os.environ.get("APPDATA", "C:\\Users"), "iTeroToolBox", "sf_profile" + DEV_SUFFIX)
_SF_CFG_PATH    = os.path.join(os.environ.get("APPDATA", "C:\\Users"), "iTeroToolBox", "sf_config.json")
_sf_driver      = None  # kept alive between calls — same window/session reused
_sf_driver_lock = threading.Lock()  # guards the check-then-launch below so two overlapping calls can't both launch a driver
_sf_mail_sent   = False  # set by sf_open_ticket's mail check, read back by sf_read_ticket


def sf_load_settings():
    try:
        if os.path.exists(_SF_CFG_PATH):
            with open(_SF_CFG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
            return ok({"show_browser": bool(cfg.get("show_browser", False))})
    except Exception:
        pass
    return ok({"show_browser": False})


def sf_save_settings(show_browser=False):
    try:
        os.makedirs(os.path.dirname(_SF_CFG_PATH), exist_ok=True)
        with open(_SF_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump({"show_browser": bool(show_browser)}, f)
        return ok(None)
    except Exception as e:
        return err(f"Could not save: {e}")


def _sf_drop_driver_if_connection_dead(exc):
    """sf_read_ticket() and esc_report_sf_lookup() reuse the _sf_driver that
    sf_open_ticket() already opened a moment earlier, instead of going
    through _sf_get_driver()'s liveness check (window_handles) again — so
    if the underlying msedgedriver.exe process dies in that gap (crash,
    killed by AV, etc.), the read fails with a raw urllib3 "connection
    refused" error and the dead reference stays cached in _sf_driver.
    Without this, every call after that keeps hitting the exact same
    connection-refused error forever, until the whole app is restarted.
    Recognize that failure signature and drop the stale reference so the
    *next* sf_open_ticket() call (which does go through _sf_get_driver())
    launches a fresh browser instead of trying to reuse the dead one."""
    global _sf_driver
    msg = str(exc)
    if any(s in msg for s in ("NewConnectionError", "Max retries exceeded",
                               "WinError 10061", "Connection refused")):
        _sf_driver = None


def _sf_get_driver():
    global _sf_driver
    with _sf_driver_lock:
        if _sf_driver is not None:
            try:
                _ = _sf_driver.window_handles  # liveness check — throws if the window was closed
                return _sf_driver
            except Exception:
                _sf_driver = None

        from selenium import webdriver
        from selenium.webdriver.edge.options import Options

        show_browser = False
        try:
            if os.path.exists(_SF_CFG_PATH):
                with open(_SF_CFG_PATH, encoding="utf-8") as f:
                    sf_cfg = json.load(f)
                show_browser = bool(sf_cfg.get("show_browser", False))
                # One-shot override left behind by sf_logout() — the freshly
                # wiped profile needs a human to see the SSO login page once;
                # every call after this one goes back to the normal
                # show_browser setting.
                if sf_cfg.get("force_visible_once"):
                    show_browser = True
                    sf_cfg["force_visible_once"] = False
                    try:
                        with open(_SF_CFG_PATH, "w", encoding="utf-8") as f:
                            json.dump(sf_cfg, f)
                    except Exception:
                        pass
        except Exception:
            pass

        os.makedirs(_SF_PROFILE_DIR, exist_ok=True)

        # If a previous run of this profile was killed/crashed (very possible
        # while we were debugging the --no-sandbox crash earlier), Chromium
        # marks the profile as "exited abnormally" and wants to show a
        # "Restore pages?" prompt on next launch. In headless mode that prompt
        # can't render, so the browser just sits there as a blank, unresponsive
        # window forever. Patch the profile's Preferences to say it exited
        # cleanly so that prompt never triggers.
        prefs_path = os.path.join(_SF_PROFILE_DIR, "Default", "Preferences")
        try:
            if os.path.exists(prefs_path):
                with open(prefs_path, encoding="utf-8") as f:
                    prefs = json.load(f)
                prefs.setdefault("profile", {})["exit_type"] = "Normal"
                prefs["profile"]["exited_cleanly"] = True
                with open(prefs_path, "w", encoding="utf-8") as f:
                    json.dump(prefs, f)
        except Exception:
            pass

        opts = Options()
        edge_binary = _find_edge_binary()
        if edge_binary:
            opts.binary_location = edge_binary
        opts.add_argument(f"--user-data-dir={_SF_PROFILE_DIR}")
        opts.add_argument("--profile-directory=Default")
        if not show_browser:
            opts.add_argument("--headless=new")
        # The app runs elevated (admin) — Chromium's sandbox refuses to
        # initialize under Administrator/SYSTEM without --no-sandbox, which
        # crashes the browser instantly ("DevToolsActivePort file doesn't
        # exist"). MAT's launcher already carries these same flags.
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--no-first-run")
        opts.add_argument("--disable-session-crashed-bubble")
        opts.add_argument("--disable-infobars")
        opts.add_experimental_option("excludeSwitches", ["enable-logging"])

        _sf_driver = webdriver.Edge(options=opts)
        return _sf_driver


def sf_open_home():
    """Open (or focus) the dedicated Salesforce window at the home page —
    used for the first-time manual SSO login, or just to bring it forward."""
    try:
        driver = _sf_get_driver()
    except Exception as e:
        return err(f"Could not open the Salesforce browser: {e}")
    try:
        driver.get(_SF_HOME_URL)
        driver.switch_to.window(driver.current_window_handle)
        return ok(None, msg="Salesforce opened.")
    except Exception as e:
        return err(f"Error opening Salesforce: {e}")


_MAIL_DEEP_TEXT_JS = r"""
function deepText(el) {
    var text = '';
    function walk(node) {
        if (node.nodeType === Node.TEXT_NODE) { text += node.textContent; return; }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        if (node.tagName === 'BR') { text += '\n'; return; }
        if (node.shadowRoot) {
            var sc = node.shadowRoot.childNodes;
            for (var i = 0; i < sc.length; i++) walk(sc[i]);
        }
        var kids = node.childNodes;
        for (var j = 0; j < kids.length; j++) walk(kids[j]);
    }
    walk(document.body);
    return text;
}
return deepText();
"""


def _sf_find_text_all_frames(driver, script, needle, max_depth=4):
    """Best-effort: run `script` (returns page text) in the top document and
    every iframe in turn until one contains `needle`. The email composer's
    rich-text body commonly renders inside its own iframe, same as the
    Case detail fields do for their own reasons (see _sf_search_all_frames)."""
    from selenium.webdriver.common.by import By

    def search(depth):
        try:
            text = driver.execute_script(script) or ""
        except Exception:
            text = ""
        if needle in text:
            return text
        if depth >= max_depth:
            return ""
        try:
            frames = driver.find_elements(By.TAG_NAME, "iframe") + driver.find_elements(By.TAG_NAME, "frame")
        except Exception:
            frames = []
        for fr in frames:
            try:
                driver.switch_to.frame(fr)
            except Exception:
                continue
            try:
                sub = search(depth + 1)
            except Exception:
                sub = ""
            driver.switch_to.parent_frame()
            if sub:
                return sub
        return ""

    driver.switch_to.default_content()
    try:
        return search(0)
    finally:
        driver.switch_to.default_content()


_EMAIL_RE = re.compile(r"[^\s<>\[\]@]+@[^\s<>\[\]@]+\.[^\s<>\[\]@]+")


_sf_mail_debug = {}  # last _sf_check_mail_sent() run — which stage it stopped at, and why


def _sf_check_mail_sent(driver, ticket_number):
    """Click into the case's "Send an Email" tab and validate the quoted
    "Original Message" block underneath the compose form — the actual
    previous email about this ticket, not the compose form's own fields
    (which have their own unrelated From/Subject inputs):

      From:    Abraham Orthodontics [info@abrahamorthodontics.com]
      To:      iterosupport@aligntech.com
      Subject: Re: Part Request | Ticket Number 67142810 | ...

    Mail Check only comes back green if From has a real email address, To
    has a real email address, and Subject says "Part Request" for this
    exact ticket number (the one currently open in Salesforce). Best-effort
    and non-fatal — any failure here just means Mail Check comes back
    not-sent, it never blocks the rest of the ticket read. Every step's
    outcome is recorded into _sf_mail_debug (read back by sf_read_ticket)
    so a false negative can actually be diagnosed instead of just "it's
    red" — since none of this can be watched live in headless mode."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    global _sf_mail_debug
    dbg = {"stage": "start"}
    _sf_mail_debug = dbg

    try:
        wait = WebDriverWait(driver, 10)
        try:
            tab = wait.until(EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a[data-target-selection-name='Case.Send_an_EmailTab']")))
        except Exception as e:
            dbg["stage"] = "tab_not_found"
            dbg["error"] = str(e)
            return False
        dbg["stage"] = "tab_found"

        driver.execute_script("arguments[0].click();", tab)
        time.sleep(1.5)
        dbg["stage"] = "tab_clicked"

        body_text = _sf_find_text_all_frames(driver, _MAIL_DEEP_TEXT_JS, "Original Message")
        dbg["body_text_len"] = len(body_text)
        idx = body_text.find("Original Message")
        if idx == -1:
            dbg["stage"] = "original_message_not_found"
            dbg["body_text_snippet"] = body_text[:1500]
            return False
        dbg["stage"] = "original_message_found"

        # Only look inside the quoted block itself — the compose form above
        # it has its own From/Subject fields that would otherwise be found
        # first and checked instead of the actual previous email.
        quoted = body_text[idx:]
        dbg["quoted_snippet"] = quoted[:600]

        from_m    = re.search(r"From:\s*([^\n]*)", quoted)
        to_m      = re.search(r"To:\s*([^\n]*)", quoted)
        subject_m = re.search(r"Subject:\s*([^\n]*)", quoted)
        dbg["from_line"]    = from_m.group(1) if from_m else None
        dbg["to_line"]      = to_m.group(1) if to_m else None
        dbg["subject_line"] = subject_m.group(1) if subject_m else None
        if not (from_m and to_m and subject_m):
            dbg["stage"] = "from_to_subject_lines_not_found"
            return False

        from_ok = bool(_EMAIL_RE.search(from_m.group(1)))
        to_ok   = bool(_EMAIL_RE.search(to_m.group(1)))
        dbg["from_email_ok"] = from_ok
        dbg["to_email_ok"]   = to_ok
        if not from_ok:
            dbg["stage"] = "from_email_invalid"
            return False
        if not to_ok:
            dbg["stage"] = "to_email_invalid"
            return False

        subject_text = subject_m.group(1)
        has_part_request = bool(re.search(r"part\s*request", subject_text, re.IGNORECASE))
        dbg["subject_has_part_request"] = has_part_request
        if not has_part_request:
            dbg["stage"] = "subject_missing_part_request"
            return False

        ticket_m = re.search(r"ticket\s*number\s*(\d+)", subject_text, re.IGNORECASE)
        wanted_ticket = re.sub(r"\D", "", ticket_number or "")
        dbg["ticket_in_subject"] = ticket_m.group(1) if ticket_m else None
        dbg["wanted_ticket"] = wanted_ticket
        # Compare numerically, not as strings — a leading zero on either
        # side (Salesforce's rendering vs. what the agent typed) would
        # otherwise fail an exact string match despite being the same ticket.
        if not (ticket_m and wanted_ticket) or int(ticket_m.group(1)) != int(wanted_ticket):
            dbg["stage"] = "ticket_number_mismatch"
            return False

        dbg["stage"] = "ok"
        return True
    except Exception as e:
        dbg["stage"] = "exception"
        dbg["error"] = str(e)
        return False


def sf_open_ticket(ticket_number=""):
    """Type a ticket number into Salesforce's global search and press Enter
    to land on the search results page."""
    ticket_number = (ticket_number or "").strip()
    if not ticket_number:
        return err("Enter a ticket number.")

    try:
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.keys import Keys
        from selenium.webdriver.common.action_chains import ActionChains
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC
        from selenium.common.exceptions import StaleElementReferenceException, TimeoutException
    except ImportError:
        return err("selenium not installed. Run: pip install selenium")

    try:
        driver = _sf_get_driver()
    except Exception as e:
        return err(f"Could not open the Salesforce browser: {e}")

    try:
        driver.get(_SF_HOME_URL)
        wait = WebDriverWait(driver, 20, ignored_exceptions=[StaleElementReferenceException])

        # Give the SPA a moment to redirect to the SSO/login page if the
        # saved session has expired.
        time.sleep(1.5)
        if "lightning.force.com" not in driver.current_url:
            return ok({"status_text": "login_required"},
                      msg="Log in on the Salesforce window that opened, then try again.")

        # Open the global search box. Salesforce auto-focuses the input the
        # instant it opens — trying to separately locate and click that
        # input ourselves was the bug: with several similar elements in
        # that widget (the "Search: All" scope dropdown sits right next to
        # it), our click was landing on the wrong one and knocking focus
        # off the real field. Instead, just type at whatever the browser
        # currently has focused — no element targeting required.
        search_btn = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button.search-button, button[aria-label='Search']")))
        try:
            search_btn.click()
        except Exception:
            # Salesforce's home page sometimes shows a promotional carousel
            # banner that visually overlaps the search button, which makes
            # Selenium's native click raise ElementClickIntercepted even
            # though the button is technically "clickable" per the wait
            # above. A JS-triggered click ignores what's on top of it.
            driver.execute_script("arguments[0].click();", search_btn)

        typed_value = ""
        for attempt in range(4):
            time.sleep(0.5 + attempt * 0.4)  # give the SPA progressively more settle time
            ActionChains(driver).send_keys(ticket_number).perform()
            typed_value = driver.execute_script(
                "var el = document.activeElement; return el ? (el.value || '') : '';"
            ) or ""
            if ticket_number in typed_value:
                break  # text landed — move on to waiting for suggestions
            # Didn't land (or landed partially) — clear whatever's in the
            # focused field before the next attempt so we don't accumulate
            # garbage across retries.
            ActionChains(driver).key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).send_keys(Keys.DELETE).perform()

        if ticket_number not in typed_value:
            return err(f"The search field never received the text after several attempts "
                       f"(ended up with: \"{typed_value}\"). Check the Salesforce window.")

        # Text landed — press Enter right away to run the full search and
        # land on the results page.
        ActionChains(driver).send_keys(Keys.RETURN).perform()

        # The results page renders the matched record's number as a real
        # <a href="/lightning/r/<id>/view" class="outputLookupLink" target=
        # "_blank">. Give it 2.5s to render, then click it. We use a native
        # Selenium click (not a JS-triggered one) so Edge treats it as a
        # trusted user gesture and opens the new tab in the foreground.
        time.sleep(2.5)
        try:
            links = WebDriverWait(driver, 8, ignored_exceptions=[StaleElementReferenceException]).until(
                lambda d: [a for a in d.find_elements(By.CSS_SELECTOR, "a.outputLookupLink[data-recordid]")
                           if a.is_displayed()] or False)
        except TimeoutException:
            return ok({"status_text": "no_case_match"},
                      msg=f"Searched \"{ticket_number}\", but the ticket link never showed up. Check the Salesforce window.")

        link = next((a for a in links
                     if (a.get_attribute("title") or a.text or "").strip() == ticket_number), links[0])

        handles_before = driver.window_handles
        link.click()

        # target="_blank" opens a new tab — follow the driver's focus there
        # so the app (and the technician) end up looking at the ticket. Some
        # orgs also pop a Twilio softphone window around the same time, so
        # among the new handles we specifically pick the one that actually
        # looks like a Salesforce record view rather than just grabbing the
        # last one opened.
        time.sleep(1.2)
        new_handles = [h for h in driver.window_handles if h not in handles_before]
        record_handle = None
        for h in new_handles:
            try:
                driver.switch_to.window(h)
                url = (driver.current_url or "").lower()
                if "lightning.force.com" in url and "twilio" not in url:
                    record_handle = h
                    break
            except Exception:
                continue

        # Any other window that popped open alongside the ticket (most
        # commonly that Twilio softphone tab) shares this same Salesforce
        # identity — leaving it open can knock the technician's own,
        # separate softphone session offline, since Twilio Client
        # typically allows only one live connection per identity. Close
        # everything except the one we're actually keeping — including
        # handles_before: on a repeated caller (Escalations Report's Find
        # All), that's the *previous* ticket's tab, which this search just
        # navigated back to the SF home page instead of reusing for the
        # new record. Left unclosed, it silently piles up one more stray
        # tab per ticket over a long batch.
        #
        # Only closes handles_before when keep_handle is real (a fresh tab
        # actually opened) — if the click ever doesn't open one and
        # keep_handle ends up None, closing every handle_before tab would
        # leave the browser with zero windows open, which kills the whole
        # WebDriver session on its next command instead of just failing
        # this one search.
        keep_handle = record_handle or (new_handles[-1] if new_handles else None)
        stale_handles = list(new_handles) + (list(handles_before) if keep_handle is not None else [])
        for h in stale_handles:
            if h == keep_handle:
                continue
            try:
                driver.switch_to.window(h)
                driver.close()
            except Exception:
                pass

        if keep_handle is not None:
            driver.switch_to.window(keep_handle)

        # Give the record page's LWCs a moment to finish rendering before
        # anything tries to read fields off it.
        time.sleep(3)

        # First thing on landing on the ticket, before anything else reads
        # a single field off it — click into "Send an Email" and check
        # whether a prior email for this ticket actually went out.
        global _sf_mail_sent
        _sf_mail_sent = _sf_check_mail_sent(driver, ticket_number)

        return ok({"status_text": "opened"}, msg=f"Ticket {ticket_number} opened.")

    except Exception as e:
        return err(f"Error searching for the ticket: {e}")


# Scanner S/N format: PREFIX(3) + YEAR(4, 2017-20xx) + LETTER + 2 DIGITS +
# LETTER + 3 DIGITS, e.g. YUC2022W18A069 — mirrors SN_REGEX in
# itero_toolbox_v1.html, used here to trim the Asset field down to "S/N
# onward" (Case.Asset text includes an internal record prefix before it).
_SN_REGEX = re.compile(r"(?:BLX|YUC|NZK|WOA|PLA)(?:20(?:1[7-9]|[2-9]\d))[A-Z]\d{2}[A-Z]\d{3}")


_SF_DEEP_EXTRACT_JS = r"""
function deepQueryAll(sel, root) {
    root = root || document;
    var results = Array.prototype.slice.call(root.querySelectorAll(sel));
    var all = root.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
        if (all[i].shadowRoot) {
            results = results.concat(deepQueryAll(sel, all[i].shadowRoot));
        }
    }
    return results;
}

function realParent(node) {
    // node.parentElement is null once you reach the top of a shadow root's
    // content -- the true parent at that point is the shadow HOST, reached
    // via getRootNode().host, not a further .parentElement hop. Without
    // this, climbing stops dead at the first shadow boundary.
    if (node.parentElement) return node.parentElement;
    var root = node.getRootNode();
    if (root && root.host) return root.host;
    return null;
}

function deepText(el) {
    var text = '';
    function walk(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            text += node.textContent;
            return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        // <br> carries no text node of its own, so without this the line
        // it separates gets silently glued to the next one (e.g. an
        // address's street line running straight into the city line).
        if (node.tagName === 'BR') { text += '\n'; return; }
        if (node.shadowRoot) {
            var sc = node.shadowRoot.childNodes;
            for (var i = 0; i < sc.length; i++) walk(sc[i]);
        }
        var kids = node.childNodes;
        for (var j = 0; j < kids.length; j++) walk(kids[j]);
    }
    walk(el);
    return text.replace(/[ \t]*\n[ \t]*/g, '\n').trim();
}

// Finds the nearest records-record-layout-item[field-label] ancestor
// (climbing the real, shadow-crossing parent chain) starting from `node`
// itself, and returns its field-label text ('' if none found within a
// reasonable depth).
function _nearestFieldLabel(node) {
    for (var depth = 0; depth < 8 && node; depth++) {
        if (node.tagName === 'RECORDS-RECORD-LAYOUT-ITEM' && node.hasAttribute && node.hasAttribute('field-label')) {
            return (node.getAttribute('field-label') || '').trim();
        }
        node = realParent(node);
    }
    return '';
}

// True unless `valEl` demonstrably belongs to a DIFFERENT field than
// `labelText` — i.e. climbing from valEl itself lands on some other
// field's own field-label host. Salesforce renders several fields side by
// side sharing a wider row-level ancestor, and each individual field still
// gets its own (closer, more specific) field-label host nested inside that
// row — so this catches a neighboring field's value even when it's found
// nested inside what looked like the right field's container.
function _valueBelongsToLabel(valEl, labelText) {
    if (!labelText) return true;
    var found = _nearestFieldLabel(valEl);
    return !found || found.toLowerCase() === labelText.toLowerCase();
}

// Looks only inside each given container -- no climbing outside it. Used
// for field-label hosts (see findValueElementByLabel below), where the
// value is always nested directly inside the host itself, so reaching
// outside it risks grabbing a neighboring field's value instead of
// correctly reporting "empty". labelText (optional) is re-verified against
// each candidate's own nearest field-label ancestor, which is what actually
// guards against a shared/too-broad container (see _valueBelongsToLabel).
function findValueDirectlyIn(containers, labelText) {
    for (var i = 0; i < containers.length; i++) {
        var valEls = deepQueryAll('.test-id__field-value', containers[i]);
        for (var j = 0; j < valEls.length; j++) {
            if (deepText(valEls[j]) && _valueBelongsToLabel(valEls[j], labelText)) return valEls[j];
        }
        var direct = deepQueryAll('[data-output-element-id="output-field"]', containers[i]);
        for (var d = 0; d < direct.length; d++) {
            if (deepText(direct[d]) && _valueBelongsToLabel(direct[d], labelText)) return direct[d];
        }
    }
    return null;
}

function findValueElementIn(containers) {
    var found = findValueDirectlyIn(containers);
    if (found) return found;
    for (var i = 0; i < containers.length; i++) {
        // The actual value is often NOT nested inside this div in the real
        // (unflattened) DOM -- it's a light-DOM child that lives one or more
        // levels up (on the records-record-layout-item host, or further if
        // that host itself sits at a shadow-root boundary), only visually
        // projected into the <slot> placeholder inside. Climb the real
        // parent chain (crossing shadow boundaries) and look there.
        //
        // Climbing broadens the search though, and can just as easily land
        // on a horizontally-adjacent field's value instead of this one's —
        // anchor on whatever field-label this specific container itself
        // belongs to (if it belongs to one at all) so a climbed candidate
        // only counts when it belongs to that same field.
        var ownLabel = _nearestFieldLabel(containers[i]);
        var node = containers[i];
        for (var depth = 0; depth < 3; depth++) {
            node = realParent(node);
            if (!node) break;
            var candidates = deepQueryAll('[slot="outputField"], [data-output-element-id="output-field"]', node);
            for (var k = 0; k < candidates.length; k++) {
                if (deepText(candidates[k]) && _valueBelongsToLabel(candidates[k], ownLabel)) return candidates[k];
            }
        }
    }
    return null;
}

function findValueElement(targetName) {
    return findValueElementIn(deepQueryAll("[data-target-selection-name='" + targetName + "']"));
}

// Some fields (e.g. Order Comments) don't have a stable/known API name to
// build a data-target-selection-name selector from, but every field's host
// <records-record-layout-item> carries a field-label attribute holding the
// exact label text shown on the page (confirmed live: field-label="Additional
// Support" wraps the "Additional Support" field) -- so look it up by that
// visible label instead of guessing the underlying API field name.
function findValueElementByLabel(labelText) {
    var hosts = deepQueryAll('records-record-layout-item[field-label]').filter(function(el) {
        return (el.getAttribute('field-label') || '').trim().toLowerCase() === labelText.toLowerCase();
    });
    return findValueDirectlyIn(hosts, labelText);
}

function fieldValue(targetName) {
    var el = findValueElement(targetName);
    return el ? deepText(el) : '';
}

function fieldValueByLabel(labelText) {
    var el = findValueElementByLabel(labelText);
    return el ? deepText(el) : '';
}

// Tries each label in order, returns the first one that actually finds a
// value — used where the exact field-label attribute text isn't known
// for certain (e.g. the Closed Date field's label wasn't confirmed
// against a live case, only "Date/Time Opened" was) so a couple of
// reasonable candidates are tried instead of hardcoding a guess that
// might not match this org's actual label.
function fieldValueByLabelAny(labels) {
    for (var i = 0; i < labels.length; i++) {
        var v = fieldValueByLabel(labels[i]);
        if (v) return v;
    }
    return '';
}

// deepText() walks child TEXT_NODEs, which doesn't reflect a live-edited
// <textarea>'s current text (that lives in .value, not as child text
// nodes) — needed for fields like "Solution Provided" that render as an
// actual editable lightning-textarea rather than a read-only output field.
// Falls back to grabbing the first .slds-textarea anywhere on the page in
// case this field doesn't follow the usual field-label wrapper pattern at
// all (an editable field may not be nested in a records-record-layout-item
// the way read-only display fields are).
function fieldValueByLabelTextarea(labelText) {
    var el = findValueElementByLabel(labelText);
    if (el) {
        if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') return (el.value || '').trim();
        var inner = deepQueryAll('textarea, input', el);
        if (inner.length) return (inner[0].value || '').trim();
        var txt = deepText(el);
        if (txt) return txt;
    }
    var textareas = deepQueryAll('textarea.slds-textarea');
    if (textareas.length) return (textareas[0].value || '').trim();
    return '';
}

function addressValue(targetName) {
    var el = findValueElement(targetName);
    if (!el) return '';
    var lines = deepQueryAll('.slds-truncate', el);
    if (lines.length) {
        var parts = lines.map(function(l) { return (l.textContent || '').trim(); }).filter(Boolean);
        if (parts.length) return parts.join(', ');
    }
    return deepText(el);
}

// Fallback for fields whose host doesn't carry a field-label attribute:
// match the visible <span class="test-id__field-label">Priority</span>,
// climb to its .test-id__output-root wrapper, and resolve the value from
// there (findValueElementIn already handles slotted/light-DOM values).
function findValueElementBySpanLabel(labelText) {
    var want = labelText.toLowerCase();
    var spans = deepQueryAll('span.test-id__field-label').filter(function(s) {
        return deepText(s).toLowerCase() === want;
    });
    for (var i = 0; i < spans.length; i++) {
        var node = spans[i];
        for (var depth = 0; depth < 6 && node; depth++) {
            if (node.classList && node.classList.contains('test-id__output-root')) break;
            node = realParent(node);
        }
        if (!node) continue;
        var found = findValueElementIn([node]);
        if (found) return found;
    }
    return null;
}

function findAnyByLabel(labelText) {
    return findValueElementByLabel(labelText) || findValueElementBySpanLabel(labelText);
}

function textByLabel(labelText) {
    var el = findAnyByLabel(labelText);
    return el ? deepText(el) : '';
}

// Lookup fields (User, Account...) render the name inside a link next to
// assistive "Preview" text — read just the link so that doesn't tag along.
function lookupByLabel(labelText) {
    var el = findAnyByLabel(labelText);
    if (!el) return '';
    var links = deepQueryAll('a', el);
    for (var i = 0; i < links.length; i++) {
        var t = deepText(links[i]);
        if (t) return t;
    }
    return deepText(el);
}

var matContainers = deepQueryAll("[data-target-selection-name='sfdc:RecordField.Account.MAT_ID__c']");
var matValueEls = matContainers.length ? deepQueryAll('.test-id__field-value', matContainers[0]) : [];

// Climb a few real (unflattened) ancestor levels so we can see the ground
// truth of what's actually around this field in the live DOM, instead of
// guessing based on how the DevTools inspector visually flattens slotted
// content.
var matAncestorHtml = '';
if (matContainers.length) {
    var anc = matContainers[0];
    for (var a = 0; a < 3; a++) {
        var up = realParent(anc);
        if (!up) break;
        anc = up;
    }
    matAncestorHtml = anc.outerHTML;
}

return {
    mat_id:  fieldValue("sfdc:RecordField.Account.MAT_ID__c"),
    address: addressValue("sfdc:RecordField.Account.ShippingAddress"),
    asset:   fieldValue("sfdc:RecordField.Case.AssetId"),
    subject: fieldValue("sfdc:RecordField.Case.Subject"),
    order_comments: fieldValueByLabel("Order Comments"),
    additional_support: fieldValueByLabel("Additional Support"),
    return_type: fieldValueByLabel("Return Type"),
    ticket_type: fieldValueByLabel("Ticket Type"),
    issue_type: fieldValueByLabel("Issue Type"),
    sub_issue_type: fieldValueByLabel("Sub-Issue Type"),
    chargeable: fieldValueByLabel("Is It Chargeable?"),
    order_status: fieldValueByLabel("Order Status"),
    sap_so: fieldValueByLabel("Sales Order(iTero/Webstore/Event/Cntrct)"),
    solution_provided: fieldValueByLabelTextarea("Solution Provided"),
    // Average Resolution Time (business hours) for the Escalations Report
    // — computed in Python from these two raw strings, see
    // _business_hours_between() in esc_report_sf_lookup.
    date_opened: fieldValueByLabel("Date/Time Opened") || textByLabel("Date/Time Opened"),
    date_closed: fieldValueByLabelAny(["Date/Time Closed", "Closed Date", "Date Closed"])
                 || textByLabel("Date/Time Closed"),
    // Excel-only (Escalations Report's Ticket Details section).
    priority: textByLabel("Priority") || fieldValue("sfdc:RecordField.Case.Priority"),
    internal_requestor: lookupByLabel("Internal Requestor"),
    // Escalations Report's Model column falls back to this editable field
    // (name="Serial_Number__c") when Asset doesn't carry a scanner S/N —
    // it's a plain <input>, not a field-label-wrapped output field, so
    // read it directly by its name attribute instead of going through
    // findValueElementByLabel.
    serial_number_field: (function() {
        var els = deepQueryAll('input[name="Serial_Number__c"]');
        return els.length ? (els[0].value || '').trim() : '';
    })(),
    debug_container_found: matContainers.length,
    debug_value_el_found: matValueEls.length,
    debug_raw_html: matAncestorHtml.slice(0, 4000)
};
"""


def _sf_search_all_frames(driver, script, max_depth=5):
    """Salesforce Console renders each record panel (Account, Case detail,
    etc.) inside its own nested <iframe> for isolation between Aura/LWC
    contexts. execute_script() only ever sees the top document, so a field
    that's genuinely present in the DOM (confirmed via the browser's own
    inspector) can still be invisible to us if it's one frame down. This
    walks every iframe in the frame tree, re-running the same extraction
    script inside each one, until a frame reports the field found."""
    from selenium.webdriver.common.by import By

    counters = {"frames_visited": 0}

    def search(depth):
        result = driver.execute_script(script) or {}
        if (result.get("mat_id") or "").strip():
            return result
        if depth >= max_depth:
            return result
        try:
            frames = driver.find_elements(By.TAG_NAME, "iframe") + driver.find_elements(By.TAG_NAME, "frame")
        except Exception:
            frames = []
        for fr in frames:
            try:
                driver.switch_to.frame(fr)
            except Exception:
                continue
            counters["frames_visited"] += 1
            try:
                sub = search(depth + 1)
            except Exception:
                sub = {}
            driver.switch_to.parent_frame()
            if (sub.get("mat_id") or "").strip():
                return sub
        return result

    driver.switch_to.default_content()
    try:
        result = search(0)
        result["_frames_visited"] = counters["frames_visited"]
        return result
    finally:
        driver.switch_to.default_content()


def sf_read_ticket():
    """Read key fields off the currently-open Salesforce ticket (Case) page.

    Built field-by-field against exact HTML confirmed on the live page
    (data-target-selection-name -> .test-id__field-value, or field-label
    for fields without a known API name), instead of guessing selectors."""
    global _sf_driver
    if _sf_driver is None:
        return err("No Salesforce window is open. Open a ticket first.")

    driver = _sf_driver
    data = {}
    try:
        for attempt in range(4):
            data = _sf_search_all_frames(driver, _SF_DEEP_EXTRACT_JS) or {}
            if (data.get("mat_id") or "").strip():
                break
            time.sleep(1.0 + attempt * 0.5)
    except Exception as e:
        _sf_drop_driver_if_connection_dead(e)
        return err(f"Lost the Salesforce browser session (it may have crashed). "
                   f"Try again — it will reopen automatically. Details: {e}")

    mat_id             = (data.get("mat_id") or "").strip()
    address            = (data.get("address") or "").strip()
    asset              = (data.get("asset") or "").strip()
    subject            = (data.get("subject") or "").strip()
    order_comments     = (data.get("order_comments") or "").strip()
    additional_support = (data.get("additional_support") or "").strip()
    return_type        = (data.get("return_type") or "").strip()
    ticket_type        = (data.get("ticket_type") or "").strip()
    issue_type         = (data.get("issue_type") or "").strip()
    sub_issue_type     = (data.get("sub_issue_type") or "").strip()
    chargeable         = (data.get("chargeable") or "").strip()
    order_status       = (data.get("order_status") or "").strip()
    sap_so             = (data.get("sap_so") or "").strip()

    # Asset text carries an internal record prefix before the actual
    # scanner S/N (e.g. "Preview223167-YUC2022W18A103-SCANNER") — drop
    # everything before the S/N and keep the rest of the string as-is.
    if asset:
        sn_match = _SN_REGEX.search(asset.upper())
        if sn_match:
            asset = asset[sn_match.start():]

    result = {
        "mat_id":             mat_id or "Empty",
        "address":            address or "Empty",
        "asset":              asset or "Empty",
        "asset_source":       "asset" if asset else "",
        "subject":            subject or "Empty",
        "order_comments":     order_comments or "Empty",
        "additional_support": additional_support or "Empty",
        "return_type":        return_type or "Empty",
        "ticket_type":        ticket_type or "Empty",
        "issue_type":         issue_type or "Empty",
        "sub_issue_type":     sub_issue_type or "Empty",
        "chargeable":         chargeable or "Empty",
        # Left raw (not defaulted to "Empty") — the frontend hides these two
        # entirely when blank instead of displaying a placeholder.
        "order_status":       order_status,
        "sap_so":             sap_so,
        "mail_sent":          _sf_mail_sent,
    }

    if not _sf_mail_sent:
        result["mail_debug"] = _sf_mail_debug

    if not mat_id:
        try:
            cur_url = driver.current_url
            cur_title = driver.title
            n_handles = len(driver.window_handles)
        except Exception as e:
            cur_url, cur_title, n_handles = f"<error: {e}>", "", 0

        result["debug_container_found"] = data.get("debug_container_found", 0)
        result["debug_value_el_found"] = data.get("debug_value_el_found", 0)
        result["debug_raw_html"] = data.get("debug_raw_html", "")
        result["debug_frames_visited"] = data.get("_frames_visited", 0)
        result["debug_url"] = cur_url
        result["debug_title"] = cur_title
        result["debug_handles"] = n_handles
        _sf_close_if_headless()
        return ok(result, msg="MAT ID not found — see debug box.")

    _sf_close_if_headless()
    return ok(result)


# Fixed keyword templates the agent's Solution Provided text always
# contains one of (at the start or somewhere in a line) — these are what
# actually categorize the outcome, not the verbose free text around them.
_ESC_REPORT_SOLUTION_TEMPLATES = [
    "Part Replacement – PPC",
    "Part Replacement – Wand",
    "Part Replacement – PPC & Wand",
    "Part Replacement – DOA",
    "Part Replacement – Wheelstand",
    "Part Replacement – Cable",
    "Part Replacement – HUB",
    "Part Replacement – Batteries",
    "Network Troubleshooting",
    "Cleanup",
    "Manual Registration",
    "No Response from Customer",
    "CTL",
    "Workaround",
    "Added to Jira",
    "Resolved on Jira",
    "Scanner Updated",
    "Reinstallation",
    "EFRA",
    "Clean Install",
    "FTI Reinstallation",
    "Information Shared with the office",
    "Information Shared with IL",
    "Report Done",
    "No Escalations scope",
]


def _esc_report_normalize(text):
    # Salesforce's actual text may use a plain hyphen instead of the
    # en dash ("–") the templates are written with — normalize both sides
    # to a plain "-" before comparing so that difference never causes a
    # miss, along with collapsing any run of whitespace.
    text = (text or "").lower().replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", text).strip()


def _esc_report_match_solution_template(solution_text):
    """Scans the Solution Provided text left to right and returns whichever
    template appears earliest — "stop reading at the first one you find".
    None of the 21 templates present -> None (caller falls back to the raw
    scraped text)."""
    haystack = _esc_report_normalize(solution_text)
    if not haystack:
        return None
    best_pos, best_len, best_template = None, 0, None
    for template in _ESC_REPORT_SOLUTION_TEMPLATES:
        norm = _esc_report_normalize(template)
        pos = haystack.find(norm)
        if pos == -1:
            continue
        # Earlier position wins; on a tie (e.g. "Part Replacement – PPC"
        # and "Part Replacement – PPC & Wand" both matching at position 0)
        # prefer the longer, more specific template instead of whichever
        # happens to come first in the list.
        if best_pos is None or pos < best_pos or (pos == best_pos and len(norm) > best_len):
            best_pos, best_len, best_template = pos, len(norm), template
    return best_template


# Salesforce renders "Date/Time Opened"/"Closed Date" as something like
# "9/16/2026, 11:48 AM" under the org's own locale — a handful of the
# most common variants (12h with/without a leading zero on the hour, 24h)
# are tried in order rather than assuming exactly one format.
_SF_DATETIME_FORMATS = (
    "%m/%d/%Y, %I:%M %p",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y, %H:%M",
    "%m/%d/%Y %H:%M",
)

_BIZ_HOUR_START = 8   # 8 AM
_BIZ_HOUR_END   = 17  # 5 PM


def _parse_sf_datetime(text):
    text = (text or "").strip()
    if not text:
        return None
    for fmt in _SF_DATETIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _business_hours_between(start, end):
    """Hours elapsed between two datetimes, counting only Mon-Fri, 8 AM-5
    PM — walks day by day between start and end, summing however much of
    each day's business window actually falls inside [start, end], and
    skipping weekends outright. Used for the Escalations Report's Average
    Resolution Time figure, since a ticket sitting untouched over a
    weekend or overnight shouldn't count as fast as it would clocking
    the same wall-clock hours during business hours.
    """
    if not start or not end or end <= start:
        return 0.0
    total = timedelta()
    day = start.date()
    while day <= end.date():
        if day.weekday() < 5:  # Monday=0 .. Friday=4
            day_start = datetime.combine(day, dt_time(_BIZ_HOUR_START, 0))
            day_end   = datetime.combine(day, dt_time(_BIZ_HOUR_END, 0))
            window_start = max(day_start, start)
            window_end   = min(day_end, end)
            if window_end > window_start:
                total += window_end - window_start
        day += timedelta(days=1)
    return round(total.total_seconds() / 3600.0, 2)


def esc_report_sf_lookup(ticket_number, close_after=True):
    """Escalations Report tab's lupa button — a narrower version of the
    Ticket Checker flow. Opens the ticket itself (unlike sf_read_ticket,
    which needs it already open) and pulls only Categorization
    (Ticket/Issue/Sub-Issue Type, same fields Ticket Checker already
    shows) and Solution Provided.

    close_after=False lets Find All keep reusing the same browser across
    a whole batch instead of quitting and relaunching Edge once per
    ticket — the frontend closes it itself (unconditionally, via
    sf_close_browser) exactly once when the batch actually ends.
    """
    ticket_number = (ticket_number or "").strip()
    if not ticket_number:
        return err("Enter a ticket number.")

    try:
        open_data = json.loads(sf_open_ticket(ticket_number))
    except Exception as e:
        return err(f"Could not open the ticket: {e}")

    if open_data.get("status") != "ok" or (open_data.get("data") or {}).get("status_text") != "opened":
        # Bubble up login_required / no_case_match / error as-is so the
        # frontend can show the same messaging Ticket Checker already does.
        return json.dumps(open_data)

    global _sf_driver
    if _sf_driver is None:
        return err("Salesforce window closed unexpectedly.")

    driver = _sf_driver
    data = {}
    try:
        for attempt in range(4):
            data = _sf_search_all_frames(driver, _SF_DEEP_EXTRACT_JS) or {}
            if (data.get("ticket_type") or "").strip() or (data.get("solution_provided") or "").strip():
                break
            time.sleep(1.0 + attempt * 0.5)
    except Exception as e:
        _sf_drop_driver_if_connection_dead(e)
        return err(f"Lost the Salesforce browser session (it may have crashed). "
                   f"Try again — it will reopen automatically. Details: {e}")

    ticket_type    = (data.get("ticket_type") or "").strip()
    issue_type     = (data.get("issue_type") or "").strip()
    sub_issue_type = (data.get("sub_issue_type") or "").strip()
    solution_raw   = (data.get("solution_provided") or "").strip()
    asset          = (data.get("asset") or "").strip()
    serial_field   = (data.get("serial_number_field") or "").strip()

    categorization_parts = [p for p in (ticket_type, issue_type, sub_issue_type) if p]
    categorization = " / ".join(categorization_parts) if categorization_parts else "Empty"

    # The agent's Solution Provided text always contains one of the fixed
    # keyword templates somewhere — that's what categorizes the outcome,
    # not the verbose text around it. Falls back to the raw scraped text
    # if none of the templates show up.
    matched = _esc_report_match_solution_template(solution_raw)
    solution = matched or solution_raw

    # Model comes from whichever of Asset / Serial_Number__c actually
    # holds a recognizable scanner S/N — Asset first (same field/pattern
    # Ticket Checker already trusts for its own S/N check), Serial_Number__c
    # as the fallback for tickets where Asset wasn't populated. The
    # frontend turns this raw S/N into an actual model name (it already
    # owns the prefix table); neither found here means no scanner at all,
    # which the frontend reports as "Office PC/other".
    scanner_sn = ""
    for candidate in (asset.upper(), serial_field.upper()):
        m = _SN_REGEX.search(candidate)
        if m:
            # Just the matched S/N itself — not m.start() to end-of-string,
            # which was also dragging along whatever trailing text Asset
            # has after it (e.g. "...A103-SCANNER").
            scanner_sn = m.group(0)
            break

    # Customer Satisfaction sub-issue type means the unit shipped under a
    # special approval — flagged plainly as its own column.
    csat = "YES" if sub_issue_type.lower() == "customer satisfaction" else "NO"

    # Average Resolution Time (business hours) — Mon-Fri 8 AM-5 PM only,
    # so a ticket sitting untouched over a weekend/overnight isn't counted
    # as if it were being actively worked that whole time. Silently 0 (not
    # an error) when either date is missing or fails to parse — a ticket
    # missing this shouldn't block the rest of the lookup from succeeding.
    date_opened = _parse_sf_datetime(data.get("date_opened"))
    date_closed = _parse_sf_datetime(data.get("date_closed"))
    resolution_business_hours = _business_hours_between(date_opened, date_closed)

    # Calendar days from opened to closed (weekends included, unlike the
    # business-hours figure above) — blank while still open or unreadable.
    days_open = ""
    if date_opened and date_closed:
        days_open = (date_closed.date() - date_opened.date()).days

    if close_after:
        _sf_close_if_headless()
    return ok({
        "categorization": categorization,
        # Also broken out individually (not just the joined string above) —
        # the Excel export's per-field statistics need to tally each one
        # on its own.
        "ticket_type": ticket_type,
        "issue_type": issue_type,
        "sub_issue_type": sub_issue_type,
        "solution": solution or "Empty",
        "scanner_sn": scanner_sn,
        "csat": csat,
        "resolution_business_hours": resolution_business_hours,
        "priority": (data.get("priority") or "").strip(),
        "internal_requestor": (data.get("internal_requestor") or "").strip(),
        "date_opened": (data.get("date_opened") or "").strip(),
        "date_closed": (data.get("date_closed") or "").strip(),
        "days_open": days_open,
    })


def _sf_close_if_headless():
    """Quit the Salesforce driver right after we've pulled what we need out
    of it. The SSO session lives in the persisted profile on disk (not in
    the running process), so this loses nothing — but leaving the process
    running between checks is exactly what turned into the orphaned,
    profile-locking msedge.exe instances that kept crashing every later
    launch. Skipped when "Show browser" is on, since then the technician
    is presumably looking at the window and closing it out from under them
    would be surprising."""
    global _sf_driver
    show_browser = False
    try:
        if os.path.exists(_SF_CFG_PATH):
            with open(_SF_CFG_PATH, encoding="utf-8") as f:
                show_browser = bool(json.load(f).get("show_browser", False))
    except Exception:
        pass
    if show_browser or _sf_driver is None:
        return
    try:
        _sf_driver.quit()
    except Exception:
        pass
    _sf_driver = None


def sf_close_browser():
    global _sf_driver
    if _sf_driver is not None:
        try:
            _sf_driver.quit()
        except Exception:
            pass
        _sf_driver = None
    return ok(None, msg="Salesforce window closed.")


def sf_logout():
    """A real logout, unlike sf_close_browser() (which only closes the
    window and leaves the SSO session cookie on disk for next time): quits
    the driver, wipes the persisted profile so the saved session is
    actually gone, and flags the next Salesforce call to launch visibly —
    the freshly logged-out account needs a human to redo corporate SSO
    once; every call after that reuses the newly saved session and goes
    back to the normal show_browser setting, headless or not."""
    global _sf_driver
    if _sf_driver is not None:
        try:
            _sf_driver.quit()
        except Exception:
            pass
        _sf_driver = None

    import shutil
    try:
        shutil.rmtree(_SF_PROFILE_DIR, ignore_errors=True)
    except Exception:
        pass

    try:
        cfg = {}
        if os.path.exists(_SF_CFG_PATH):
            with open(_SF_CFG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
        cfg["force_visible_once"] = True
        os.makedirs(os.path.dirname(_SF_CFG_PATH), exist_ok=True)
        with open(_SF_CFG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    except Exception:
        pass

    return ok(None, msg="Logged out of Salesforce.")
