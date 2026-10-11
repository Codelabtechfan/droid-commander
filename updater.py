"""Update checker for Droid Commander. Never touches %APPDATA% save data; only replaces the .exe file."""
import json, os, re, subprocess, sys, tempfile, threading, urllib.request

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
            tmp = os.path.join(tempfile.gettempdir(), "DroidCommander_update.exe")
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
            self.bat = write_swap_script(tmp, exe, os.getpid())
            self.status = "ready"
        except Exception as e:
            self.status, self.error = "error", str(e)

    def restart_into_update(self):
        """Launch the helper (it waits for us to exit, swaps the exe, relaunches). Caller must then quit."""
        subprocess.Popen(["cmd", "/c", self.bat], creationflags=0x08000000 | 0x00000008, close_fds=True)


def write_swap_script(new_exe, target_exe, pid):
    bat = os.path.join(tempfile.gettempdir(), "droidcommander_update.bat")
    with open(bat, "w") as f:
        f.write('@echo off\r\n'
                ':wait\r\n'
                'tasklist /FI "PID eq %d" 2>nul | find "%d" >nul && (timeout /t 1 /nobreak >nul & goto wait)\r\n'
                'set n=0\r\n'
                ':swap\r\n'
                'move /y "%s" "%s" >nul 2>&1\r\n'
                'if errorlevel 1 (set /a n+=1 & timeout /t 1 /nobreak >nul & if %%n%% lss 15 goto swap)\r\n'
                'start "" "%s"\r\n'
                'del "%%~f0"\r\n' % (pid, pid, new_exe, target_exe, target_exe))
    return bat
