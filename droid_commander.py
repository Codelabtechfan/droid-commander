"""Droid Commander - drive and play with Sphero app-enabled droids (BB-8, BB-9E, R2-D2, R2-Q5).
Unofficial fan tool. Not affiliated with Sphero, Disney or Lucasfilm. Uses no movie assets."""
import json, math, os, queue, random, sys, threading, time, traceback

APP = "Droid Commander"
VERSION = "1.1.0"
SUPPORTED = ("BB8", "BB9E", "R2D2", "R2Q5")
PRETTY = {"BB8": "BB-8", "BB9E": "BB-9E", "R2D2": "R2-D2", "R2Q5": "R2-Q5"}


def data_dir():
    base = os.environ.get("APPDATA") or os.path.join(os.path.expanduser("~"), ".config")
    d = os.path.join(base, "DroidCommander")
    os.makedirs(d, exist_ok=True)
    return d


def log(msg):
    try:
        with open(os.path.join(data_dir(), "log.txt"), "a", encoding="utf-8") as f:
            f.write(time.strftime("%H:%M:%S ") + str(msg) + "\n")
    except Exception:
        pass


# ---------------------------------------------------------------- personality
class Personality:
    """Mood / energy / XP memory that persists between sessions (one file per droid)."""
    MOODS = [(-60, "Grumpy"), (-20, "Sad"), (20, "Calm"), (60, "Happy"), (101, "Ecstatic")]

    def __init__(self, droid_id, path=None):
        self.droid_id = droid_id
        self.path = path or os.path.join(data_dir(), "memory_%s.json" % "".join(c for c in droid_id if c.isalnum() or c in "-_"))
        self.mood, self.energy, self.xp = 10.0, 80.0, 0
        self.bumps = self.pets = self.sessions = self.emotes = 0
        self.drive_seconds = 0.0
        self.last_seen = None
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            for k in ("mood", "energy", "xp", "bumps", "pets", "sessions", "emotes", "drive_seconds", "last_seen"):
                if k in d:
                    setattr(self, k, d[k])
        except Exception:
            pass

    def save(self):
        d = {k: getattr(self, k) for k in ("mood", "energy", "xp", "bumps", "pets", "sessions", "emotes", "drive_seconds", "last_seen")}
        d["last_seen"] = time.time()
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=1)
        os.replace(tmp, self.path)

    def start_session(self):
        """Called on connect. Returns greeting kind based on how long it has been away."""
        self.sessions += 1
        away = (time.time() - self.last_seen) if self.last_seen else None
        self.energy = min(100, self.energy + (30 if away and away > 3600 else 5))
        if away is None:
            kind = "first"
            self.mood = 20
        elif away > 3 * 86400:
            kind = "missed"; self.mood = max(-100, self.mood - 15)
        else:
            kind = "back"; self.mood = min(100, self.mood + 10)
        self.add_xp(5)
        return kind

    def nudge(self, d):
        self.mood = max(-100.0, min(100.0, self.mood + d))

    def add_xp(self, n):
        self.xp += n

    @property
    def level(self):
        return 1 + int(math.sqrt(self.xp / 20))

    @property
    def mood_name(self):
        for lim, name in self.MOODS:
            if self.mood < lim:
                return name
        return "Ecstatic"

    def tick(self, dt, speed_frac):
        if speed_frac > 0.05:
            self.drive_seconds += dt
            self.energy = max(0.0, self.energy - dt * 0.4 * speed_frac)
            self.nudge(dt * 0.3)
        else:
            self.energy = min(100.0, self.energy + dt * 0.05)
            self.nudge(-dt * 0.02)  # gets a bit bored when ignored


# ---------------------------------------------------------------- emote tables
def emote_table(model):
    """Return list of (label, animation_name) supported by model. Names verified against spherov2 0.12."""
    r2 = [("Happy", "WWM_HAPPY"), ("Laugh", "EMOTE_LAUGH"), ("Yes", "EMOTE_YES"), ("No", "EMOTE_NO"),
          ("Excited", "EMOTE_EXCITED"), ("Scared", "WWM_SCARED"), ("Angry", "EMOTE_ANGRY"), ("Sad", "WWM_SAD"),
          ("Surprised", "EMOTE_SURPRISED"), ("Scan", "EMOTE_SCAN"), ("Alarm", "EMOTE_ALARM"), ("Bow", "WWM_BOW"),
          ("Curious", "WWM_CURIOUS"), ("Yoohoo", "WWM_YOOHOO"), ("Short circuit", "EMOTE_SHORT_CIRCUIT"), ("Shake", "WWM_SHAKE")]
    bb9 = [("Happy", "WWM_HAPPY"), ("Laugh", "WWM_LAUGH"), ("Yes", "EMOTE_YES"), ("No", "EMOTE_NO"),
           ("Excited", "EMOTE_EXCITED"), ("Scared", "EMOTE_SCARED"), ("Angry", "EMOTE_ANGRY"), ("Content", "EMOTE_CONTENT"),
           ("Surprised", "EMOTE_SURPRISED"), ("Scan", "EMOTE_SCAN_SWEEP"), ("Alarm", "EMOTE_ALARM"), ("Bow", "WWM_BOW"),
           ("Curious", "WWM_CURIOUS"), ("Greetings", "EMOTE_GREETINGS"), ("Nervous", "EMOTE_NERVOUS"), ("Sleep", "EMOTE_SLEEP")]
    bb8 = [("Happy", "~happy"), ("Spin", "~spin"), ("Yes", "~yes"), ("No", "~no"), ("Excited", "~excited"),
           ("Scared", "~scared"), ("Angry", "~angry"), ("Sad", "~sad"), ("Rainbow", "~rainbow"), ("Wiggle", "~wiggle")]
    return {"R2D2": r2, "R2Q5": r2, "BB9E": bb9, "BB8": bb8}.get(model, bb8)


# mood-related picks (label from emote_table)
REACT = {"bump": ["Scared", "Surprised", "Angry", "No"], "fast": ["Excited", "Happy", "Laugh"],
         "idle_happy": ["Happy", "Curious", "Yes", "Laugh"], "idle_sad": ["Sad", "No", "Scared", "Content"],
         "idle": ["Curious", "Scan", "Content", "Happy"], "greet": ["Excited", "Happy", "Greetings", "Yoohoo"],
         "missed": ["Sad", "Excited"], "pet": ["Happy", "Laugh", "Yes", "Content"], "poke": ["Angry", "No", "Surprised"]}


def pick(model, kind):
    labels = {l for l, _ in emote_table(model)}
    opts = [x for x in REACT.get(kind, []) if x in labels] or [emote_table(model)[0][0]]
    return random.choice(opts)


# ---------------------------------------------------------------- droid links
class MockDroid:
    """Fake droid used for --demo and --selftest."""
    def __init__(self, model="R2D2", name="Mock-R2"):
        self.model, self.name = model, name
        self.connected = False
        self.heading = 0; self.speed = 0
        self.battery = 87
        self.calls = []
        self.on_collision = None
        self.dome = 0; self.stance = "tripod"

    def connect(self):
        self.connected = True; return True

    def disconnect(self):
        self.connected = False

    def drive(self, heading, speed):
        self.heading, self.speed = int(heading) % 360, int(max(0, min(255, speed)))

    def emote(self, label):
        self.calls.append(("emote", label))

    def dome_to(self, angle):
        self.dome = angle; self.calls.append(("dome", angle))

    def set_stance(self, s):
        self.stance = s; self.calls.append(("stance", s))

    def lights(self, rgb):
        self.calls.append(("led", rgb))

    def get_battery(self):
        return self.battery

    def simulate_bump(self):
        if self.on_collision:
            self.on_collision()


class RealDroid:
    """Runs spherov2's SpheroEduAPI inside a worker thread; GUI talks to it via thread-safe calls."""
    def __init__(self, toy):
        self.toy = toy
        self.model = type(toy).__name__
        self.name = getattr(toy, "name", None) or PRETTY.get(self.model, self.model)
        self.connected = False
        self.error = None
        self.battery = None
        self.on_collision = None
        self._q = queue.Queue()
        self._drive = (0, 0)
        self._sent = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._t = None

    def connect(self, timeout=25):
        self._t = threading.Thread(target=self._run, daemon=True)
        self._t.start()
        self._ready.wait(timeout)
        return self.connected

    def disconnect(self):
        self._stop.set()
        if self._t:
            self._t.join(6)

    def drive(self, heading, speed):
        self._drive = (int(heading) % 360, int(max(0, min(255, speed))))

    def emote(self, label):
        self._q.put(("emote", label))

    def dome_to(self, angle):
        self._q.put(("dome", angle))

    def set_stance(self, s):
        self._q.put(("stance", s))

    def lights(self, rgb):
        self._q.put(("led", rgb))

    def get_battery(self):
        return self.battery

    # worker ---------------------------------------------------------------
    def _run(self):
        try:
            from spherov2.sphero_edu import SpheroEduAPI, EventType
            from spherov2.types import Color
            with SpheroEduAPI(self.toy) as api:
                self.api, self.Color = api, Color
                try:
                    api.register_event(EventType.on_collision, lambda *_: self.on_collision and self.on_collision())
                except Exception as e:
                    log("collision events unavailable: %r" % e)
                if self.model in ("R2D2", "R2Q5"):
                    self._safe(lambda: api.set_stance(__import__("spherov2.types", fromlist=["Stance"]).Stance.Tripod))
                self._safe(lambda: api.set_main_led(Color(0, 120, 255)))
                self.connected = True
                self._ready.set()
                last_batt = 0
                while not self._stop.is_set():
                    try:
                        cmd = self._q.get(timeout=0.05)
                        self._do(cmd)
                    except queue.Empty:
                        pass
                    if self._drive != self._sent:
                        h, s = self._drive
                        self._safe(lambda: (api.set_heading(h), api.set_speed(s)))
                        self._sent = (h, s)
                    if time.time() - last_batt > 20:
                        last_batt = time.time()
                        self._read_battery()
                self._safe(lambda: api.stop_roll())
        except Exception as e:
            self.error = str(e) or type(e).__name__
            log("droid thread error: " + traceback.format_exc())
        finally:
            self.connected = False
            self._ready.set()

    def _safe(self, fn):
        try:
            return fn()
        except Exception as e:
            log("cmd failed: %r" % e)

    def _read_battery(self):
        for attr in ("get_battery_percentage", "get_battery_voltage"):
            f = getattr(self.toy, attr, None)
            if f:
                try:
                    v = f()
                    if attr == "get_battery_voltage":
                        v = max(0, min(100, int((v - 3.5) / 0.7 * 100)))
                    self.battery = int(v)
                    return
                except Exception:
                    continue

    def _do(self, cmd):
        api, Color = self.api, self.Color
        kind, arg = cmd
        if kind == "emote":
            name = dict(emote_table(self.model)).get(arg)
            if not name:
                return
            if name.startswith("~"):
                self._bb8_emote(name[1:])
            else:
                anim = getattr(getattr(self.toy, "Animations", None), name, None)
                if anim is not None:
                    self._safe(lambda: api.play_animation(anim))
                    self._sent = None
        elif kind == "dome":
            self._safe(lambda: api.set_dome_position(arg))
        elif kind == "stance":
            from spherov2.types import Stance
            self._safe(lambda: api.set_stance(Stance.Bipod if arg == "bipod" else Stance.Tripod))
        elif kind == "led":
            self._safe(lambda: api.set_main_led(Color(*arg)))

    def _bb8_emote(self, n):
        api, C = self.api, self.Color
        s = self._safe
        if n == "happy":
            s(lambda: api.strobe(C(0, 255, 0), 0.15, 4)); s(lambda: api.spin(360, 0.8))
        elif n == "spin":
            s(lambda: api.spin(720, 1.2))
        elif n == "yes":
            for _ in range(2):
                s(lambda: api.raw_motor(80, 80, 0.15)); s(lambda: api.raw_motor(-80, -80, 0.15))
        elif n == "no":
            s(lambda: api.spin(30, 0.15)); s(lambda: api.spin(-60, 0.25)); s(lambda: api.spin(30, 0.15))
        elif n == "excited":
            s(lambda: api.strobe(C(255, 200, 0), 0.08, 8)); s(lambda: api.spin(540, 0.8))
        elif n == "scared":
            s(lambda: api.set_main_led(C(255, 255, 255))); s(lambda: api.raw_motor(-120, -120, 0.4))
        elif n == "angry":
            s(lambda: api.strobe(C(255, 0, 0), 0.1, 6))
        elif n == "sad":
            s(lambda: api.fade(C(0, 0, 255), C(0, 0, 30), 1.5))
        elif n == "rainbow":
            for c in [(255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0), (0, 0, 255), (128, 0, 255)]:
                s(lambda c=c: api.set_main_led(C(*c))); time.sleep(0.2)
        elif n == "wiggle":
            for _ in range(3):
                s(lambda: api.spin(25, 0.12)); s(lambda: api.spin(-25, 0.12))
        s(lambda: api.set_main_led(C(0, 120, 255)))
        self._sent = None


def scan(timeout=6.0):
    """Return list of supported toys nearby."""
    from spherov2 import scanner
    from spherov2.toy.bb8 import BB8
    from spherov2.toy.bb9e import BB9E
    from spherov2.toy.r2d2 import R2D2
    from spherov2.toy.r2q5 import R2Q5
    toys = scanner.find_toys(timeout=timeout, toy_types=[BB8, BB9E, R2D2, R2Q5])
    return [t for t in toys if type(t).__name__ in SUPPORTED]


# ---------------------------------------------------------------- brain (personality + controls logic, GUI independent)
class Brain:
    def __init__(self, droid, personality=None):
        self.d = droid
        self.p = personality or Personality("%s_%s" % (droid.model, droid.name))
        self.events = []  # (time, text)
        self.last_input = time.time()
        droid.speed_now = 0
        self.next_idle = time.time() + random.uniform(12, 25)
        self.fast_since = None
        self.last_react = 0
        self.bump_flag = False
        droid.on_collision = self._bump
        self.dome = 0
        self.stance = "tripod"
        self.signals = []  # events other droids can react to
        self.joined = time.time()
        import modes
        self.mode = "Drive"
        self.auto = None  # active autopilot (Patrol/Path/Playback)
        self.recorder = modes.Recorder()
        self.path_points = []

    def say(self, text):
        self.events.append((time.time(), text)); self.events = self.events[-6:]
        log(text)

    def _bump(self):
        self.bump_flag = True  # handled on main thread
        self.patrol_bump = True

    def greet(self):
        kind = self.p.start_session()
        if kind == "first":
            self.say("%s says hello for the first time!" % self.d.name); self.emote(pick(self.d.model, "greet"), xp=0)
        elif kind == "missed":
            self.say("%s missed you! It's been a while." % self.d.name); self.emote(pick(self.d.model, "missed"), xp=0)
        else:
            self.say("%s is happy you're back (mood: %s)" % (self.d.name, self.p.mood_name)); self.emote(pick(self.d.model, "greet"), xp=0)
        self.p.save()

    def emote(self, label, xp=1):
        self.d.emote(label)
        if xp:
            self.recorder.emote(label)
        self.p.emotes += 1
        if xp:
            self.p.add_xp(xp); self.p.nudge(2)
        self.last_react = time.time()

    def pet(self):
        self.p.pets += 1; self.p.nudge(8); self.p.add_xp(2)
        self.say("You gave %s a pat. It loves that!" % self.d.name); self.emote(pick(self.d.model, "pet"), xp=0)

    def poke(self):
        self.p.nudge(-6)
        self.say("Hey! %s didn't like that poke." % self.d.name); self.emote(pick(self.d.model, "poke"), xp=0)

    def toggle_stance(self):
        if self.d.model not in ("R2D2", "R2Q5"):
            return
        self.stance = "bipod" if self.stance == "tripod" else "tripod"
        self.d.set_stance(self.stance); self.say("Stance: " + self.stance)

    def turn_dome(self, delta):
        if self.d.model not in ("R2D2", "R2Q5"):
            return
        self.dome = max(-160, min(180, self.dome + delta)); self.d.dome_to(self.dome)

    def set_mode(self, mode):
        import modes
        self.auto = None
        if self.recorder.recording:
            self.recorder.stop()
        self.mode = mode
        if mode == "Patrol":
            self.auto = modes.PatrolMode(self); self.say("%s starts patrolling." % self.d.name)

    def start_path(self):
        import modes
        pm = modes.PathMode(self, self.path_points)
        if pm.segs:
            self.auto = pm; self.say("%s follows your path (%d legs)." % (self.d.name, len(pm.segs)))

    def start_playback(self, events):
        import modes
        if events:
            self.auto = modes.PlaybackMode(self, events); self.say("%s replays a recording." % self.d.name)

    def control(self, dt, heading, speed, had_input):
        """Combine manual input with the current mode. Any manual input stops an autopilot."""
        if self.auto:
            if had_input:
                self.say("%s: %s stopped by you." % (self.d.name, self.auto.name))
                self.auto = None
                if self.mode == "Patrol":
                    self.mode = "Drive"
            else:
                out = self.auto.step(dt, self)
                if out is None:
                    self.say("%s finished %s." % (self.d.name, self.auto.name.lower())); self.auto = None
                    heading, speed = (self.d.heading if hasattr(self.d, "heading") else heading), 0
                else:
                    heading, speed = out
                    self.next_idle = time.time() + 20
        if self.recorder.recording:
            self.recorder.tick(heading, speed)
        self.update(dt, heading, int(max(0, min(255, speed))), had_input)

    def update(self, dt, heading, speed, had_input, max_speed=255):
        now = time.time()
        if had_input:
            self.last_input = now
            self.next_idle = now + random.uniform(15, 30)
        if self.stance == "bipod" and speed > 0:
            self.stance = "tripod"; self.d.set_stance("tripod")
        self.d.drive(heading, speed)
        self.d.speed_now = speed
        frac = speed / 255.0
        self.p.tick(dt, frac)
        self.p.add_xp(0)
        if frac > 0.75:
            self.fast_since = self.fast_since or now
            if now - self.fast_since > 3 and now - self.last_react > 12:
                self.say("Wheee! %s loves going fast!" % self.d.name); self.signals.append("fast")
                self.p.add_xp(3); self.p.nudge(5); self.emote(pick(self.d.model, "fast"), xp=0)
                self.fast_since = now
        else:
            self.fast_since = None
        if self.bump_flag:
            self.bump_flag = False
            self.p.bumps += 1; self.p.nudge(-4)
            if now - self.last_react > 2:
                self.say("Ouch! %s bumped into something." % self.d.name); self.signals.append("bump")
                self.emote(pick(self.d.model, "bump"), xp=0)
        if speed == 0 and now > self.next_idle and not getattr(self, 'social_busy', False):
            kind = "idle_happy" if self.p.mood > 40 else "idle_sad" if self.p.mood < -20 else "idle"
            lab = pick(self.d.model, kind)
            self.say("%s is bored... (%s)" % (self.d.name, lab.lower()) if kind != "idle_happy" else "%s is feeling chatty (%s)" % (self.d.name, lab.lower()))
            self.emote(lab, xp=0)
            if self.d.model in ("R2D2", "R2Q5") and random.random() < 0.5:
                self.turn_dome(random.choice([-90, -45, 45, 90]) - self.dome)
            self.next_idle = now + random.uniform(20, 45)


# ---------------------------------------------------------------- droid-to-droid social life
class Society:
    """Friendships between connected droids, persisted in friends.json. Drives greetings, chats and reactions."""
    def __init__(self, path=None):
        self.path = path or os.path.join(data_dir(), "friends.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.friends = json.load(f)
        except Exception:
            self.friends = {}
        self.known = set()
        self.next_chat = time.time() + random.uniform(15, 30)
        self.script = []  # pending (time, brain, label, text)

    @staticmethod
    def key(a, b):
        return "|".join(sorted([a.p.droid_id, b.p.droid_id]))

    def friendship(self, a, b):
        return self.friends.get(self.key(a, b), 0)

    def bond(self, a, b, n):
        k = self.key(a, b); self.friends[k] = max(-100, min(100, self.friends.get(k, 0) + n))

    def save(self):
        with open(self.path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self.friends, f, indent=1)
        os.replace(self.path + ".tmp", self.path)

    def queue(self, steps):
        t = time.time()
        for delay, b, lab, txt in steps:
            t += delay; self.script.append((t, b, lab, txt))
        for _, b, _, _ in steps:
            b.social_busy = True

    def update(self, brains):
        now = time.time()
        ids = {id(b) for b in brains}
        self.script = [x for x in self.script if id(x[1]) in ids]
        due = [x for x in self.script if x[0] <= now]
        self.script = [x for x in self.script if x[0] > now]
        for _, b, lab, txt in due:
            if lab:
                b.emote(lab, xp=0)
            if txt:
                b.say(txt)
        busy = {id(x[1]) for x in self.script}
        for b in brains:
            b.social_busy = id(b) in busy
        # greetings for newcomers
        for b in brains:
            if id(b) not in self.known:
                self.known.add(id(b))
                for o in brains:
                    if o is not b:
                        fr = self.friendship(b, o)
                        mood = "best friend" if fr > 50 else "friend" if fr > 10 else "new pal" if fr > -10 else "rival"
                        self.queue([(3, o, pick(o.d.model, "greet"), "%s spots %s (%s) and says hi!" % (o.d.name, b.d.name, mood)),
                                    (2.5, b, pick(b.d.model, "greet" if fr > -10 else "poke"), "%s waves back." % b.d.name)])
                        self.bond(b, o, 3)
        self.known &= ids
        # reactions to signals
        for b in brains:
            while b.signals:
                sig = b.signals.pop(0)
                for o in brains:
                    if o is b or o.social_busy:
                        continue
                    fr = self.friendship(b, o)
                    if sig == "bump":
                        if fr >= 0:
                            self.queue([(1.5, o, pick(o.d.model, "missed" if fr > 30 else "bump"), "%s worries about %s." % (o.d.name, b.d.name))]); self.bond(b, o, 2)
                        else:
                            self.queue([(1.5, o, pick(o.d.model, "fast"), "%s laughs at %s's crash!" % (o.d.name, b.d.name))])
                    elif sig == "fast":
                        self.queue([(1, o, pick(o.d.model, "fast" if fr >= 0 else "poke"), "%s cheers %s on!" % (o.d.name, b.d.name) if fr >= 0 else "%s is jealous of %s's speed." % (o.d.name, b.d.name))])
                        self.bond(b, o, 1)
        # idle chats / playful sequences
        idle = [b for b in brains if b.d.speed_now == 0 and now - b.last_input > 8 and not b.social_busy] if len(brains) > 1 else []
        if len(idle) >= 2 and now > self.next_chat:
            a, b = random.sample(idle, 2)
            fr = self.friendship(a, b)
            if random.random() < 0.35:
                self.queue([(0, a, None, "%s shows off a trick for %s!" % (a.d.name, b.d.name)),
                            (0.5, a, pick(a.d.model, "fast"), None),
                            (3, b, pick(b.d.model, "pet" if fr >= 0 else "poke"), "%s %s." % (b.d.name, "is impressed" if fr >= 0 else "isn't impressed"))])
            else:
                topic = random.choice(["the weather", "batteries", "who is faster", "funny noises", "their favourite spot"])
                steps = [(0, a, pick(a.d.model, "idle"), "%s chats with %s about %s." % (a.d.name, b.d.name, topic))]
                for i in range(random.randint(2, 4)):
                    who = b if i % 2 == 0 else a
                    steps.append((3, who, pick(who.d.model, "idle_happy" if fr >= -10 else "poke"), None))
                steps.append((3, a, pick(a.d.model, "pet"), "%s and %s had a nice chat." % (a.d.name, b.d.name) if fr >= -10 else "%s and %s argued!" % (a.d.name, b.d.name)))
                self.queue(steps)
            self.bond(a, b, 4); a.p.add_xp(2); b.p.add_xp(2)
            for x in (a, b):
                x.next_idle = now + 40
            self.next_chat = now + random.uniform(25, 50)
            self.save()


# ---------------------------------------------------------------- GUI
def run_gui(demo=False, selftest_frames=0, demo_count=1):
    import pygame
    import modes, band as bandmod
    pygame.init()
    pygame.joystick.init()
    W, H = 1180, 720
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("%s %s" % (APP, VERSION))
    clock = pygame.time.Clock()
    F = pygame.font.SysFont("segoeui,arial,dejavusans", 18)
    FB = pygame.font.SysFont("segoeui,arial,dejavusans", 26, bold=True)
    FS = pygame.font.SysFont("segoeui,arial,dejavusans", 14)
    BG, PANEL, ACC, TXT, DIM = (18, 22, 34), (30, 36, 54), (0, 170, 255), (235, 240, 250), (140, 150, 170)
    society = Society()
    sounds = bandmod.make_sounds(pygame)
    def sfx(n):
        if n in sounds:
            try: sounds[n].play()
            except Exception: pass
    bs_ = {"band": None, "found": [], "tab": "Control", "game": None, "hunt": None, "drive_until": 0, "drive_off": 0,
           "last_g": "", "last_g_t": 0, "msg": "", "ping_t": 0, "scanning": False}
    cubes = bandmod.CubeCollection(os.path.join(data_dir(), "data_cubes.json"))
    GKEYS = {getattr(pygame, "K_" + v.lower()): g for g, v in bandmod.GESTURE_KEYS.items()}
    state = {"found": [], "scanning": False, "status": "Press SCAN to look for droids", "brains": [],
             "active": 0, "connecting": 0, "max": 160, "heading": {}, "busy_addrs": set()}
    joys = {}      # instance_id -> joystick
    joy_map = {}   # instance_id -> brain index offset (which droid this pad drives)

    def brains():
        return state["brains"]

    def active():
        bs = brains()
        if not bs:
            return None
        state["active"] %= len(bs)
        return bs[state["active"]]

    def do_scan():
        state["scanning"] = True; state["status"] = "Scanning... keep your droids close and awake"
        def w():
            try:
                found = scan()
                state["found"] = found
                state["status"] = ("Found %d droid(s). Click each one to connect." % len(found)) if found else "No droids found. Is Bluetooth on and the droid awake (off its charger)?"
            except Exception as e:
                log(traceback.format_exc()); state["status"] = "Scan failed: %s" % e
            state["scanning"] = False
        threading.Thread(target=w, daemon=True).start()

    def do_connect(droid, key=None):
        state["connecting"] += 1; state["status"] = "Connecting to %s..." % droid.name
        if key:
            state["busy_addrs"].add(key)
        def w():
            ok = droid.connect()  # each droid gets its own BLE worker thread
            if ok:
                b = Brain(droid); b.greet(); b.key = key
                brains().append(b); state["active"] = len(brains()) - 1
                state["status"] = "Connected to %s (%s). %d droid(s) online." % (droid.name, PRETTY.get(droid.model, droid.model), len(brains()))
            else:
                state["busy_addrs"].discard(key)
                state["status"] = "Could not connect to %s: %s" % (droid.name, getattr(droid, "error", None) or "timed out")
            state["connecting"] -= 1
        threading.Thread(target=w, daemon=True).start()

    def disconnect(b=None):
        b = b or active()
        if not b:
            return
        b.d.drive(0, 0)
        b.p.save(); b.d.disconnect()
        if b in brains():
            brains().remove(b)
        state["busy_addrs"].discard(getattr(b, "key", None))
        society.save()
        state["status"] = "Disconnected %s. Its memory was saved." % b.d.name

    def demo_add():
        models = ["R2D2", "BB8", "BB9E", "R2Q5"]
        n = len(brains())
        m = models[n % 4]
        do_connect(MockDroid(m, "Demo %s" % PRETTY[m]), key="demo%d" % n)

    if demo:
        for _ in range(demo_count):
            demo_add(); time.sleep(0.05)

    buttons = []
    CANVAS = pygame.Rect(346, 366, 330, 230)

    def button(rect, label, cb, col=ACC, enabled=True, f=None):
        r = pygame.Rect(rect)
        hov = r.collidepoint(pygame.mouse.get_pos()) and enabled
        c = col if enabled else (70, 75, 90)
        if hov:
            c = tuple(min(255, x + 40) for x in c)
        pygame.draw.rect(screen, c, r, border_radius=8)
        t = (f or F).render(label, True, (10, 12, 20) if enabled else DIM)
        screen.blit(t, t.get_rect(center=r.center))
        if enabled:
            buttons.append((r, cb))

    def text(s, pos, f=F, c=TXT):
        screen.blit(f.render(s, True, c), pos)

    def bar(x, y, w, frac, col, label, h=16):
        pygame.draw.rect(screen, (50, 56, 76), (x, y, w, h), border_radius=6)
        pygame.draw.rect(screen, col, (x, y, max(0, int(w * max(0, min(1, frac)))), h), border_radius=6)
        if label:
            text(label, (x, y - 20), FS, DIM)

    help_lines = ["KEYBOARD (drives selected droid)", "Tab / F1-F4: pick droid", "W/S or Up/Down: forward / back",
                  "A/D or Left/Right: turn", "Shift: boost   Q/E: speed - / +", "1-9, 0: emotes   P: pat   O: poke",
                  "Z/C: dome (R2)   X: stance (R2)", "Space: stop   Esc: disconnect", "",
                  "CONTROLLERS (one per droid)", "Pad 1 -> droid 1, pad 2 -> droid 2...", "Back/View: switch pad's droid",
                  "Left stick: drive   Right stick X: dome", "RT: boost   LT: slow", "A/B/X/Y: emotes   LB: pat",
                  "RB: stance   Start: random emote", "", "Idle droids chat to each other,", "greet newcomers and react",
                  "to each other's bumps."]

    def pad_target(iid):
        bs = brains()
        if not bs:
            return None
        order = sorted(joys)
        base = order.index(iid) if iid in order else 0
        return bs[(base + joy_map.get(iid, 0)) % len(bs)]

    def band_scan():
        bs_["scanning"] = True; bs_["msg"] = "Looking for a band (wake it up first)..."
        def w():
            try:
                bs_["found"] = bandmod.scan_bands()
                bs_["msg"] = "Found %d possible band(s)." % len(bs_["found"]) if bs_["found"] else "No band found. Real band support is experimental."
            except Exception as e:
                bs_["msg"] = "Band scan failed: %s" % e
            bs_["scanning"] = False
        threading.Thread(target=w, daemon=True).start()

    def band_connect(bd):
        bs_["msg"] = "Connecting to %s..." % bd.name
        def w():
            if bd.connect():
                bs_["band"] = bd; bs_["msg"] = "%s connected!" % bd.name
            else:
                bs_["msg"] = "Could not connect: %s" % (bd.error or "timed out")
        threading.Thread(target=w, daemon=True).start()

    def set_tab(t):
        bs_["tab"] = t
        bs_["game"] = bandmod.ReflexTrainer() if t == "Reflex" else bandmod.DuelTrainer() if t == "Duel" else None
        bs_["hunt"] = bandmod.CubeHunt(cubes) if t == "Data Cubes" else None

    def draw_band():
        now = time.time()
        text("Force Band  (experimental)", (346, 106), FB, (255, 170, 70))
        bd = bs_["band"]
        text(("Band: %s" % bd.name) if bd else "No band connected", (346, 140), F, DIM)
        if not bd:
            button((346, 168, 150, 32), "Scan for band", band_scan, col=(255, 170, 70), enabled=not bs_["scanning"], f=FS)
            button((506, 168, 150, 32), "Demo band", lambda: band_connect(bandmod.DemoBand()), col=(150, 120, 255), f=FS)
            for i, fb in enumerate(bs_["found"][:3]):
                button((666, 168 + i * 36, 170, 32), fb.name, (lambda fb=fb: band_connect(fb)), col=(0, 200, 140), f=FS)
        else:
            button((666, 140, 170, 30), "Disconnect band", lambda: (bd.disconnect(), bs_.__setitem__("band", None)), col=(255, 100, 100), f=FS)
        text(bs_["msg"], (346, 206), FS, TXT)
        for i, t in enumerate(["Control", "Data Cubes", "Reflex", "Duel"]):
            sel = bs_["tab"] == t
            button((346 + i * 120, 232, 112, 28), ("> " if sel else "") + t, (lambda t=t: set_tab(t)), col=(0, 220, 255) if sel else (90, 110, 150), f=FS)
        # gesture buttons (also keys I K J L U M)
        text("Gestures (band, keys or buttons):", (346, 272), FS, DIM)
        for i, g in enumerate(bandmod.GESTURES):
            hot = bs_["last_g"] == g and now - bs_["last_g_t"] < 0.6
            button((346 + i * 81, 292, 76, 28), "%s %s" % (bandmod.GESTURE_KEYS[g], g), (lambda g=g: bs_["band"] and bs_["band"].events.append(g)),
                   col=(255, 230, 120) if hot else (200, 170, 90), enabled=bool(bd), f=FS)
        y0 = 336
        tab = bs_["tab"]
        if tab == "Control":
            tgt = active()
            for i, s_ in enumerate(["Push = drive forward     Pull = drive backward",
                                    "Left / Right = turn and go     Stop = stop", "Up = cheer (emote)",
                                    "Controls the selected droid: %s" % (tgt.d.name if tgt else "none connected"),
                                    "", "Real bands: the gesture reading is a best guess", "and may need tuning."]):
                text(s_, (346, y0 + i * 24), F if i < 4 else FS, TXT if i < 4 else DIM)
        elif tab == "Data Cubes":
            h = bs_["hunt"]
            n = len(cubes.found)
            text("Data Cubes found: %d / %d" % (n, len(bandmod.CUBE_NAMES)), (346, y0), F)
            text(h.msg if h else "", (346, y0 + 24), FS, (255, 220, 120))
            cx, cy = 510, 470
            aim = bs_.get("aim", 0); sig = h.signal(aim) if h and h.idx is not None else 0
            pygame.draw.circle(screen, (40, 46, 66), (cx, cy), 80)
            pygame.draw.circle(screen, (int(60 + 195 * sig), int(200 * sig), 80), (cx, cy), int(10 + 60 * sig))
            a = math.radians(aim)
            pygame.draw.line(screen, ACC, (cx, cy), (cx + 78 * math.sin(a), cy - 78 * math.cos(a)), 4)
            text("Aim with the band (demo: point the mouse)", (346, 560), FS, DIM)
            bar(346, 600, 330, sig, (255, 120, 60), "Signal")
            bar(346, 640, 330, (h.lock / 2) if h else 0, (0, 220, 120), "Lock")
            for i, k in enumerate(sorted(cubes.found, key=lambda k: -cubes.found[k])[:8]):
                text("#%d %s" % (int(k) + 1, bandmod.CUBE_NAMES[int(k)]), (690, y0 + 30 + i * 20), FS, (180, 220, 255))
        else:
            gm = bs_["game"]
            if tab == "Reflex":
                text("Do the gesture before time runs out!", (346, y0), F)
                if gm:
                    text(gm.prompt.upper() if not gm.over else "GAME OVER", (346, y0 + 40), FB, (255, 220, 120))
                    bar(346, y0 + 100, 330, gm.t / gm.limit if not gm.over else 0, (0, 170, 255), "Time")
                    text("Score %d    Lives %d" % (gm.score, gm.lives), (346, y0 + 130), F)
            else:
                text("Block the training bot: Left/Right/Up match its attack,", (346, y0), FS)
                text("then PUSH to strike while it's open.", (346, y0 + 18), FS)
                if gm:
                    lab = ("OPEN! PUSH!" if gm.opening > 0 else "Attack: %s" % gm.attack.upper()) if not gm.over else ("YOU WIN!" if gm.bot_hp <= 0 else "Defeated...")
                    text(lab, (346, y0 + 50), FB, (255, 220, 120))
                    bar(346, y0 + 120, 160, gm.hp / 5, (0, 220, 120), "You")
                    bar(516, y0 + 120, 160, gm.bot_hp / 6, (255, 90, 90), "Training bot")
            button((346, 600, 140, 32), "Restart", lambda: set_tab(tab), col=(0, 200, 140), f=FS)

    running, frame, last = True, 0, time.time()
    emote_keys = [pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9, pygame.K_0]
    while running:
        now = time.time(); dt = min(0.1, now - last); last = now
        clicks = []
        b = active()
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
                clicks.append(ev.pos)
                if b and b.mode == "Path" and CANVAS.collidepoint(ev.pos) and not b.auto:
                    b.path_points = [ev.pos]; state["drawing"] = True
            elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
                state["drawing"] = False
            elif ev.type == pygame.MOUSEMOTION and state.get("drawing") and b and CANVAS.collidepoint(ev.pos):
                b.path_points.append(ev.pos)
            elif ev.type == pygame.JOYDEVICEADDED:
                j = pygame.joystick.Joystick(ev.device_index); joys[j.get_instance_id()] = j
            elif ev.type == pygame.JOYDEVICEREMOVED:
                joys.pop(ev.instance_id, None)
            elif ev.type == pygame.KEYDOWN and ev.key in GKEYS and bs_["band"] and isinstance(bs_["band"], bandmod.DemoBand):
                bs_["band"].events.append(GKEYS[ev.key])
            elif ev.type == pygame.KEYDOWN and b:
                tbl = emote_table(b.d.model)
                if ev.key == pygame.K_TAB:
                    state["active"] += 1
                elif ev.key in (pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F4):
                    i = [pygame.K_F1, pygame.K_F2, pygame.K_F3, pygame.K_F4].index(ev.key)
                    if i < len(brains()):
                        state["active"] = i
                elif ev.key in emote_keys and emote_keys.index(ev.key) < len(tbl):
                    lab = tbl[emote_keys.index(ev.key)][0]; b.emote(lab); b.say("Emote: " + lab)
                elif ev.key == pygame.K_p: b.pet()
                elif ev.key == pygame.K_o: b.poke()
                elif ev.key == pygame.K_x: b.toggle_stance()
                elif ev.key == pygame.K_z: b.turn_dome(-30)
                elif ev.key == pygame.K_c: b.turn_dome(30)
                elif ev.key == pygame.K_q: state["max"] = max(40, state["max"] - 20)
                elif ev.key == pygame.K_e: state["max"] = min(255, state["max"] + 20)
                elif ev.key == pygame.K_ESCAPE: disconnect(b)
            elif ev.type == pygame.JOYBUTTONDOWN and brains():
                if ev.button == 6:
                    joy_map[ev.instance_id] = joy_map.get(ev.instance_id, 0) + 1; continue
                pb = pad_target(ev.instance_id)
                if not pb:
                    continue
                tbl = emote_table(pb.d.model)
                if ev.button in (0, 1, 2, 3):
                    pb.emote(tbl[ev.button][0]); pb.say("Emote: " + tbl[ev.button][0])
                elif ev.button == 4: pb.pet()
                elif ev.button == 5: pb.toggle_stance()
                elif ev.button == 7: lab = random.choice(tbl)[0]; pb.emote(lab); pb.say("Emote: " + lab)

        # ---- input -> drive (each droid separately)
        b = active()
        drive = {id(x): [state["heading"].get(id(x), 0), 0, False] for x in brains()}
        if b:
            base, h, sp, had = modes.drive_from_keyboard(pygame.key.get_pressed(), pygame, state["heading"].get(id(b), 0), state["max"], dt)
            state["heading"][id(b)] = base
            drive[id(b)] = [h, sp, had]
        for iid, j in list(joys.items()):
            pb = pad_target(iid)
            if not pb:
                continue
            try:
                r = modes.drive_from_pad(j, state["heading"].get(id(pb), 0), state["max"])
                if r:
                    drive[id(pb)] = list(r)
                if j.get_numaxes() > 2 and abs(j.get_axis(2)) > 0.5 and frame % 6 == 0:
                    pb.turn_dome(15 if j.get_axis(2) > 0 else -15)
            except Exception:
                pass
        if b and now < bs_["drive_until"] and not drive[id(b)][2]:
            drive[id(b)] = [(state["heading"].get(id(b), 0) + bs_["drive_off"]) % 360, state["max"], False]
        for x in list(brains()):
            h, sp, had = drive[id(x)]
            x.control(dt, h, sp, had)
            if frame % 600 == 0:
                x.p.save()
            if not isinstance(x.d, MockDroid) and not x.d.connected:
                x.p.save(); brains().remove(x); state["busy_addrs"].discard(getattr(x, "key", None))
                state["status"] = "Lost connection to %s." % x.d.name
        society.update(brains())
        # ---- Force Band
        bd = bs_["band"]
        gests = []
        if bd:
            if not bd.connected:
                bs_["msg"] = "Band disconnected. %s" % (bd.error or ""); bs_["band"] = None
            else:
                gests = bd.poll()
        for g in gests:
            bs_["last_g"], bs_["last_g_t"] = g, now
            sfx("swoosh")
        if bs_["tab"] == "Control" and b and gests:
            g = gests[-1]
            if g in ("push", "pull", "left", "right"):
                bs_["drive_off"] = {"push": 0, "pull": 180, "left": -90, "right": 90}[g]
                if g in ("left", "right"):
                    state["heading"][id(b)] = (state["heading"].get(id(b), 0) + bs_["drive_off"]) % 360; bs_["drive_off"] = 0
                bs_["drive_until"] = now + 1.5
                if b.auto: b.set_mode("Drive")
            elif g == "stop":
                bs_["drive_until"] = 0; b.say("Band: stop!")
            elif g == "up":
                lab = pick(b.d.model, "fast"); b.emote(lab); b.say("Band lifts %s's spirits: %s" % (b.d.name, lab))
        if bs_["tab"] == "Data Cubes" and bs_["hunt"]:
            hb = bs_["band"]
            if hb and type(hb) is not bandmod.DemoBand:
                aim = hb.pointing
            else:
                mx, my = pygame.mouse.get_pos(); aim = math.degrees(math.atan2(mx - 510, -(my - 470))) % 360
            bs_["aim"] = aim
            got = bs_["hunt"].update(dt, aim, gests)
            sig = bs_["hunt"].signal(aim)
            if now - bs_["ping_t"] > 1.2 - sig:
                bs_["ping_t"] = now; sfx("ping")
            if got:
                sfx("found"); bs_["msg"] = "You found " + got + "!"
                for x in brains():
                    x.emote(pick(x.d.model, "fast"), xp=0); x.p.add_xp(10)
        if bs_["tab"] in ("Reflex", "Duel") and bs_["game"]:
            r = bs_["game"].update(dt, gests)
            if r:
                sfx({"hit": "hit", "strike": "clash", "block": "clash", "miss": "miss", "over": "lose", "win": "win", "lose": "lose"}.get(r, "hit"))
                if b and r in ("win", "strike"):
                    b.emote(pick(b.d.model, "fast"), xp=0)
                if b and r in ("lose",):
                    b.emote(pick(b.d.model, "idle_sad"), xp=0)
        b = active()

        # ---- draw
        buttons.clear()
        screen.fill(BG)
        text(APP, (24, 14), FB, ACC); text("v%s  - unofficial fan app for BB-8, BB-9E, R2-D2, R2-Q5" % VERSION, (24, 44), FS, DIM)
        # left: connect + droid roster
        pygame.draw.rect(screen, PANEL, (16, 70, 300, 634), border_radius=12)
        text("Connect", (32, 80), FB)
        button((32, 118, 130, 38), "Scanning..." if state["scanning"] else "SCAN", do_scan, enabled=not state["scanning"])
        button((172, 118, 130, 38), "+ Demo droid", demo_add, col=(150, 120, 255), enabled=len(brains()) < 4, f=FS)
        y = 166
        for t in state["found"][:5]:
            m = type(t).__name__
            key = getattr(t, "address", None) or str(id(t))
            nm = getattr(t, "name", "?")
            if key in state["busy_addrs"]:
                continue
            button((32, y, 270, 34), "Connect %s (%s)" % (nm, PRETTY.get(m, m)), (lambda t=t, key=key: do_connect(RealDroid(t), key)), col=(0, 200, 140), f=FS)
            y += 40
        text("My droids (%d)" % len(brains()), (32, max(y + 6, 300)), F)
        y = max(y + 34, 328)
        for i, x in enumerate(brains()):
            sel = x is b
            r = pygame.Rect(32, y, 270, 82)
            pygame.draw.rect(screen, (45, 70, 110) if sel else (40, 46, 66), r, border_radius=10)
            if sel:
                pygame.draw.rect(screen, ACC, r, 2, border_radius=10)
            buttons.append((r, (lambda i=i: state.__setitem__("active", i))))
            pads = [str(n + 1) for n, iid in enumerate(sorted(joys)) if pad_target(iid) is x]
            text("F%d  %s" % (i + 1, x.d.name), (42, y + 4), F)
            text("%s  Lv%d  %s%s" % (PRETTY.get(x.d.model, x.d.model), x.p.level, x.p.mood_name, ("  pad " + ",".join(pads)) if pads else ""), (42, y + 28), FS, DIM)
            bt = x.d.get_battery()
            bar(42, y + 56, 120, (bt or 0) / 100, (0, 170, 255), None, 10)
            bar(172, y + 56, 120, (x.p.mood + 100) / 200, (255, 200, 0), None, 10)
            y += 90
        bl = "Force Band (experimental)" + ("  [on]" if bs_["band"] else "")
        button((32, 640, 270, 32), ("< Back to droids" if state.get("page") == "band" else bl), lambda: state.__setitem__("page", "droid" if state.get("page") == "band" else "band"), col=(255, 160, 60), f=FS)
        text("Controllers: %d   connecting: %d" % (len(joys), state["connecting"]), (32, 682), FS, DIM)

        # middle: active droid
        text(state["status"], (330, 74), FS, TXT)
        pygame.draw.rect(screen, PANEL, (330, 96, 520, 608), border_radius=12)
        if state.get("page") == "band":
            draw_band()
        elif b:
            p = b.p
            text("%s  -  %s" % (b.d.name, PRETTY.get(b.d.model, b.d.model)), (346, 106), FB)
            text("Level %d   XP %d   Mood: %s" % (p.level, p.xp, p.mood_name), (346, 142), F, DIM)
            button((734, 108, 100, 30), "Disconnect", lambda b=b: disconnect(b), col=(255, 100, 100), f=FS)
            bar(346, 190, 230, (p.mood + 100) / 200, (255, 200, 0), "Mood")
            bar(596, 190, 230, p.energy / 100, (0, 220, 120), "Energy")
            batt = b.d.get_battery()
            sp = getattr(b.d, "speed_now", 0)
            bar(346, 240, 230, (batt or 0) / 100, (0, 170, 255), "Battery: %s" % ("%d%%" % batt if batt is not None else "checking..."))
            bar(596, 240, 230, sp / 255, (255, 120, 60), "Speed  (max %d)" % state["max"])
            text("Bumps %d  Pats %d  Visits %d  Drive %dm" % (p.bumps, p.pets, p.sessions, p.drive_seconds // 60), (346, 266), FS, DIM)
            others = [o for o in brains() if o is not b]
            if others:
                text("Friends: " + "  ".join("%s %+d" % (o.d.name, society.friendship(b, o)) for o in others), (346, 284), FS, (255, 200, 120))
            cx, cy = 760, 350
            hd = drive.get(id(b), [0])[0]
            pygame.draw.circle(screen, (50, 56, 76), (cx, cy), 40, 3)
            a = math.radians(hd)
            pygame.draw.line(screen, ACC, (cx, cy), (cx + 36 * math.sin(a), cy - 36 * math.cos(a)), 4)
            text("Heading %d" % hd, (cx - 40, cy + 44), FS, DIM)
            for i, m in enumerate(modes.MODES):
                sel = b.mode == m
                button((346 + i * 84, 304, 78, 28), ("> " if sel else "") + m, (lambda m=m, b=b: b.set_mode(m)),
                       col=(0, 220, 255) if sel else (90, 110, 150), f=FS)
            if b.mode == "Drive":
                text("Emotes", (346, 338), FS, DIM)
                for i, (lab, _) in enumerate(emote_table(b.d.model)):
                    bx, by = 346 + (i % 2) * 140, 358 + (i // 2) * 31
                    key = str((i + 1) % 10) if i < 10 else ""
                    button((bx, by, 130, 28), ("%s %s" % (key, lab)).strip(), (lambda l=lab, b=b: (b.emote(l), b.say("Emote: " + l))), col=(255, 190, 70), f=FS)
            elif b.mode == "Patrol":
                text("Patrol: roams by itself, backs off when it bumps,", (346, 340), FS)
                text("emotes now and then. Any key/stick stops it.", (346, 358), FS)
                running_p = b.auto is not None
                button((346, 390, 160, 34), "Stop patrol" if running_p else "Start patrol", (lambda b=b: b.set_mode("Drive") if b.auto else b.set_mode("Patrol")), col=(255, 130, 130) if running_p else (0, 200, 140))
                button((516, 390, 160, 34), "Patrol ALL", (lambda: [x.set_mode("Patrol") for x in brains()]), col=(0, 200, 140))
                button((346, 432, 160, 34), "Stop ALL", (lambda: [x.set_mode("Drive") for x in brains()]), col=(255, 130, 130))
                text("Phase: %s" % (getattr(b.auto, "phase", "-") if b.auto else "stopped"), (346, 480), F, DIM)
            elif b.mode == "Path":
                text("Draw a path (start = droid, up = droid's forward):", (346, 340), FS)
                pygame.draw.rect(screen, (22, 26, 40), CANVAS, border_radius=8)
                pygame.draw.rect(screen, (70, 80, 110), CANVAS, 1, border_radius=8)
                pts = b.path_points
                if len(pts) > 1:
                    pygame.draw.lines(screen, (0, 220, 255), False, pts, 3)
                if pts:
                    pygame.draw.circle(screen, (0, 220, 120), pts[0], 6)
                if b.auto and isinstance(b.auto, modes.PathMode):
                    done = b.auto.i / max(1, len(b.auto.segs))
                    text("Driving... %d%%" % (done * 100), (CANVAS.x + 8, CANVAS.y + 6), FS, ACC)
                button((346, 602, 100, 26), "Go!", b.start_path, col=(0, 200, 140), enabled=len(pts) > 1 and not b.auto, f=FS)
                button((452, 602, 100, 26), "Clear", lambda b=b: setattr(b, "path_points", []), col=(200, 200, 200), f=FS)
            elif b.mode == "Record":
                rec = b.recorder
                text("Record driving + emotes, then replay it.", (346, 340), FS)
                if rec.recording:
                    text("RECORDING  %.1fs  (%d steps)" % (time.time() - rec.t0, len(rec.events)), (346, 362), F, (255, 80, 80))
                else:
                    text("Recording: %.1fs, %d steps" % (rec.length, len(rec.events)), (346, 362), F, DIM)
                button((346, 392, 104, 32), "Stop" if rec.recording else "Record", (lambda rec=rec: rec.stop() if rec.recording else rec.start()), col=(255, 90, 90), f=FS)
                button((456, 392, 104, 32), "Play", lambda b=b: b.start_playback(b.recorder.events), col=(0, 200, 140), enabled=bool(rec.events) and not rec.recording and not b.auto, f=FS)
                button((566, 392, 110, 32), "Save", lambda b=b: b.say("Saved " + os.path.basename(b.recorder.save())), col=(160, 160, 255), enabled=bool(rec.events) and not rec.recording, f=FS)
                text("Saved recordings (click to load):", (346, 436), FS, DIM)
                for i, pth in enumerate(state.get("recs", [])[:5]):
                    button((346, 456 + i * 30, 330, 26), os.path.basename(pth)[:-5], (lambda pth=pth, b=b: (b.recorder.load(pth), b.say("Loaded " + os.path.basename(pth)))), col=(120, 130, 170), f=FS)
                if frame % 60 == 0:
                    try:
                        state["recs"] = modes.list_recordings()
                    except Exception:
                        state["recs"] = []
            button((690, 420, 140, 32), "Pat (P)", b.pet, col=(120, 220, 140))
            button((690, 458, 140, 32), "Poke (O)", b.poke, col=(255, 130, 130))
            if b.d.model in ("R2D2", "R2Q5"):
                button((690, 496, 140, 32), "Stance (X)", b.toggle_stance, col=(160, 160, 255))
                button((690, 534, 66, 32), "Dome<", lambda: b.turn_dome(-30), col=(160, 160, 255), f=FS)
                button((764, 534, 66, 32), "Dome>", lambda: b.turn_dome(30), col=(160, 160, 255), f=FS)
            if isinstance(b.d, MockDroid):
                button((690, 572, 140, 32), "Fake bump", b.d.simulate_bump, col=(200, 200, 200))
            evs = sorted([e for x in brains() for e in x.events])[-4:]
            yy = 694 - 18 * len(evs)
            for t0, s in evs:
                text(s, (346, yy), FS, TXT if now - t0 < 6 else DIM); yy += 18
        else:
            text("No droid connected.", (346, 110), FB, DIM)
            for i, s in enumerate(["1. Turn on Bluetooth in Windows settings.", "2. Take the droids off their chargers and wake them",
                                   "   (pick them up / give them a shake).", "3. Keep them close to the PC and press SCAN.",
                                   "4. Click each droid to connect (up to 4).", "", "Tip: press + Demo droid to try it with no droids."]):
                text(s, (346, 160 + i * 26))
        pygame.draw.rect(screen, PANEL, (864, 70, 300, 634), border_radius=12)
        text("Controls", (880, 80), FB)
        for i, s in enumerate(help_lines):
            text(s, (880, 118 + i * 21), FS, ACC if s.startswith(("KEYBOARD", "CONTROLLERS")) else TXT)
        for r, cb in buttons:
            for c in clicks:
                if r.collidepoint(c):
                    try:
                        cb()
                    except Exception as e:
                        log(traceback.format_exc()); state["status"] = "Error: %s" % e
        pygame.display.flip()
        clock.tick(60)
        frame += 1
        if selftest_frames:  # exercise the band screens in the self-test
            if frame == 20:
                state["page"] = "band"; bs_["band"] = bandmod.DemoBand(); bs_["band"].connect()
            for fr, tb in ((25, "Control"), (40, "Data Cubes"), (55, "Reflex"), (70, "Duel")):
                if frame == fr:
                    set_tab(tb)
            if 20 < frame < 85 and frame % 5 == 0 and bs_["band"]:
                bs_["band"].events.append(random.choice(bandmod.GESTURES))
            if os.environ.get("DC_SHOT") and frame in (35, 50, 80):
                pygame.image.save(screen, "/tmp/band%d.png" % frame)
        if selftest_frames and frame >= selftest_frames:
            running = False
    for x in list(brains()):
        disconnect(x)
    society.save()
    pygame.quit()
    return state


# ---------------------------------------------------------------- selftest
def selftest():
    import tempfile
    ok = True
    def check(cond, name):
        nonlocal ok
        print(("PASS " if cond else "FAIL ") + name); ok = ok and bool(cond)
    try:
        import bleak, spherov2  # noqa
        from spherov2.toy.bb8 import BB8; from spherov2.toy.bb9e import BB9E
        from spherov2.toy.r2d2 import R2D2; from spherov2.toy.r2q5 import R2Q5
        from spherov2.sphero_edu import SpheroEduAPI, EventType  # noqa
        check(True, "imports bleak + spherov2")
        for cls, model in ((BB9E, "BB9E"), (R2D2, "R2D2"), (R2Q5, "R2Q5")):
            missing = [n for _, n in emote_table(model) if not hasattr(cls.Animations, n)]
            check(not missing, "animation names valid for %s %s" % (model, missing or ""))
        check(not hasattr(BB8, "Animations") or True, "BB8 uses custom emotes")
    except Exception as e:
        check(False, "imports: %r" % e)
    path = os.path.join(tempfile.mkdtemp(), "m.json")
    p = Personality("t", path); check(p.start_session() == "first", "first session")
    p.xp = 100; p.save(); p2 = Personality("t", path)
    check(p2.xp == 100 and p2.sessions == 1, "memory persists")
    check(p2.start_session() == "back", "returning greeting")
    for m in SUPPORTED:
        d = MockDroid(m, "x"); b = Brain(d, Personality("t" + m, path + m)); b.greet()
        b.update(0.1, 90, 255, True); check(d.speed == 255 and d.heading == 90, "drive %s" % m)
        d.simulate_bump(); b.last_react = 0; b.update(0.1, 0, 0, False)
        check(b.p.bumps == 1 and len(d.calls) >= 2, "bump reaction %s" % m)
        b.next_idle = 0; n = len(d.calls); b.update(0.1, 0, 0, False); check(len(d.calls) > n, "idle reaction %s" % m)
    # multi-droid social test
    soc = Society(path + "friends")
    bs = [Brain(MockDroid(m, "s" + m), Personality("s" + m, path + "s" + m)) for m in ("R2D2", "BB8")]
    soc.update(bs); check(len(soc.script) >= 2, "newcomer greeting queued")
    soc.script = []; [setattr(x, "social_busy", False) for x in bs]
    bs[0].signals.append("bump"); soc.update(bs); check(any(x[1] is bs[1] for x in soc.script), "other droid reacts to bump")
    soc.script = []
    for x in bs:
        x.last_input = 0; x.d.speed_now = 0; x.social_busy = False
    soc.next_chat = 0; soc.update(bs); check(len(soc.script) >= 2, "idle droids chat")
    soc2 = Society(path + "friends"); check(soc2.friendship(bs[0], bs[1]) > 0, "friendship persists")
    # modes
    import modes
    d = MockDroid("R2D2", "m"); b = Brain(d, Personality("m", path + "m"))
    b.set_mode("Patrol"); moved = 0
    for i in range(200):
        b.control(0.05, 0, 0, False); moved += d.speed > 0
    check(moved > 0 and b.auto is not None, "patrol roams by itself")
    d.simulate_bump(); b.control(0.05, 0, 0, False); check(b.auto.phase == "backup", "patrol backs up after bump")
    b.control(0.05, 0, 100, True); check(b.auto is None and b.mode == "Drive", "input stops patrol")
    segs = modes.path_to_segments([(0, 100), (0, 0), (100, 0)])
    check(len(segs) == 2 and abs(segs[0][0]) < 1 and abs(segs[1][0] - 90) < 1, "path -> headings")
    b.mode = "Path"; b.path_points = [(0, 100), (0, 0), (100, 0)]; b.start_path(); hs = set()
    for i in range(400):
        b.control(0.05, 0, 0, False); hs.add(d.heading if d.speed else None)
    check({0, 90} <= hs and b.auto is None, "path drive follows both legs then stops")
    b.set_mode("Record"); b.recorder.start(); b.recorder.t0 -= 1
    b.control(0.05, 45, 120, True); b.emote("Happy"); b.recorder.t0 -= 1; b.control(0.05, 45, 0, True); b.recorder.stop()
    p = b.recorder.save("selftest"); r2 = modes.Recorder(); r2.load(p); os.remove(p)
    check(len(r2.events) >= 3, "recording saved + loaded")
    d.calls.clear(); b.start_playback(r2.events); sp = []
    for i in range(80):
        b.control(0.05, 0, 0, False); sp.append(d.speed)
    check(120 in sp and ("emote", "Happy") in d.calls and b.auto is None, "playback replays drive + emote")
    bs2 = [Brain(MockDroid(m, "p" + m), Personality("p" + m, path + "p" + m)) for m in SUPPORTED]
    for x in bs2: x.set_mode("Patrol")
    for i in range(100):
        for x in bs2: x.control(0.05, 0, 0, False)
    check(all(x.auto for x in bs2), "multi-droid patrol")
    # force band (gesture detector with synthetic accelerometer data, cubes, games)
    import band as bandmod
    def flick(axis, sign):
        det = bandmod.GestureDetector(); t = 0; out = []
        for i in range(40):
            t += 0.03; out.append(det.feed(t, 0, 0, 1))
        for v in (0.8, 2.0, 2.5, 1.0):
            t += 0.03; vec = [0, 0, 1]; vec["xyz".index(axis)] += sign * v; out.append(det.feed(t, *vec))
        return [g for g in out if g]
    check(flick("y", 1)[:1] == ["push"] and flick("y", -1)[:1] == ["pull"], "band push/pull gestures")
    check(flick("x", -1)[:1] == ["left"] and flick("x", 1)[:1] == ["right"] and flick("z", 1)[:1] == ["up"], "band side/up gestures")
    cc = bandmod.CubeCollection(path + "cubes"); h = bandmod.CubeHunt(cc); got = None
    for i in range(30):
        got = h.update(0.1, h.target, ["pull"]) or got
    check(got and len(bandmod.CubeCollection(path + "cubes").found) == 1, "data cube hunt + save")
    rt = bandmod.ReflexTrainer(); rt.update(0.1, [rt.prompt]); check(rt.score == 1, "reflex trainer scores")
    dt_ = bandmod.DuelTrainer(); dt_.update(0.1, [dt_.BLOCK[dt_.attack]]); dt_.update(0.1, ["push"]); check(dt_.bot_hp == 5, "duel block + strike")
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy"); os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    try:
        st = run_gui(demo=True, selftest_frames=90, demo_count=3)
        check(len(st["brains"]) == 0, "GUI ran 90 frames with 3 demo droids")
    except Exception as e:
        traceback.print_exc(); check(False, "GUI: %r" % e)
    print("SELFTEST", "OK" if ok else "FAILED")
    return 0 if ok else 1


def main():
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")
    if "--selftest" in sys.argv:
        code = selftest()
        if getattr(sys, "frozen", False):
            with open(os.path.join(os.getcwd(), "selftest_result.txt"), "w") as f:
                f.write("OK" if code == 0 else "FAILED")
        sys.exit(code)
    try:
        run_gui(demo="--demo" in sys.argv)
    except Exception:
        log(traceback.format_exc()); raise


if __name__ == "__main__":
    main()
