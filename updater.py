"""Update checker for Droid Commander. Never touches %APPDATA% save data; only replaces the .exe file."""
import json, ntpath, os, re, subprocess, sys, tempfile, threading, urllib.request

REPO = "Codelabtechfan/droid-commander"
API = "https://api.github.com/repos/%s/releases/latest" % REPO
ASSET = "DroidCommander.exe"


def parse_version(v):
    nums = re.findall(r"\d+", v or "")[:3]
    return tuple(int(n) for n in nums) + (0,) * (3 - len(nums))


def is_newer(remote, local):
    return parse_version(remote) > parse_version(local)


def pick_asset(assets):
    """Choose the exe download from a release's asset list."""
    exes = [a for a in assets or [] if a.get("name", "").lower().endswith(".exe")]
    for a in exes:
        if a["name"].lower() == ASSET.lower():
            return a
    return exes[0] if exes else None


class Updater:
    def __init__(self, current):
        self.current = current
        self.status = "idle"  # idle, checking, uptodate, available, offline, downloading, ready, error
        self.latest = None
        self.asset = None
        self.url = None
        self.progress = 0.0
        self.error = ""
        self.dismissed = False

    def check(self):
        if self.status in ("checking", "downloading"):
            return
        self.status = "checking"; self.dismissed = False
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            req = urllib.request.Request(API, headers={"Accept": "application/vnd.github+json", "User-Agent": "DroidCommander"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.load(r)
            self.latest = data.get("tag_name", "")
            self.url = data.get("html_url")
            self.asset = pick_asset(data.get("assets"))
            self.status = "available" if is_newer(self.latest, self.current) and self.asset else "uptodate"
        except Exception as e:
            self.status, self.error = "offline", str(e)

    def can_self_update(self):
        return getattr(sys, "frozen", False) and os.name == "nt"

    def update_now(self):
        if not self.asset or self.status == "downloading":
            return
        if not self.can_self_update():
            import webbrowser
            webbrowser.open(self.url or "https://github.com/%s/releases" % REPO); return
        self.status, self.progress = "downloading", 0.0
        threading.Thread(target=self._download, daemon=True).start()

    def _download(self):
        try:
            exe = os.path.abspath(sys.executable)
            tmp = os.path.join(tempfile.gettempdir(), "DroidCommander_update_%s.exe" % re.sub(r"[^0-9.]", "", self.latest or "new"))
            req = urllib.request.Request(self.asset["browser_download_url"], headers={"User-Agent": "DroidCommander"})
            with urllib.request.urlopen(req, timeout=30) as r, open(tmp, "wb") as f:
                total = int(r.headers.get("Content-Length") or self.asset.get("size") or 0)
                done = 0
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    f.write(chunk); done += len(chunk)
                    if total:
                        self.progress = done / total
            if total and os.path.getsize(tmp) != total:
                raise IOError("download incomplete")
            self.bat = write_swap_script(tmp, exe, sorted({os.getpid(), os.getppid()}), self.latest)
            self.status = "ready"
        except Exception as e:
            self.status, self.error = "error", str(e)

    def restart_into_update(self):
        """Launch the helper (it waits for us to exit, swaps the exe, relaunches). Caller must then quit."""
        subprocess.Popen(["cmd", "/c", self.bat], creationflags=0x08000000 | 0x00000200, close_fds=True,
                         cwd=tempfile.gettempdir(), env=clean_env())


def clean_env(env=None):
    """Environment without PyInstaller's onefile vars / old _MEI paths, so the relaunched exe extracts afresh."""
    env = dict(os.environ if env is None else env)
    for k in list(env):
        ku = k.upper()
        if ku.startswith("_PYI") or ku.startswith("_MEI") or ku in ("_MEIPASS2", "TCL_LIBRARY", "TK_LIBRARY"):
            del env[k]
    for k in list(env):
        if k.upper() == "PATH":
            env[k] = ";".join(p for p in env[k].split(";") if "_MEI" not in p)
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env


LOG_NAME = "DroidCommanderUpdate.log"


def log_path():
    return os.path.join(tempfile.gettempdir(), LOG_NAME)


def write_swap_script(new_exe, target_exe, pids, version="?"):
    """Batch helper. Waits for ALL our processes (PyInstaller onefile runs a bootloader parent + python child),
    then swaps the exe with retries for up to ~60 s. Uses ping for delays because 'timeout' fails without a console.
    On failure it copies the new exe next to the old one as DroidCommander-new.exe. Logs to %TEMP%."""
    if isinstance(pids, int):
        pids = [pids]
    d = ntpath.dirname(target_exe)
    fallback = ntpath.join(d, "DroidCommander-new.exe")
    old = target_exe + ".old"
    lines = ['@echo off', 'setlocal EnableDelayedExpansion', 'set "LOG=%s"' % log_path(),
             'echo START %s>"%%LOG%%"' % version, 'set n=0', ':wait']
    for p in pids:
        lines.append('tasklist /FI "PID eq %d" /NH /FO CSV 2>nul | findstr /c:"\\"%d\\"" >nul && goto sleep' % (p, p))
    lines += ['echo all processes gone>>"%LOG%"', 'ping -n 3 127.0.0.1 >nul', 'goto swap', ':sleep', 'set /a n+=1', 'if !n! geq 90 goto swap', 'ping -n 2 127.0.0.1 >nul', 'goto wait',
              ':swap', 'echo processes gone after !n!s>>"%LOG%"', 'set m=0', 'if exist "%s" del /f /q "%s" >nul 2>&1' % (old, old),
              ':tryold', 'move /y "%s" "%s" >nul 2>&1' % (target_exe, old), 'if not errorlevel 1 goto trynew',
              'set /a m+=1', 'if !m! geq 60 goto fail', 'ping -n 2 127.0.0.1 >nul', 'goto tryold',
              ':trynew', 'move /y "%s" "%s" >nul 2>&1' % (new_exe, target_exe), 'if not errorlevel 1 goto ok',
              'move /y "%s" "%s" >nul 2>&1' % (old, target_exe), 'goto fail',
              ':ok', 'del /f /q "%s" >nul 2>&1' % old, 'echo OK %s>>"%%LOG%%"' % version, 'goto launch',
              ':fail', 'copy /y "%s" "%s" >nul 2>&1' % (new_exe, fallback), 'echo FAILED %s "%s">>"%%LOG%%"' % (version, fallback),
              ':launch', 'ping -n 3 127.0.0.1 >nul',
              'for /f "delims==" %%V in (\'set _PYI 2^>nul\') do set "%%V="',
              'for /f "delims==" %%V in (\'set _MEI 2^>nul\') do set "%%V="',
              'set "PYINSTALLER_RESET_ENVIRONMENT=1"', 'cd /d "%s"' % d, 'start "" "%s"' % target_exe, '(goto) 2>nul & del "%~f0"']
    bat = os.path.join(tempfile.gettempdir(), "droidcommander_update.bat")
    with open(bat, "w") as f:
        f.write("\r\n".join(lines) + "\r\n")
    return bat


def read_last_result(current_version, path=None):
    """Called on startup. Returns a message for the user (or None) and removes the log."""
    path = path or log_path()
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            txt = f.read()
    except Exception:
        return None
    try:
        os.remove(path)
    except Exception:
        pass
    m = re.search(r"^(OK|FAILED) (\S+)(?: \"(.*)\")?", txt, re.M)
    if not m:
        return "The last update didn't finish. Please try Update now again."
    kind, ver, fb = m.groups()
    if kind == "FAILED":
        return "Update couldn't replace the app. The new version was saved as %s - run that file instead." % (fb or "DroidCommander-new.exe")
    if parse_version(ver) != parse_version(current_version):
        return "Update to %s was installed but you're still on v%s. Close all copies of the app and reopen it." % (ver, current_version)
    return "Updated to v%s!" % current_version


def cleanup_old():
    if getattr(sys, "frozen", False):
        try:
            os.remove(sys.executable + ".old")
        except Exception:
            pass
