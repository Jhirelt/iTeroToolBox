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
import winreg
import socket
import threading
from datetime import datetime
from pathlib import Path


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


def _run_elevated(cmd, wait=True):
    """
    Run a command elevated (ShellExecute runas).
    For commands that need UAC even when already admin.
    """
    try:
        import win32api
        import win32con
        ret = win32api.ShellExecute(
            0, "runas", "cmd.exe",
            f'/c "{cmd}"', None, win32con.SW_HIDE if not wait else win32con.SW_SHOW
        )
        return str(ret), "", 0
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
    out, stderr, rc = _run(f"ping -n 4 {target}")
    return ok(out) if rc == 0 else err(out or stderr)


def get_wifi_details():
    out, stderr, rc = _run("netsh wlan show interfaces")
    return ok(out) if rc == 0 else err(stderr)


def get_network_details():
    """Return structured network info for Transfer Service panel."""
    out, _, _ = _run("ipconfig /all")
    data = {
        "ssid": "", "mac": "", "ipv4": "", "subnet": "",
        "gateway": "", "dhcp": "", "dns": "", "dhcp_enabled": ""
    }
    # Parse relevant fields
    lines = out.splitlines()
    in_wifi = False
    for line in lines:
        l = line.lower()
        if "wireless" in l or "wi-fi" in l or "wlan" in l:
            in_wifi = True
        if in_wifi:
            if "physical address" in l:
                data["mac"] = line.split(":")[-1].strip() if ":" in line else ""
            elif "ipv4 address" in l and not data["ipv4"]:
                data["ipv4"] = re.sub(r"\(.*\)", "", line.split(":")[-1]).strip()
            elif "subnet mask" in l:
                data["subnet"] = line.split(":")[-1].strip()
            elif "default gateway" in l:
                data["gateway"] = line.split(":")[-1].strip()
            elif "dhcp server" in l:
                data["dhcp"] = line.split(":")[-1].strip()
            elif "dhcp enabled" in l:
                data["dhcp_enabled"] = line.split(":")[-1].strip()
            elif "dns servers" in l:
                data["dns"] = line.split(":")[-1].strip()
    # SSID
    wifi_out, _, _ = _run("netsh wlan show interfaces")
    for line in wifi_out.splitlines():
        if "ssid" in line.lower() and "bssid" not in line.lower():
            data["ssid"] = line.split(":")[-1].strip()
            break
    return ok(data)


def disable_ipv6():
    out, stderr, rc = _run("netsh int ipv6 set state disabled")
    if rc == 0:
        return ok("IPv6 disabled successfully")
    return err(stderr or out)


def flush_dns():
    out, stderr, rc = _run("ipconfig /flushdns")
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
# SERVICES
# ─────────────────────────────────────────────

def check_service(name):
    out, stderr, rc = _run(f"sc query {name}")
    if "RUNNING" in out:
        status = "running"
    elif "STOPPED" in out:
        status = "stopped"
    elif "does not exist" in out.lower() or rc != 0:
        status = "missing"
    else:
        status = "unknown"
    return ok({"name": name, "status": status, "raw": out})


def set_service_auto_start(name):
    out1, _, rc1 = _run(f"sc config {name} start= auto")
    out2, _, rc2 = _run(f"sc start {name}")
    if rc1 == 0:
        return ok(f"Service {name} set to Automatic. Start result: {out2}")
    return err(f"Failed to configure service: {out1}")


# ─────────────────────────────────────────────
# REGISTRY
# ─────────────────────────────────────────────

def query_registry(key_path):
    """Query a registry key and return its values."""
    out, stderr, rc = _run(f'reg query "{key_path}"')
    return ok(out) if rc == 0 else err(stderr or out)


def set_registry_value(key_path, value_name, value_data, value_type="REG_BINARY"):
    out, stderr, rc = _run(
        f'reg add "{key_path}" /v "{value_name}" /t {value_type} /d "{value_data}" /f'
    )
    return ok(out) if rc == 0 else err(stderr or out)


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


def kill_process(process_name):
    out, _, rc = _run(f'taskkill /F /IM "{process_name}"')
    return ok(out) if "SUCCESS" in out or rc == 0 else err(out)


# ─────────────────────────────────────────────
# CLEAN INSTALL
# ─────────────────────────────────────────────

def rename_cadent_folders():
    cmd = (
        'powershell -NoProfile -ExecutionPolicy Bypass -Command '
        '"$paths=@(\'C:\\Program Files\\Cadent\','
        '\'C:\\Program Files (x86)\\Cadent\','
        '\'C:\\ProgramData\\Cadent\');'
        'foreach($p in $paths){'
        '  if(Test-Path $p){'
        '    $parent=Split-Path $p;'
        '    $new=Join-Path $parent \'Cadent_old\';'
        '    Rename-Item -Path $p -NewName \'Cadent_old\' -Force -ErrorAction SilentlyContinue;'
        '    Write-Host \'Renamed: \' $p'
        '  } else { Write-Host \'Not found: \' $p }'
        '}"'
    )
    out, stderr, rc = _run(cmd, timeout=60)
    return ok(out) if rc == 0 else err(stderr or out)


def clean_registry():
    keys = [
        (r"HKLM\SOFTWARE\Cadent", "iTeroPackageVersion"),
        (r"HKLM\SOFTWARE\Cadent", "TensorCUDA"),
        (r"HKLM\SOFTWARE\Cadent", "BiosUpdate"),
        (r"HKLM\SOFTWARE\Cadent", "DotNetVersion"),
        (r"HKLM\SOFTWARE\Cadent\ElementDemoDB", "Version"),
        (r"HKLM\SOFTWARE\Cadent\AngieDemoDB", "Version"),
    ]
    results = []
    for path, name in keys:
        out, _, rc = _run(f'reg delete "{path}" /v "{name}" /f')
        results.append(f"{'OK' if rc == 0 else 'Skip'}: {path}\\{name}")
    return ok("\n".join(results))


def remove_leftover_files():
    cmds = [
        r'del "C:\ProgramData\Cadent\iTero\RxData.sqlite" /f /q',
        r'del "C:\ProgramData\Cadent\Config\cadent_ini.dll" /f /q',
        r'del "C:\ProgramData\Cadent\Config\RxManagerConfig.ini.dll" /f /q',
    ]
    results = []
    for cmd in cmds:
        out, _, rc = _run(cmd)
        results.append(f"{'OK' if rc == 0 else 'Skip/NF'}: {cmd.split(chr(34))[1]}")
    return ok("\n".join(results))


# ─────────────────────────────────────────────
# TRANSFER SERVICE / FOLDER
# ─────────────────────────────────────────────

def verify_export_folder():
    path = r"C:\itero\export"
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
        return ok(f"Created {path}")
    return ok(f"Exists: {path}")


def share_export_folder():
    out, stderr, rc = _run(
        r'net share export="C:\itero\export" /GRANT:Everyone,FULL'
    )
    return ok(out) if rc == 0 else err(stderr or out)


def disable_password_sharing():
    out, stderr, rc = _run(
        r'reg add "HKLM\SYSTEM\CurrentControlSet\Control\Lsa" '
        r'/v "restrictanonymous" /t REG_DWORD /d 0 /f'
    )
    return ok(out) if rc == 0 else err(stderr)


# ─────────────────────────────────────────────
# SYSTEM TOOLS
# ─────────────────────────────────────────────

def open_device_manager():
    subprocess.Popen(["devmgmt.msc"], shell=True)
    return ok("Device Manager opened")


def open_event_viewer():
    subprocess.Popen(["eventvwr.msc"], shell=True)
    return ok("Event Viewer opened")


def open_services():
    subprocess.Popen(["services.msc"], shell=True)
    return ok("Services opened")


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

    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent

    src = base / "wand_reference_WOA.png"
    dest_dir = Path(r"C:\iTeroToolbox\Reference\WOA")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "wand_reference_WOA.png"

    if not src.exists():
        alt = Path(__file__).parent / "wand_reference_WOA.png"
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
    config = {
        'yucblx': (r'C:\iTeroToolbox\Reference\YUC_BLX', 'wand_reference_YUC_BLX.png'),
        'lumina':  (r'C:\iTeroToolbox\Reference\Lumina',  'wand_reference_LUMINA.png'),
        'woa':     (r'C:\iTeroToolbox\Reference\WOA',     'wand_reference_WOA.png'),
    }
    if collage_type not in config:
        return err(f'Unknown collage type: {collage_type}')
    folder, fname = config[collage_type]
    dest = Path(folder) / fname
    # If not in Reference subfolder, fall back to app dir
    if not dest.exists():
        alt = Path(__file__).parent / fname
        if alt.exists():
            # Copy to correct subfolder
            import shutil
            Path(folder).mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(alt), str(dest))
        else:
            return err(f'Collage not found: {fname}. Place PNG in {folder}\\')
    subprocess.Popen(f'explorer /select,"{dest}"', shell=True)
    return ok({'path': str(dest), 'msg': f'Explorer opened -> {dest}'})


def get_catalog_parts(model=""):
    """Return list of parts from C:\\iTeroToolbox\\Catalog\\ as base64-encoded images."""
    import base64
    catalog_dir = Path(r"C:\iTeroToolbox\Catalog")
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


def fetch_sf_case_title(url=""):
    """Extract case ID from SF URL — title requires authenticated browser session."""
    if not url:
        return err("No URL provided")
    m = re.search(r'/([0-9]{8,18})', url)
    case_id = m.group(1) if m else ""
    # Salesforce requires an authenticated browser session — cannot fetch title server-side.
    return err(f"Salesforce requires login — fill title manually.{(' Case ID: ' + case_id) if case_id else ''}")


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
