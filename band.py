"""Force Band (EXPERIMENTAL) support + band games for Droid Commander.
There is no public documentation of the Force Band's BLE protocol. Real-band support is a best-effort guess:
the band is a 2017 Sphero device that uses the same 'usetheforce...band' unlock and API-v2 packets as BB-9E/R2-D2,
so we try to talk to it through spherov2's BB-9E command set and read its accelerometer.
Everything also works with the Demo band (keyboard / on-screen gestures)."""
import json, math, os, random, re, threading, time, traceback
from collections import deque

GESTURES = ["push", "pull", "left", "right", "up", "stop"]
GESTURE_KEYS = {"push": "I", "pull": "K", "left": "J", "right": "L", "up": "U", "stop": "M"}
KNOWN_DROID_PREFIXES = ("BB-", "GB-", "D2-", "Q5-", "SB-", "SM-", "SK-", "RV-", "2B-", "2O-")


# ------------------------------------------------------------ gesture recognition (pure, unit tested)
class GestureDetector:
    """Feed accelerometer samples (x, y, z in g; y = forward along the arm, x = sideways, z = up).
    Detects a flick when linear accel (gravity removed by slow average) passes a threshold."""
    def __init__(self, threshold=1.3, cooldown=0.6, still_time=1.5):
        self.th, self.cool, self.still_time = threshold, cooldown, still_time
        self.grav = None
        self.last_fire = -9
        self.still_since = None
        self.stopped = True

    def feed(self, t, x, y, z):
        if self.grav is None:
            self.grav = [x, y, z]
        g = self.grav
        for i, v in enumerate((x, y, z)):
            g[i] = g[i] * 0.95 + v * 0.05
        lx, ly, lz = x - g[0], y - g[1], z - g[2]
        mag = math.sqrt(lx * lx + ly * ly + lz * lz)
        if mag < 0.15:
            self.still_since = self.still_since or t
            if not self.stopped and t - self.still_since > self.still_time and t - self.last_fire > self.cool:
                self.stopped = True
                return "stop"
        else:
            self.still_since = None
        if mag < self.th or t - self.last_fire < self.cool:
            return None
        self.last_fire = t
        self.stopped = False
        ax = max((abs(lx), "x"), (abs(ly), "y"), (abs(lz), "z"))[1]
        if ax == "y":
            return "push" if ly > 0 else "pull"
        if ax == "x":
            return "right" if lx > 0 else "left"
        return "up" if lz > 0 else "stop"


# ------------------------------------------------------------ bands
class DemoBand:
    name = "Demo band"
    def __init__(self):
        self.connected = False
        self.events = deque()
        self.pointing = 0.0  # degrees, for the Data Cube hunt
        self.battery = None
        self.error = None

    def connect(self):
        self.connected = True; return True

    def disconnect(self):
        self.connected = False

    def gesture(self, g):
        self.events.append(g)

    def poll(self):
        out = list(self.events); self.events.clear(); return out


class RealBand(DemoBand):
    """Experimental: talk to a Force Band using spherov2's API-v2 command set."""
    def __init__(self, raw_toy, adapter_cls):
        super().__init__()
        self.raw, self.adapter_cls = raw_toy, adapter_cls
        self.name = getattr(raw_toy, "name", "Force Band")
        self.det = GestureDetector()
        self._stop = threading.Event()
        self._ready = threading.Event()

    def connect(self, timeout=25):
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(timeout)
        return self.connected

    def disconnect(self):
        self._stop.set()

    def _run(self):
        try:
            from spherov2.toy.bb9e import BB9E
            from spherov2.types import ToyType
            from spherov2.sphero_edu import SpheroEduAPI

            class ForceBandToy(BB9E):
                toy_type = ToyType("Force Band", None, self.name[:3], .12)

            toy = ForceBandToy(self.raw, self.adapter_cls)
            with SpheroEduAPI(toy) as api:
                self.connected = True; self._ready.set()
                last_b = 0
                while not self._stop.is_set():
                    a = api.get_acceleration()
                    o = api.get_orientation()
                    now = time.time()
                    if a:
                        g = self.det.feed(now, a.get("x", 0), a.get("y", 0), a.get("z", 0))
                        if g:
                            self.events.append(g)
                    if o:
                        self.pointing = o.get("yaw", 0) % 360
                    if now - last_b > 30:
                        last_b = now
                        try:
                            v = toy.get_battery_voltage(); self.battery = max(0, min(100, int((v - 3.5) / 0.7 * 100)))
                        except Exception:
                            pass
                    time.sleep(0.03)
        except Exception as e:
            self.error = str(e) or type(e).__name__
            try:
                from droid_commander import log
                log("band error: " + traceback.format_exc())
            except Exception:
                pass
        finally:
            self.connected = False; self._ready.set()


def scan_bands(timeout=6.0):
    """List nearby Sphero-style devices (XX-1234 names) that are not known droids/robots."""
    from spherov2.adapter.bleak_adapter import BleakAdapter
    out = []
    for t in BleakAdapter.scan_toys(timeout):
        n = getattr(t, "name", None) or ""
        if re.match(r"^[A-Z0-9]{2}-[0-9A-F]{4}$", n) and not n.startswith(KNOWN_DROID_PREFIXES):
            out.append(RealBand(t, BleakAdapter))
        elif "band" in n.lower() or "force" in n.lower():
            out.append(RealBand(t, BleakAdapter))
    return out


# ------------------------------------------------------------ Data Cubes collection
CUBE_NAMES = ["Star Map", "Ancient Engine", "Lost Melody", "Pilot's Log", "Crystal Lens", "Old Blueprint",
              "Desert Compass", "Ice Moon Notes", "Rebel Radio", "Golden Gear", "Hidden Garden", "Storm Chart",
              "Comet Tail", "Robot Poem", "Secret Recipe", "Shadow Code", "Sunrise Song", "Deep Sea Echo",
              "Mountain Key", "Forest Whisper", "Sky Lantern", "Iron Feather", "Moon Dust", "Time Capsule",
              "Silver Shield", "Dragon Scale", "Glow Stone", "Lost Robot Arm", "Ocean Pearl", "Master Cube"]


class CubeCollection:
    def __init__(self, path):
        self.path = path
        try:
            with open(path, encoding="utf-8") as f:
                self.found = json.load(f)
        except Exception:
            self.found = {}

    def save(self):
        with open(self.path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self.found, f, indent=1)
        os.replace(self.path + ".tmp", self.path)

    def next_cube(self):
        left = [i for i in range(len(CUBE_NAMES)) if str(i) not in self.found]
        return left[0] if left else None

    def collect(self, i):
        self.found[str(i)] = time.time(); self.save()
        return "Data Cube #%d: %s" % (i + 1, CUBE_NAMES[i])


class CubeHunt:
    """Turn (band yaw, arrow keys or mouse) to aim a scanner. Signal gets stronger near the hidden target;
    hold it on target for 2 s, then do a PULL gesture to collect."""
    def __init__(self, cubes):
        self.cubes = cubes
        self.idx = cubes.next_cube()
        self.target = random.uniform(0, 360)
        self.lock = 0.0
        self.ready = False
        self.msg = "Turn slowly and watch the signal..." if self.idx is not None else "You found every Data Cube!"

    def signal(self, aim):
        diff = abs((aim - self.target + 180) % 360 - 180)
        return max(0.0, 1 - diff / 180) ** 3

    def update(self, dt, aim, gestures):
        if self.idx is None:
            return None
        s = self.signal(aim)
        self.lock = self.lock + dt if s > 0.93 else max(0, self.lock - dt * 2)
        if self.lock > 2:
            self.ready = True; self.msg = "LOCKED ON! Do a PULL to grab the cube."
        if self.ready and "pull" in gestures:
            name = self.cubes.collect(self.idx)
            self.__init__(self.cubes)
            return name
        return None


# ------------------------------------------------------------ training games
class ReflexTrainer:
    """'Reflex Trainer': do the gesture shown before time runs out. Gets faster."""
    name = "Reflex Trainer"
    def __init__(self):
        self.score, self.lives, self.limit = 0, 3, 2.0
        self.new_prompt()
        self.over = False

    def new_prompt(self):
        self.prompt = random.choice(["push", "pull", "left", "right", "up"])
        self.t = self.limit

    def update(self, dt, gestures):
        if self.over:
            return None
        self.t -= dt
        res = None
        if gestures:
            if self.prompt in gestures:
                self.score += 1; self.limit = max(0.8, self.limit * 0.94); res = "hit"
            else:
                self.lives -= 1; res = "miss"
            self.new_prompt()
        elif self.t <= 0:
            self.lives -= 1; res = "miss"; self.new_prompt()
        if self.lives <= 0:
            self.over = True; res = "over"
        return res


class DuelTrainer:
    """'Duel Trainer': a training bot attacks from a side; block with the matching gesture, then PUSH to strike."""
    name = "Duel Trainer"
    BLOCK = {"left": "left", "right": "right", "high": "up"}

    def __init__(self):
        self.hp, self.bot_hp = 5, 6
        self.over = False
        self.next_attack()

    def next_attack(self):
        self.attack = random.choice(list(self.BLOCK)); self.t = 1.8; self.opening = 0

    def update(self, dt, gestures):
        if self.over:
            return None
        res = None
        if self.opening > 0:
            self.opening -= dt
            if "push" in gestures:
                self.bot_hp -= 1; res = "strike"; self.next_attack()
            elif self.opening <= 0:
                self.next_attack()
        else:
            self.t -= dt
            if self.BLOCK[self.attack] in gestures:
                res = "block"; self.opening = 1.2
            elif gestures or self.t <= 0:
                self.hp -= 1; res = "hit"; self.next_attack()
        if self.hp <= 0 or self.bot_hp <= 0:
            self.over = True; res = "win" if self.bot_hp <= 0 else "lose"
        return res


# ------------------------------------------------------------ generic synthesized sounds
def make_sounds(pygame):
    """Generate simple beeps/hums with numpy. Returns dict name->Sound (empty if audio unavailable)."""
    try:
        import numpy as np
        if not pygame.mixer.get_init():
            pygame.mixer.init(22050, -16, 1)
        sr = pygame.mixer.get_init()[0]
        ch = pygame.mixer.get_init()[2]

        def tone(freqs, dur, vol=0.4, noise=0.0):
            t = np.linspace(0, dur, int(sr * dur), False)
            f = np.interp(t, np.linspace(0, dur, len(freqs)), freqs)
            w = np.sin(2 * np.pi * np.cumsum(f) / sr)
            if noise:
                w = w * (1 - noise) + np.random.uniform(-1, 1, len(t)) * noise
            env = np.minimum(1, np.minimum(t * 60, (dur - t) * 30))
            a = (w * env * vol * 32767).astype(np.int16)
            if ch == 2:
                a = np.column_stack([a, a])
            return pygame.sndarray.make_sound(a.copy())
        return {"ping": tone([1200], 0.06), "found": tone([600, 900, 1300], 0.5), "hit": tone([880, 1320], 0.12),
                "miss": tone([300, 150], 0.3), "swoosh": tone([200, 700, 120], 0.25, 0.3, 0.5),
                "clash": tone([1500, 400], 0.18, 0.5, 0.6), "win": tone([500, 700, 900, 1200], 0.8),
                "lose": tone([400, 300, 200], 0.8)}
    except Exception:
        return {}
