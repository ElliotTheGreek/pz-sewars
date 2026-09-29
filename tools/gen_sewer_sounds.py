"""The sewers' own sounds, synthesised, so they re-make identically.

    python tools/gen_sewer_sounds.py

Writes Sewars/42/media/sound/SEW_*.wav (22.05 kHz, mono, 16-bit) -- the
format pz_trekship's generated sounds ship in -- and every one is declared in
media/scripts/sewars_sounds.txt, which tests/test_assets.py checks both ways.

  SEW_Lid      a cast-iron cover dragged off its seat and dropped: grinding
               noise through a resonant ring, then a heavy clank
  SEW_Ladder   rungs under boots: four dull metallic knocks
  SEW_Drip     one drop into standing water, with a long wet tail
  SEW_Groan    something far off in the pipes: a slow sub-bass swell with
               a detuned metallic moan over it

Vanilla already has rats in the walls (AnimalRatScuttleWall), and the mod
uses those as they are.
"""
import os
import wave

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "Sewars", "42", "media", "sound")
SR = 22050
rng = np.random.default_rng(1993)


def t(sec):
    return np.arange(int(sec * SR)) / SR


def env(n, attack, release):
    e = np.ones(n)
    a, r = int(attack * SR), int(release * SR)
    if a:
        e[:a] = np.linspace(0, 1, a)
    if r:
        e[-r:] *= np.linspace(1, 0, r) ** 2
    return e


def resonator(x, freq, q):
    """A two-pole band-pass: rings at freq."""
    w = 2 * np.pi * freq / SR
    r = np.exp(-w / (2 * q))
    a1, a2 = -2 * r * np.cos(w), r * r
    y = np.zeros_like(x)
    for i in range(len(x)):
        y[i] = x[i] - a1 * (y[i - 1] if i else 0) - a2 * (y[i - 2] if i > 1 else 0)
    return y * (1 - r)


def clank(freqs, decay, sec):
    tt = t(sec)
    out = np.zeros_like(tt)
    for f, amp in freqs:
        out += amp * np.sin(2 * np.pi * f * tt + rng.uniform(0, 6)) * np.exp(-tt * decay * (f / freqs[0][0]) ** 0.5)
    click = np.zeros_like(tt)
    click[:200] = rng.normal(0, 1, 200) * np.linspace(1, 0, 200)
    return out + 0.6 * click


def reverb(x, tail=1.2, wet=0.35):
    n = len(x) + int(tail * SR)
    y = np.zeros(n)
    y[:len(x)] = x
    for delay, g in ((0.043, 0.5), (0.071, 0.42), (0.113, 0.35), (0.167, 0.3), (0.241, 0.24), (0.331, 0.18)):
        d = int(delay * SR)
        for k in range(1, 6):
            if d * k < n:
                y[d * k:] += wet * (g ** k) * np.pad(x, (0, n - len(x)))[:n - d * k]
    return y


def norm(x, peak=0.85):
    return x / (np.max(np.abs(x)) + 1e-9) * peak


def write(name, x):
    os.makedirs(OUT, exist_ok=True)
    data = (np.clip(x, -1, 1) * 32767).astype("<i2")
    with wave.open(os.path.join(OUT, name + ".wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data.tobytes())
    print("%-11s %.2fs" % (name, len(x) / SR))


def lid():
    drag = rng.normal(0, 1, int(0.9 * SR))
    drag = resonator(drag, 420, 6) + 0.6 * resonator(drag, 1150, 9) + 0.3 * resonator(drag, 2600, 12)
    wob = 0.6 + 0.4 * np.abs(np.sin(2 * np.pi * 7 * t(0.9)))
    drag *= wob * env(len(drag), 0.05, 0.1)
    hit = clank([(180, 1.0), (397, 0.6), (731, 0.35), (1210, 0.2)], 9, 1.2)
    x = np.concatenate([norm(drag, 0.5), np.zeros(int(0.08 * SR)), norm(hit, 0.95)])
    return norm(reverb(x, 1.0, 0.3))


def ladder():
    parts = []
    for i in range(4):
        k = clank([(260 + 15 * i, 1.0), (590, 0.4), (1010, 0.2)], 30, 0.28)
        parts += [norm(k, 0.8 - 0.08 * i), np.zeros(int(0.16 * SR))]
    return norm(reverb(np.concatenate(parts), 0.8, 0.3))


def drip():
    tt = t(0.25)
    f = 900 + 1400 * np.exp(-tt * 40)
    ph = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(ph) * np.exp(-tt * 28)
    x[:60] += rng.normal(0, 0.5, 60)
    return norm(reverb(x, 1.8, 0.5), 0.6)


def groan():
    tt = t(5.0)
    sub = np.sin(2 * np.pi * (38 + 4 * np.sin(2 * np.pi * 0.2 * tt)) * tt)
    moan = sum(np.sin(2 * np.pi * (f + 3 * np.sin(2 * np.pi * 0.31 * tt + f)) * tt) * a
               for f, a in ((147, 0.5), (151.5, 0.4), (221, 0.25), (298, 0.15)))
    noise = resonator(rng.normal(0, 1, len(tt)), 90, 3)
    x = (0.8 * sub + 0.5 * moan + 0.4 * norm(noise)) * env(len(tt), 1.6, 2.2)
    return norm(reverb(x, 2.5, 0.4), 0.7)


if __name__ == "__main__":
    write("SEW_Lid", lid())
    write("SEW_Ladder", ladder())
    write("SEW_Drip", drip())
    write("SEW_Groan", groan())
