"""Keybinds: action -> keyboard key (+ optional 2nd key) and controller button. Saved to keybinds.json."""
import json, os

DEFAULTS = {  # action: [label, key, key2, pad_button]
    "up": ["Drive forward", "w", "up", None], "down": ["Drive back", "s", "down", None],
    "left": ["Turn left", "a", "left", None], "right": ["Turn right", "d", "right", None],
    "boost": ["Boost", "left shift", "right shift", None], "speed_down": ["Speed -", "q", None, None],
    "speed_up": ["Speed +", "e", None, None], "stop": ["Stop", "space", None, None],
    "next_droid": ["Switch droid", "tab", None, None], "disconnect": ["Disconnect", "escape", None, None],
    "reverse": ["Reverse (hold)", "r", None, 4], "aim": ["Aim / calibrate", "h", None, None], "stance": ["Stance (R2)", "x", None, 5],
    "dome_left": ["Dome left (R2)", "z", None, None], "dome_right": ["Dome right (R2)", "c", None, None],
    "random_emote": ["Random emote", None, None, 7], "deep_sleep": ["Deep Sleep", None, None, None], "fullscreen": ["Toggle fullscreen", "f11", None, None], "pad_switch": ["Pad: change droid", None, None, 6],
}
for i in range(10):
    DEFAULTS["emote%d" % (i + 1)] = ["Emote %d" % (i + 1), str((i + 1) % 10), None, i if i < 4 else None]
for g, k in (("push", "i"), ("pull", "k"), ("left", "j"), ("right", "l"), ("up", "u"), ("stop", "m")):
    DEFAULTS["band_" + g] = ["Band demo: " + g, k, None, None]
ORDER = list(DEFAULTS)


class Keybinds:
    def __init__(self, path):
        self.path = path
        self.reset(save=False)
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
            for a, v in d.items():
                if a in self.b and isinstance(v, dict):
                    self.b[a].update({k: v[k] for k in ("key", "key2", "pad") if k in v})
        except Exception:
            pass

    def reset(self, save=True):
        self.b = {a: {"key": v[1], "key2": v[2], "pad": v[3]} for a, v in DEFAULTS.items()}
        if save:
            self.save()

    def save(self):
        try:
            with open(self.path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(self.b, f, indent=1)
            os.replace(self.path + ".tmp", self.path)
        except Exception:
            pass

    def label(self, a):
        return DEFAULTS[a][0]

    def set_key(self, a, name):
        self.b[a]["key"], self.b[a]["key2"] = name, None
        self.save()

    def set_pad(self, a, btn):
        self.b[a]["pad"] = btn
        self.save()

    def keys(self, a):
        return [k for k in (self.b[a]["key"], self.b[a]["key2"]) if k]

    def action_for_key(self, name):
        for a in ORDER:
            if name in self.keys(a):
                return a
        return None

    def action_for_pad(self, btn):
        for a in ORDER:
            if self.b[a]["pad"] == btn:
                return a
        return None

    def conflicts(self):
        seen, bad = {}, set()
        for a in ORDER:
            for k in ["k:" + x for x in self.keys(a)] + (["p:%s" % self.b[a]["pad"]] if self.b[a]["pad"] is not None else []):
                if k in seen:
                    bad |= {a, seen[k]}
                seen[k] = a
        return bad

    def pressed(self, a, keystate, keycode):
        """True if any key for action is held. keycode = pygame.key.key_code."""
        for k in self.keys(a):
            try:
                if keystate[keycode(k)]:
                    return True
            except Exception:
                pass
        return False
