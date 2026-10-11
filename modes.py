"""Droid Commander modes. Each mode's step(dt, brain) returns (heading, speed) or None when finished.
Drive (free roam) input is in drive_from_keyboard / drive_from_pad so it can be changed on its own."""
import json, math, os, random, time

MODES = ["Drive", "Patrol", "Path", "Record"]


# ------------------------------------------------------------ Drive (free roam)
class DriveSettings:
    turn_rate = 140      # degrees per second when turning with keys
    boost = 1.5          # Shift multiplier
    deadzone = 0.25      # stick deadzone


def drive_from_keyboard(k, K, base_heading, max_speed, dt, s=DriveSettings):
    """k = pygame key state, K = pygame module. Returns (new_base_heading, heading, speed, had_input)."""
    fwd = (k[K.K_w] or k[K.K_UP]) - (k[K.K_s] or k[K.K_DOWN])
    turn = (k[K.K_d] or k[K.K_RIGHT]) - (k[K.K_a] or k[K.K_LEFT])
    boost = k[K.K_LSHIFT] or k[K.K_RSHIFT]
    base = (base_heading + turn * s.turn_rate * dt) % 360
    h, sp = base, 0
    if fwd:
        sp = max_speed * (s.boost if boost else 1)
        if fwd < 0:
            h = (h + 180) % 360
    if k[K.K_SPACE]:
        sp = 0
    return base, h, sp, bool(fwd or turn or k[K.K_SPACE])


def drive_from_pad(j, base_heading, max_speed, s=DriveSettings):
    """Returns (heading, speed, had_input) or None if stick is centred."""
    x, y = j.get_axis(0), j.get_axis(1)
    mag = math.hypot(x, y)
    if mag <= s.deadzone:
        return None
    rt = (j.get_axis(5) + 1) / 2 if j.get_numaxes() > 5 else 0
    lt = (j.get_axis(4) + 1) / 2 if j.get_numaxes() > 4 else 0
    return ((base_heading + math.degrees(math.atan2(x, -y))) % 360, min(1, mag) * max_speed * (1 + 0.6 * rt - 0.5 * lt), True)


# ------------------------------------------------------------ Patrol
class PatrolMode:
    name = "Patrol"

    def __init__(self, brain):
        self.b = brain
        self.phase, self.t, self.heading, self.speed = "pause", 0.5, random.uniform(0, 360), 0
        brain.patrol_bump = False

    def step(self, dt, brain):
        self.t -= dt
        if brain.patrol_bump:
            brain.patrol_bump = False
            self.phase, self.t = "backup", 0.8
            self.heading = (self.heading + 180) % 360
            brain.say("%s backs away from the obstacle." % brain.d.name)
        if self.t <= 0:
            if self.phase == "backup":
                self.heading = (self.heading + random.choice([-1, 1]) * random.uniform(60, 120)) % 360
                self.phase, self.t = "wander", random.uniform(1.5, 3)
            elif self.phase == "wander" and random.random() < 0.35:
                self.phase, self.t = "pause", random.uniform(1.5, 3.5)
                from droid_commander import pick
                mood = brain.p.mood
                brain.emote(pick(brain.d.model, "idle_happy" if mood > 40 else "idle_sad" if mood < -20 else "idle"), xp=0)
            else:
                self.phase, self.t = "wander", random.uniform(2, 5)
                self.heading = (self.heading + random.uniform(-100, 100)) % 360
        if self.phase == "pause":
            return (self.heading, 0)
        energy = max(0.4, brain.p.energy / 100)  # tired droids patrol slower
        speed = 90 if self.phase == "backup" else int((50 + 0.5 * max(0, brain.p.mood)) * energy + 20)
        return (self.heading, min(140, speed))


# ------------------------------------------------------------ Path (draw to drive)
class PathMode:
    """Follows a drawn path with roll timing. 1 canvas pixel ~ CM_PER_PX cm; SPEED ~ CM_PER_SEC."""
    name = "Path"
    SPEED, CM_PER_SEC, CM_PER_PX = 70, 45.0, 1.0

    def __init__(self, brain, points):
        self.segs = path_to_segments(points, self.CM_PER_PX, self.CM_PER_SEC)
        self.i, self.t = 0, self.segs[0][1] if self.segs else 0
        self.last_h = 0

    def step(self, dt, brain):
        if self.i >= len(self.segs):
            return None
        h, dur = self.segs[self.i]
        self.t -= dt
        if self.t <= 0:
            self.i += 1
            if self.i < len(self.segs):
                self.t = self.segs[self.i][1]
        self.last_h = h
        return (h, self.SPEED)


def simplify(points, min_dist=12):
    out = []
    for p in points:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) >= min_dist:
            out.append(p)
    return out


def path_to_segments(points, cm_per_px=1.0, cm_per_sec=45.0):
    """Screen points -> [(heading_deg, seconds)]. Up on screen = heading 0 (droid's forward/aim)."""
    pts = simplify(points)
    segs = []
    for a, b in zip(pts, pts[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        d = math.hypot(dx, dy)
        if d < 1:
            continue
        segs.append((math.degrees(math.atan2(dx, -dy)) % 360, d * cm_per_px / cm_per_sec))
    return segs


# ------------------------------------------------------------ Record & playback
def rec_dir():
    from droid_commander import data_dir
    d = os.path.join(data_dir(), "recordings")
    os.makedirs(d, exist_ok=True)
    return d


class Recorder:
    def __init__(self):
        self.recording = False
        self.events = []  # (t, "drive", heading, speed) | (t, "emote", label)
        self.t0 = 0
        self._last = None

    def start(self):
        self.recording, self.events, self.t0, self._last = True, [], time.time(), None

    def stop(self):
        self.recording = False
        if self._last is not None and self._last[1]:
            self.events.append((time.time() - self.t0, "drive", self._last[0], 0))

    def tick(self, heading, speed):
        if not self.recording:
            return
        cur = (int(heading), int(speed))
        if cur != self._last:
            self.events.append((round(time.time() - self.t0, 3), "drive", cur[0], cur[1]))
            self._last = cur

    def emote(self, label):
        if self.recording:
            self.events.append((round(time.time() - self.t0, 3), "emote", label))

    @property
    def length(self):
        return self.events[-1][0] if self.events else 0

    def save(self, name=None):
        name = name or time.strftime("rec_%Y%m%d_%H%M%S")
        path = os.path.join(rec_dir(), name + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"events": self.events}, f)
        return path

    def load(self, path):
        with open(path, encoding="utf-8") as f:
            self.events = [tuple(e) for e in json.load(f)["events"]]


def list_recordings():
    d = rec_dir()
    return sorted((os.path.join(d, f) for f in os.listdir(d) if f.endswith(".json")), key=os.path.getmtime, reverse=True)


class PlaybackMode:
    name = "Playback"

    def __init__(self, brain, events):
        self.ev, self.i, self.t, self.cur = list(events), 0, 0.0, (0, 0)

    def step(self, dt, brain):
        self.t += dt
        while self.i < len(self.ev) and self.ev[self.i][0] <= self.t:
            e = self.ev[self.i]
            if e[1] == "drive":
                self.cur = (e[2], e[3])
            elif e[1] == "emote":
                brain.d.emote(e[2])
            self.i += 1
        if self.i >= len(self.ev):
            return None
        return self.cur
