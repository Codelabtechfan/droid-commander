"""Read-only Force Band probe. Lists the band's BLE services/characteristics, reads every readable one,
listens to notifications, and sends ONLY 'get'/query packets (versions, board info, supported devices, battery).
Never writes memory, config, settings or firmware. Output: band_probe.txt + log.txt."""
import asyncio, os, re, time

V2_UUID = "00010002-574f-4f20-5370-6865726f2121"          # API v2 command/response (droids, maybe band)
V2_UNLOCK = "00020005-574f-4f20-5370-6865726f2121"        # anti-DoS unlock (same string the official apps send)
V1_SEND = "22bb746f-2ba1-7554-2d6f-726568705327"          # API v1 command (BB-8 style)
V1_UNLOCK = "22bb746f-2bbd-7554-2d6f-726568705327"
# (did, cid, name) - every entry is a documented read-only GET
V2_QUERIES = [(16, 1, "api protocol version"), (16, 5, "supported DIDs"),
              (17, 0, "main app version"), (17, 1, "bootloader version"), (17, 3, "board revision"),
              (17, 6, "mac address"), (17, 18, "model number"), (17, 19, "stats id"), (17, 31, "processor name"),
              (17, 32, "boot reason"), (17, 33, "last error info"), (17, 40, "3-char SKU"), (17, 51, "manufacturing date"),
              (17, 56, "SKU"), (17, 57, "uptime ms"), (17, 58, "event log status"),
              (19, 3, "battery voltage"), (19, 4, "battery state")]
V1_QUERIES = [(0x00, 0x02, "get versions"), (0x00, 0x11, "get bluetooth info"), (0x00, 0x20, "get power state"),
              (0x02, 0x36, "get permanent option flags")]
ALLOWED_V2 = {(d, c) for d, c, _ in V2_QUERIES}
ALLOWED_V1 = {(d, c) for d, c, _ in V1_QUERIES}


def v2_packet(did, cid, seq):
    assert (did, cid) in ALLOWED_V2, "not a whitelisted read-only query"
    body = bytearray([0x0A, did, cid, seq & 0xFF])
    body.append(0xFF - (sum(body) & 0xFF))
    out = bytearray([0x8D])
    for c in body:
        if c in (0xAB, 0x8D, 0xD8):
            out += bytes([0xAB, {0xAB: 0x23, 0x8D: 0x05, 0xD8: 0x50}[c]])
        else:
            out.append(c)
    out.append(0xD8)
    return out


def v1_packet(did, cid, seq):
    assert (did, cid) in ALLOWED_V1, "not a whitelisted read-only query"
    body = bytearray([did, cid, seq & 0xFF, 1])
    return bytearray([0xFF, 0xFF]) + body + bytearray([0xFF - (sum(body) & 0xFF)])


def fmt(data):
    b = bytes(data)
    return "%s | %s" % (b.hex(" "), "".join(chr(x) if 32 <= x < 127 else "." for x in b))


def is_band_name(n):
    from band import KNOWN_DROID_PREFIXES
    n = n or ""
    return bool(re.match(r"^[A-Z0-9]{2}-[0-9A-F]{4}$", n) and not n.startswith(KNOWN_DROID_PREFIXES)) or "band" in n.lower() or "force" in n.lower()


async def _probe(out, address=None, scan_time=6.0, listen=4.0):
    import bleak
    if not address:
        out("Scanning %.0fs for a Force Band..." % scan_time)
        devs = await bleak.BleakScanner.discover(scan_time)
        for d in devs:
            out("  seen: %s  %s" % (d.address, d.name))
        cands = [d for d in devs if is_band_name(d.name)]
        if not cands:
            out("No Force Band found. Wake it (press the button) and try again.")
            return False
        address = cands[0].address
        out("Probing %s (%s)" % (cands[0].name, address))
    try:
        cl = bleak.BleakClient(address, timeout=15.0, winrt={"use_cached_services": False})
    except TypeError:
        cl = bleak.BleakClient(address, timeout=15.0)
    async with cl:
        await asyncio.sleep(1.0)
        chars = []
        out("== SERVICES ==")
        for s in cl.services:
            out("SERVICE %s  (%s)" % (s.uuid, s.description))
            for c in s.characteristics:
                chars.append(c)
                out("  CHAR %s  handle=%s  props=%s  (%s)" % (c.uuid, c.handle, ",".join(c.properties), c.description))
                for dsc in c.descriptors:
                    out("    DESC %s handle=%s" % (dsc.uuid, dsc.handle))
        out("== READS ==")
        for c in chars:
            if "read" in c.properties:
                try:
                    out("READ %s: %s" % (c.uuid, fmt(await cl.read_gatt_char(c))))
                except Exception as e:
                    out("READ %s failed: %r" % (c.uuid, e))
        out("== NOTIFICATIONS ==")
        subs = []
        for c in chars:
            if "notify" in c.properties or "indicate" in c.properties:
                try:
                    await cl.start_notify(c, (lambda u: (lambda _h, d: out("NOTIFY %s: %s" % (u, fmt(d)))))(c.uuid))
                    subs.append(c); out("subscribed %s" % c.uuid)
                except Exception as e:
                    out("subscribe %s failed: %r" % (c.uuid, e))
        await asyncio.sleep(listen)
        uu = {c.uuid.lower(): c for c in chars}
        if V2_UNLOCK in uu:
            out("== UNLOCK (session handshake only, same as official app) ==")
            try:
                await cl.write_gatt_char(uu[V2_UNLOCK], b"usetheforce...band", True)
            except Exception as e:
                out("unlock failed: %r" % e)
            await asyncio.sleep(0.5)
        if V2_UUID in uu:
            out("== API v2 QUERIES (read-only GETs) ==")
            for i, (d, c, name) in enumerate(V2_QUERIES):
                p = v2_packet(d, c, i)
                out("SEND v2 did=%d cid=%d (%s): %s" % (d, c, name, p.hex(" ")))
                try:
                    await cl.write_gatt_char(uu[V2_UUID], p, True)
                except Exception as e:
                    out("  write failed: %r" % e)
                await asyncio.sleep(0.6)
        if V1_SEND in uu:
            out("== API v1 QUERIES (read-only GETs) ==")
            if V1_UNLOCK in uu:
                try:
                    await cl.write_gatt_char(uu[V1_UNLOCK], b"011i3", True)
                except Exception as e:
                    out("v1 unlock failed: %r" % e)
            for i, (d, c, name) in enumerate(V1_QUERIES):
                p = v1_packet(d, c, i)
                out("SEND v1 did=%d cid=%d (%s): %s" % (d, c, name, p.hex(" ")))
                try:
                    await cl.write_gatt_char(uu[V1_SEND], p, True)
                except Exception as e:
                    out("  write failed: %r" % e)
                await asyncio.sleep(0.6)
        await asyncio.sleep(listen)
        for c in subs:
            try:
                await cl.stop_notify(c)
            except Exception:
                pass
    return True


def run_probe(data_dir, log=print, address=None):
    """Blocking. Returns path of band_probe.txt."""
    lines = []
    def out(s):
        lines.append("%s  %s" % (time.strftime("%H:%M:%S"), s))
    out("===== FORCE BAND PROBE START (read-only) =====")
    try:
        asyncio.run(_probe(out, address))
    except Exception as e:
        import traceback
        out("PROBE ERROR: %r" % e); out(traceback.format_exc())
    out("===== FORCE BAND PROBE END =====")
    path = os.path.join(data_dir, "band_probe.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    for ln in lines:
        log(ln)
    return path
