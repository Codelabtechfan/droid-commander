"""Battery % from droid voltage using a Li-ion discharge curve (non-linear), smoothed, with load compensation."""
CURVE = [(3.30, 0), (3.50, 5), (3.61, 10), (3.67, 20), (3.71, 30), (3.75, 40), (3.80, 50),
         (3.85, 60), (3.92, 70), (4.00, 80), (4.10, 90), (4.18, 100)]
STATE_NAMES = {"CHARGING": "Charging", "CHARGED": "Charged", "LOW": "Low", "CRITICAL": "Critical"}


def cells_for(voltage):
    return 2 if voltage > 5.5 else 1  # in case a droid reports a 2-cell pack voltage


def voltage_to_percent(v, load_frac=0.0):
    """load_frac 0..1 = how hard the motors were working; voltage sags under load so we add some back."""
    v = v / cells_for(v) + 0.10 * max(0.0, min(1.0, load_frac))
    if v <= CURVE[0][0]:
        return 0
    for (v0, p0), (v1, p1) in zip(CURVE, CURVE[1:]):
        if v <= v1:
            return int(round(p0 + (p1 - p0) * (v - v0) / (v1 - v0)))
    return 100


class BatteryGauge:
    def __init__(self):
        self.percent = None
        self.state = ""
        self.source = ""

    def update(self, voltage=None, percent=None, state=None, load_frac=0.0):
        if state is not None:
            self.state = STATE_NAMES.get(getattr(state, "name", str(state)).upper(), "")
        if percent is not None:
            new, self.source = max(0, min(100, int(percent))), "droid"
        elif voltage:
            new, self.source = voltage_to_percent(voltage, load_frac), "voltage"
        else:
            return self.percent
        if self.percent is None or self.state in ("Charging", "Charged") or self.source == "droid":
            self.percent = new
        else:
            # smooth, and don't let it creep upward from voltage noise while discharging
            sm = self.percent * 0.7 + new * 0.3
            self.percent = int(round(min(sm, self.percent + 1)))
        return self.percent

    def label(self):
        if self.percent is None:
            return "checking..."
        return "%d%%%s" % (self.percent, (" (%s)" % self.state) if self.state else "")
