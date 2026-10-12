"""Window modes (Windowed / Full window / Fullscreen) + scaling of the fixed-size UI canvas to any window size."""
import json, os, sys

MODES = ["Windowed", "Full window", "Fullscreen"]
BASE = (1180, 720)


def enable_dpi_awareness():
    """Stop Windows from blurry-stretching the window on high-DPI screens."""
    if os.name != "nt":
        return False
    try:
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            ctypes.windll.user32.SetProcessDPIAware()
        return True
    except Exception:
        return False


def fit(win, base=BASE):
    """Letterbox: returns (scale, (offset_x, offset_y), (scaled_w, scaled_h))."""
    w, h = max(1, win[0]), max(1, win[1])
    s = min(w / base[0], h / base[1])
    sw, sh = int(base[0] * s), int(base[1] * s)
    return s, ((w - sw) // 2, (h - sh) // 2), (sw, sh)


def to_canvas(pos, win, base=BASE):
    s, (ox, oy), _ = fit(win, base)
    return (int((pos[0] - ox) / s), int((pos[1] - oy) / s))


class Settings:
    def __init__(self, path):
        self.path = path
        self.display = "Windowed"
        self.window_size = list(BASE)
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            if d.get("display") in MODES:
                self.display = d["display"]
            ws = d.get("window_size")
            if isinstance(ws, list) and len(ws) == 2 and all(isinstance(v, int) and 320 <= v <= 10000 for v in ws):
                self.window_size = ws
        except Exception:
            pass

    def save(self):
        try:
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                json.dump({"display": self.display, "window_size": self.window_size}, f)
            os.replace(self.path + ".tmp", self.path)
        except Exception:
            pass


def next_mode(cur):
    return MODES[(MODES.index(cur) + 1) % len(MODES)] if cur in MODES else MODES[0]


def apply_mode(pygame, mode, window_size):
    """Create the window for a mode. The display subsystem is fully restarted first, because switching flags
    on an existing SDL window (esp. leaving fullscreen) can crash on Windows. Falls back to Windowed."""
    try:
        return _apply(pygame, mode, window_size)
    except Exception:
        _log_exc("display mode %s failed" % mode)
        try:
            return _apply(pygame, "Windowed", list(BASE))
        except Exception:
            _log_exc("windowed fallback failed")
            pygame.display.init()
            return pygame.display.set_mode(BASE)


def _apply(pygame, mode, window_size):
    pygame.display.quit()
    for k in ("SDL_VIDEO_WINDOW_POS", "SDL_VIDEO_CENTERED"):
        os.environ.pop(k, None)
    if mode == "Full window":
        os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
    elif mode == "Windowed":
        os.environ["SDL_VIDEO_CENTERED"] = "1"
    pygame.display.init()
    try:
        desk = pygame.display.get_desktop_sizes()[0]
    except Exception:
        desk = BASE
    if mode == "Fullscreen":
        win = pygame.display.set_mode(desk, pygame.FULLSCREEN)
    elif mode == "Full window":
        win = pygame.display.set_mode(desk, pygame.NOFRAME)
    else:
        size = (max(480, min(window_size[0], desk[0])), max(300, min(window_size[1], desk[1] - 60)))
        win = pygame.display.set_mode(size, pygame.RESIZABLE)
    try:
        from droid_commander import APP, VERSION
        pygame.display.set_caption("%s %s" % (APP, VERSION))
    except Exception:
        pass
    return win


def _log_exc(msg):
    try:
        import traceback
        from droid_commander import log
        log(msg + ": " + traceback.format_exc())
    except Exception:
        pass
