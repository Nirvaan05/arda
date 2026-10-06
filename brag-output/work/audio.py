# 120 BPM, A minor, Am-F-C-G (bar = 2s). Hook 0-4s filtered/sparse, drop at 4.0s.
import numpy as np, wave
SR, DUR, B = 44100, 22.0, 0.5
N = int(SR*DUR); t = np.arange(N)/SR
mus = np.zeros((N, 2)); sfx = np.zeros((N, 2))
hz = lambda m: 440*2**((m-69)/12)
def env(n, a, d):  # attack, exp decay
    x = np.arange(n)/SR; return np.minimum(1, x/max(a, 1e-4))*np.exp(-x/d)
def add(buf, start, sig, gain=1., pan=0.):
    i = int(start*SR); sig = sig[:max(0, N-i)]
    buf[i:i+len(sig), 0] += sig*gain*(1-pan)**.5; buf[i:i+len(sig), 1] += sig*gain*(1+pan)**.5
def lp(x, a):  # one-pole lowpass, a in (0,1]
    y = np.empty_like(x); acc = 0.; a = np.broadcast_to(a, x.shape)
    for i, v in enumerate(x): acc += a[i]*(v-acc); y[i] = acc
    return y
def tone(f, dur, a=.005, d=.3, harm=(1, .5, .25)):
    n = int(dur*SR); x = np.arange(n)/SR
    return sum(h*np.sin(2*np.pi*f*(k+1)*x) for k, h in enumerate(harm))*env(n, a, d)
CH = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
BASS = [45, 41, 36, 43]
rng = np.random.default_rng(7)
for bar in range(11):
    t0 = bar*2; ch = CH[bar % 4]; hook = t0 < 4
    # pad: soft detuned triad
    n = int(2*SR); x = np.arange(n)/SR
    pad = sum(np.sin(2*np.pi*hz(m)*x*(1+dt)) for m in ch for dt in (-.002, .002))
    pad *= np.minimum(1, x/.25)*np.minimum(1, (2-x)/.3)
    add(mus, t0, pad, .035 if hook else .05)
    # plucked arp on eighths (in hook: quarters only)
    for k in range(16 if not hook else 4):
        step = .125*4 if hook else .125*1
        tt = t0 + (k*(1.0 if hook else 0.25)) / (1 if hook else 1) * (0.5 if hook else 0.5)
        m = (ch + [c+12 for c in ch])[[0, 1, 2, 4, 3, 5, 4, 2][k % 8]] + 12
        add(mus, t0 + k*(.5 if hook else .125), tone(hz(m), .3, .002, .12, (1, .3, .1)), .05 if hook else .045, (-.4, .4)[k % 2])
    if hook: continue
    for beat in range(4):
        tb = t0 + beat*B
        # kick: pitch drop sine
        n = int(.35*SR); x = np.arange(n)/SR
        f = 45 + 90*np.exp(-x/.03); kick = np.sin(2*np.pi*np.cumsum(f)/SR)*np.exp(-x/.12)
        add(mus, tb, kick, .5)
        # bass: root on beat, offbeat octave
        add(mus, tb, lp(tone(hz(BASS[bar % 4]), .45, .005, .2, (1, .6, .3, .15)), .15), .32)
        # hat on offbeat; snare-ish clap on 2 and 4
        hat = rng.standard_normal(int(.05*SR)); hat = (hat - lp(hat, .5))*env(len(hat), .001, .012)
        add(mus, tb+.25, hat, .07, .3)
        if beat in (1, 3):
            sn = rng.standard_normal(int(.25*SR)); sn = (sn - lp(sn, .08))*env(len(sn), .001, .06)
            add(mus, tb, sn, .12, -.1)
# riser into drop (3.0-4.0)
n = int(1*SR); x = np.arange(n)/SR; nz = rng.standard_normal(n)
add(mus, 3.0, lp(nz, .02 + .3*(x/1)**2)*(x/1)**2, .25)
# --- SFX (key of A), kept under the music ---
def pluck(m, g=.08, pan=0.): return tone(hz(m), .5, .002, .18, (1, .4, .2))
def whoosh(dur, up=True):
    n = int(dur*SR); x = np.arange(n)/SR; nz = rng.standard_normal(n)
    sweep = np.sin(np.pi*x/dur); return lp(nz, .03 + .12*(x/dur if up else 1-x/dur))*sweep
def click(): c = rng.standard_normal(int(.012*SR)); return (c - lp(c, .3))*env(len(c), .0005, .003)
hops = [(.75, 1.25, 1, 0), (1.4, 1.85, 2, 1), (2.0, 2.45, 0, 2), (2.55, 2.85, 1, 0), (2.95, 3.2, 2, 1), (3.28, 3.46, 1, 2), (3.52, 3.68, 0, 1)]
P = [-.6, 0, .6]
for i, (s, e, b, a) in enumerate(hops):
    add(sfx, s, whoosh(e-s), .10, P[a]); add(sfx, e, pluck(76 + (i % 3)*2), .05, P[b])
add(sfx, 4.0, tone(hz(57), 1.5, .002, .6, (1, .5, .3, .2)), .12)  # reveal hit (A)
def typing(s, e):
    tt = s
    while tt < e: add(sfx, tt, click(), .05, .2); tt += .045 + rng.random()*.03
typing(7.35, 7.8); typing(11.3, 12.25); typing(13.45, 13.8); typing(14.0, 14.7)
for k, tt in enumerate([8.05, 8.2, 8.35, 8.6, 8.75, 9.0, 9.15]): add(sfx, tt, pluck(81 + [0, 2, 4, 7, 9, 7, 4][k]), .025)
add(sfx, 12.45, pluck(81), .06); add(sfx, 12.5, whoosh(.5), .14, -.3); add(sfx, 13.0, pluck(88), .06, .3)
add(sfx, 14.75, whoosh(.45), .14, .3); add(sfx, 15.2, pluck(84), .06, -.3); add(sfx, 15.3, pluck(88), .05, -.3)
for k, tt in enumerate([16.1, 16.45, 16.8]):
    add(sfx, tt, lp(tone(hz(45 + [0, 3, 7][k]), .4, .001, .1, (1, .5)), .3), .35)
add(sfx, 18.4, whoosh(.35), .14)
add(sfx, 18.7, tone(hz(69), 1.2, .002, .5, (1, .4, .2)), .06); add(sfx, 19.0, tone(hz(76), 1.5, .002, .7, (1, .4, .2)), .06)
mix = mus + sfx*0.8
mix *= np.minimum(1, (DUR - t)/1.2)[:, None]  # fade out
mix = np.tanh(mix*1.4)/np.tanh(1.4); mix *= .89/np.abs(mix).max()
with wave.open('music.wav', 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes((mix*32767).astype('<i2').tobytes())
print('ok', np.abs(mix).max())
