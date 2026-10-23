"""Turning audio into a sound the game plays: 16-bit samples -> DSP-ADPCM -> a .bfwav file.

DSP-ADPCM is the format every voice in Mario Kart 8 Deluxe uses: 4 bits a sample, 14 samples to an 8-byte frame, and each
frame names one of 8 predictor pairs (kept in the sound's header) plus a scale. voice_audio.py decodes it; this is the other
direction. The decoder is followed sample by sample while encoding (same integer arithmetic), so what the encoder measures
is exactly what the game will hear.

The .bfwav layout - header, INFO block with each channel's coefficients, DATA block with every channel's frames - follows the
game's own voice files, read off real ones (mono and stereo): make_fwav() called with silence gives back, byte for byte, the
silent sound a mod known to work on a Switch uses (see voice_edit.SILENT_FWAV, and the tests).

Pure Python, no dependencies. A few seconds of audio take a few seconds to encode.
"""
import math
import struct
from array import array


class EncodeError(Exception):
    pass


def _solve2(a, b, c, p, q):
    """Solve [[a, b], [b, c]] x = [p, q]; None when the matrix is (nearly) singular."""
    det = a * c - b * b
    if det <= 1e-9 * (abs(a * c) + 1.0):
        return None
    return ((p * c - q * b) / det, (a * q - b * p) / det)


def coefficients(samples) -> list:
    """Eight predictor pairs [(c1, c2)] as integers (1.11 fixed point) chosen for these samples: the best two-tap predictor is
    worked out for every 14-sample frame, then the frames are grouped into eight (start with one group; split every group in
    two and let each frame move to the group that predicts it best, three times over) and each group's pair is the best one
    for all of its frames."""
    n = len(samples)
    stats = []                                   # per frame: (r11, r12, r22, p1, p2, e0) - what the predictor's error depends on
    for f in range((n + 13) // 14):
        base = f * 14
        r11 = r12 = r22 = p1 = p2 = e0 = 0.0
        h1 = samples[base - 1] if base >= 1 else 0
        h2 = samples[base - 2] if base >= 2 else 0
        for i in range(base, min(base + 14, n)):
            x = samples[i]
            r11 += h1 * h1
            r12 += h1 * h2
            r22 += h2 * h2
            p1 += x * h1
            p2 += x * h2
            e0 += x * x
            h2 = h1
            h1 = x
        stats.append((r11, r12, r22, p1, p2, e0))
    live = [s for s in stats if s[5] > 56.0]     # frames with something in them
    if not live:
        return [(0, 0)] * 8
    tot = [sum(s[k] for s in live) for k in range(6)]
    centers = [_solve2(tot[0], tot[1], tot[2], tot[3], tot[4]) or (0.0, 0.0)]

    def cost(s, c):
        return s[5] - 2 * (c[0] * s[3] + c[1] * s[4]) + c[0] * c[0] * s[0] + 2 * c[0] * c[1] * s[1] + c[1] * c[1] * s[2]

    while len(centers) < 8:
        centers = [(c[0] + d, c[1] + d) for c in centers for d in (0.03, -0.03)]
        for _ in range(5):
            groups = [[] for _ in centers]
            for s in live:
                groups[min(range(len(centers)), key=lambda k: cost(s, centers[k]))].append(s)
            for k, g in enumerate(groups):
                if g:
                    sol = _solve2(*(sum(s[j] for s in g) for j in (0, 1, 2, 3, 4)))
                    if sol:
                        centers[k] = sol
    return [(max(-32768, min(32767, round(c1 * 2048))), max(-32768, min(32767, round(c2 * 2048)))) for c1, c2 in centers]


def _try_scale(x, h1, h2, c1, c2, exp):
    """Encode one frame at scale 2**exp: (every value fits, squared error, nibbles, last two decoded samples)."""
    scale = 1 << exp
    half, den = scale << 10, scale << 11
    ok, err, nibs, a, b = True, 0, [], h1, h2
    for v in x:
        pred = c1 * a + c2 * b
        q = ((v << 11) - pred + half) // den
        if q > 7:
            q, ok = 7, False
        elif q < -8:
            q, ok = -8, False
        s = (((q * scale) << 11) + 1024 + pred) >> 11
        s = 32767 if s > 32767 else (-32768 if s < -32768 else s)
        err += (v - s) * (v - s)
        nibs.append(q & 15)
        b = a
        a = s
    return ok, err, nibs, a, b


def _encode_frame(x, h1, h2, coefs, candidates):
    """(header byte, 7 data bytes, last two decoded samples) for one frame: of the candidate predictors, the one that leaves the
    least error, each at the finest scale at which every 4-bit value still fits."""
    best = None
    for idx in candidates:
        c1, c2 = coefs[idx]
        a, b, worst = h1, h2, 0
        for v in x:
            e = abs(v - ((c1 * a + c2 * b) >> 11))
            worst = e if e > worst else worst
            b = a
            a = v
        exp = 0
        while exp < 15 and (worst >> exp) > 7:
            exp += 1
        r = _try_scale(x, h1, h2, c1, c2, exp)
        while not r[0] and exp < 15:
            exp += 1
            r = _try_scale(x, h1, h2, c1, c2, exp)
        while r[0] and exp > 0:
            lower = _try_scale(x, h1, h2, c1, c2, exp - 1)
            if not lower[0]:
                break
            exp, r = exp - 1, lower
        if best is None or r[1] < best[0]:
            best = (r[1], idx, exp, r[2], r[3], r[4])
    _err, idx, exp, nibs, a, b = best
    nibs = nibs + [0] * (14 - len(nibs))
    return (idx << 4) | exp, bytes((nibs[2 * i] << 4) | nibs[2 * i + 1] for i in range(7)), a, b


def encode_channel(samples) -> tuple:
    """([(c1, c2)] * 8, frame bytes) for one channel of 16-bit samples."""
    coefs = coefficients(samples)
    out = bytearray()
    h1 = h2 = 0
    for f in range((len(samples) + 13) // 14):
        x = list(samples[f * 14:f * 14 + 14])
        if not any(x) and not h1 and not h2:
            out += b"\0" * 8                        # silence stays silence: predictor 0, scale 0, all zero
            continue

        def open_loop(i, x=x, a0=h1, b0=h2):
            c1, c2 = coefs[i]
            a, b, e = a0, b0, 0
            for v in x:
                d = v - ((c1 * a + c2 * b) >> 11)
                e += d * d
                b = a
                a = v
            return e

        header, body, h1, h2 = _encode_frame(x, h1, h2, coefs, sorted(range(8), key=open_loop)[:2])
        out.append(header)
        out += body
    return coefs, bytes(out)


def make_fwav(rate: int, channels_pcm: list) -> bytes:
    """A .bfwav sound (little-endian, DSP-ADPCM, no loop) from per-channel 16-bit samples."""
    nch = len(channels_pcm)
    n = len(channels_pcm[0]) if nch else 0
    if nch not in (1, 2) or n == 0 or any(len(c) != n for c in channels_pcm):
        raise EncodeError("The sound needs one or two channels of the same, non-zero length.")
    if not 1000 <= rate <= 96000:
        raise EncodeError("The sample rate is out of range.")
    enc = [encode_channel(c) for c in channels_pcm]
    u32 = lambda v: struct.pack("<I", v)
    u16 = lambda v: struct.pack("<H", v)
    s16 = lambda v: struct.pack("<h", v)
    info_content = 0x20 + 28 * nch + 46 * nch
    info_size = info_content + (-info_content % 0x40)
    offsets, at = [], 0x18                          # where each channel's frames start, from the DATA block's body
    for _coefs, frames in enc:
        offsets.append(at)
        at += len(frames) + (-len(frames) % 0x20)
    data_body = bytearray(b"\0" * 0x18)
    for i, (_coefs, frames) in enumerate(enc):
        data_body += frames
        if i < nch - 1:
            data_body += b"\0" * (-len(frames) % 0x20)
    data_size = 8 + len(data_body)
    info = bytearray(b"INFO" + u32(info_size) + bytes([2, 0, 0, 0]) + u32(rate) + u32(0) + u32(n) + u32(0) + u32(nch))
    for k in range(nch):                            # a reference to each channel's block
        info += u16(0x7100) + u16(0) + u32(0x20 + 8 * nch + 20 * k - 0x1C)
    for k in range(nch):                            # each channel's block: where its samples are, where its coefficients are
        struct_at = 0x20 + 8 * nch + 20 * k
        adpcm_at = 0x20 + 28 * nch + 46 * k
        info += u16(0x1F00) + u16(0) + u32(offsets[k]) + u16(0x0300) + u16(0) + u32(adpcm_at - struct_at) + u32(0)
    for coefs, frames in enc:                       # each channel's coefficients and starting state
        ps = frames[0]
        for c1, c2 in coefs:
            info += s16(c1) + s16(c2)
        info += u16(ps) + s16(0) + s16(0) + u16(ps) + s16(0) + s16(0) + u16(0)
    info += b"\0" * (info_size - len(info))
    data_at = 0x40 + info_size
    head = bytearray(b"FWAV" + b"\xff\xfe" + u16(0x40) + bytes([0, 1, 1, 0]) + u32(data_at + data_size) + u16(2) + u16(0))
    head += u16(0x7000) + u16(0) + u32(0x40) + u32(info_size)
    head += u16(0x7001) + u16(0) + u32(data_at) + u32(data_size)
    head += b"\0" * (0x40 - len(head))
    return bytes(head) + bytes(info) + b"DATA" + u32(data_size) + bytes(data_body)


def encode_sound(rate: int, channels_pcm: list, want_channels: int) -> bytes:
    """A .bfwav for audio of one or two channels, made into `want_channels` (mono is doubled, stereo averaged)."""
    ch = list(channels_pcm)
    if want_channels == 1 and len(ch) == 2:
        ch = [array("h", [(a + b) // 2 for a, b in zip(ch[0], ch[1])])]
    elif want_channels == 2 and len(ch) == 1:
        ch = [ch[0], ch[0]]
    return make_fwav(rate, ch)


# ------------------------------------------------------------------------------------------------ matching loudness
# The game's own race voice lines were measured (on the user's real mods) at a median -14.7 dBFS RMS with a crest
# factor (peak / average) of about 4.7 - they are mastered/compressed, not just loud at their single loudest instant.
# matchGameLoudness() in ui/js/voice.js applies this same pipeline client-side to a freshly recorded
# clip before it is ever sent to the app; boost_to_game_loudness() below is the same math, ported to Python, so an
# already-saved custom line can be re-gained without asking the user to redo it in the file picker (e.g. one that
# predates this feature, or was saved with "Match the game's own voice volume" unticked).
LOUD_TARGET_RMS = 0.185
LOUD_TARGET_DBFS = 20 * math.log10(LOUD_TARGET_RMS)   # ~ -14.65 dBFS
LOUD_CEILING = 0.97
LOUD_THRESHOLD = 0.07
LOUD_RATIO = 8
LOUD_ATTACK_MS = 3
LOUD_RELEASE_MS = 70
LOUD_MAX_GAIN = 14
# How far under the target counts as "quiet" in the editor - some slack, since the target is a median across real
# lines and plenty of them naturally sit a bit under it without anyone noticing.
QUIET_DBFS_MARGIN = 6.0


def rms_dbfs(channels_pcm) -> float | None:
    """RMS loudness of int16 PCM (one array per channel), in dBFS. None for a channel set too quiet to measure
    meaningfully (at or near digital silence) - a caller checking for "quiet" should treat that as its own case
    (voice_edit.is_silent), not as "very quiet"."""
    total, count = 0.0, 0
    for c in channels_pcm:
        for v in c:
            f = v / 32768.0
            total += f * f
        count += len(c)
    if not count:
        return None
    rms = math.sqrt(total / count)
    if rms <= 1e-6:
        return None
    return 20 * math.log10(rms)


def boost_to_game_loudness(channels_pcm, rate: int) -> list:
    """Re-gains already-decoded int16 PCM (one array per channel) to the game's own median voice-line loudness:
    a soft compressor (one shared envelope across channels, so stereo content isn't pulled out of balance) brings
    the peak-to-average ratio down near the game's own, then the gain that follows is searched for (a single-shot
    guess would be eaten into by the limiter below), then a smooth (tanh) limiter catches whatever peaks remain
    without turning them into an audible crackle. Mirrors ui/js/voice.js matchGameLoudness()/customPcm() exactly,
    minus the trim/fade (this operates on audio already trimmed when it was first saved). Returns new int16 arrays,
    one per channel."""
    nch = len(channels_pcm)
    n = len(channels_pcm[0]) if nch else 0
    if not n:
        return [array("h", c) for c in channels_pcm]
    floats = [[v / 32768.0 for v in c] for c in channels_pcm]
    attack = math.exp(-1 / (rate * LOUD_ATTACK_MS / 1000))
    release = math.exp(-1 / (rate * LOUD_RELEASE_MS / 1000))
    comp = [[0.0] * n for _ in range(nch)]
    env = 0.0
    for i in range(n):
        a = max(abs(floats[c][i]) for c in range(nch))
        env = a + (env - a) * (attack if a > env else release)
        g = (LOUD_THRESHOLD + (env - LOUD_THRESHOLD) / LOUD_RATIO) / env if env > LOUD_THRESHOLD else 1.0
        for c in range(nch):
            comp[c][i] = floats[c][i] * g

    def rms_of(chans):
        total = sum(v * v for c in chans for v in c)
        return math.sqrt(total / (nch * n)) if nch * n else 0.0

    def soft_limit(chans, gain):
        return [[LOUD_CEILING * math.tanh((v * gain) / LOUD_CEILING) for v in c] for c in chans]

    rms0 = rms_of(comp)
    gain = min(LOUD_MAX_GAIN, LOUD_TARGET_RMS / rms0) if rms0 > 1e-6 else 1.0
    out = soft_limit(comp, gain)
    for _ in range(5):
        r1 = rms_of(out)
        if abs(r1 - LOUD_TARGET_RMS) < 0.003 or gain >= LOUD_MAX_GAIN:
            break
        gain = min(LOUD_MAX_GAIN, gain * (LOUD_TARGET_RMS / max(r1, 1e-6)))
        out = soft_limit(comp, gain)
    return [array("h", (max(-32768, min(32767, round(v * 32767))) for v in c)) for c in out]
