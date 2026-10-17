#!/usr/bin/env python3
"""
QLIK OR TREAT  -  a spooky, silly, Qlik-themed arcade shooter for Raspberry Pi.

Controls (3 buttons):  LEFT  |  FIRE  |  RIGHT
  Keyboard:  arrows or A/D to move, UP/W/ENTER to fire (hold for auto-fire), ESC to quit
             hold SPACE to fast-forward (for testing)
  GPIO:      one leg of each button to the pin below, other leg to GND
             (internal pull-ups are used, no resistors needed)

Run:
  python3 qlik_or_treat.py            fullscreen (on the Pi)
  python3 qlik_or_treat.py --window   windowed (on your laptop)

Pins can also be overridden with env vars PIN_LEFT, PIN_FIRE, PIN_RIGHT.
"""
import array
import json
import math
import os
import random
import sys

import pygame

# --------------------------------------------------------------------- config
W, H = 800, 600
FPS = 60
FAST_FORWARD = 8  # game speed multiplier while SPACE is held (testing aid)
ROUND_SECONDS = 90
HIT_PENALTY = 100
TRAIN_TIMES = (35, 65)  # seconds into the round when the Fivetrain arrives

PIN_LEFT = int(os.environ.get("PIN_LEFT", 17))    # physical pin 11
PIN_FIRE = int(os.environ.get("PIN_FIRE", 27))    # physical pin 13
PIN_RIGHT = int(os.environ.get("PIN_RIGHT", 22))  # physical pin 15

HERE = os.path.dirname(os.path.abspath(__file__))
SCORE_FILE = os.path.join(HERE, "highscores.json")

# -------------------------------------------------------------------- palette
QLIK_GREEN = (0, 152, 69)
QLIK_LIGHT = (130, 230, 150)
WHITE = (240, 240, 250)
GREY = (180, 180, 200)
RED = (235, 50, 60)
ORANGE = (255, 140, 20)
YELLOW = (242, 200, 17)
CONFETTI = [QLIK_GREEN, QLIK_LIGHT, (255, 180, 0), (230, 60, 130), (60, 160, 255), ORANGE]

KILL_QUIPS = [
    "Datasilo krossad!", "Dashboard uppdaterad!", "Insikt upplåst!",
    "Pipeline rensad!", "Associerad & eliminerad!", "Bu-ja!", "Spöket under kontroll!",
]
HIT_QUIPS = [
    "Aj! Manuell uppdatering!", "Datakvalitetsproblem!", "Buu! Skrämd!",
    "Vilse i en silo!", "Vem beställde en CSV?!",
]
RANKS = [
    (0, "Kalkylarksöverlevare"),
    (2500, "Dashboardförsvarare"),
    (6000, "Insiktsjägare"),
    (10000, "Dataspökjägare"),
    (15000, "Chefsspökjägare"),
]


def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v


def lerp_color(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def rank_for(score):
    title = RANKS[0][1]
    for threshold, name in RANKS:
        if score >= threshold:
            title = name
    return title


def load_scores():
    try:
        with open(SCORE_FILE) as f:
            return sorted((int(s) for s in json.load(f)), reverse=True)[:10]
    except Exception:
        return []


def save_scores(scores):
    try:
        with open(SCORE_FILE, "w") as f:
            json.dump(scores, f)
    except Exception as exc:
        print("Could not save scores:", exc)


# ---------------------------------------------------------------- text / glow
_fonts, _text_cache, _glows = {}, {}, {}


def font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def render(text, size, color):
    key = (text, size, color)
    img = _text_cache.get(key)
    if img is None:
        if len(_text_cache) > 500:
            _text_cache.clear()
        img = font(size).render(text, True, color)
        _text_cache[key] = img
    return img


def draw_text(surf, text, size, color, center=None, topleft=None, topright=None, shadow=True):
    img = render(text, size, color)
    rect = img.get_rect()
    if center:
        rect.center = (int(center[0]), int(center[1]))
    elif topright:
        rect.topright = topright
    else:
        rect.topleft = topleft or (0, 0)
    if shadow:
        surf.blit(render(text, size, (0, 0, 0)), rect.move(2, 2))
    surf.blit(img, rect)
    return rect


def glow(radius, color, strength=80):
    key = (radius, color, strength)
    if key not in _glows:
        s = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        for r in range(radius, 0, -2):
            a = int(strength * (1 - r / radius) ** 2)
            pygame.draw.circle(s, (*color, a), (radius, radius), r)
        _glows[key] = s
    return _glows[key]


def blit_glow(surf, x, y, radius, color, strength=80):
    surf.blit(glow(radius, color, strength), (int(x) - radius, int(y) - radius))


# ---------------------------------------------------------------------- sound
class Sfx:
    """All sounds are synthesised at startup - no audio files needed."""

    def __init__(self):
        self.sounds = {}
        self.enabled = False
        self.drone = None
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(22050, -16, 1, 512)
            freq, fmt, ch = pygame.mixer.get_init()
            if abs(fmt) != 16:
                raise RuntimeError("unsupported sample format %s" % fmt)
            self.rate, self.channels = freq, ch
            pygame.mixer.set_num_channels(24)
            pygame.mixer.set_reserved(1)
            self._build()
            self.enabled = True
        except Exception as exc:
            print("Sound disabled:", exc)

    def tone(self, f0, f1, dur, wave="square", vol=0.3, noise=0.0, vib=0.0, vibf=8.0, attack=0.005):
        r = self.rate
        n = int(r * dur)
        out = array.array("h")
        ph = 0.0
        for i in range(n):
            t = i / r
            p = i / n
            f = f0 + (f1 - f0) * p
            if vib:
                f *= 1 + vib * math.sin(2 * math.pi * vibf * t)
            ph += f / r
            frac = ph % 1.0
            if wave == "square":
                s = 1.0 if frac < 0.5 else -1.0
            elif wave == "saw":
                s = 2.0 * frac - 1.0
            elif wave == "tri":
                s = 4.0 * abs(frac - 0.5) - 1.0
            else:
                s = math.sin(2 * math.pi * ph)
            if noise:
                s = s * (1 - noise) + random.uniform(-1, 1) * noise
            env = min(1.0, t / attack) * (1 - p) ** 1.6
            out.append(int(clamp(s * env * vol, -1, 1) * 32767))
        return out

    def seq(self, notes, each, wave, vol, vib=0.0):
        out = array.array("h")
        for f in notes:
            out.extend(self.tone(f, f, each, wave, vol, vib=vib, vibf=6))
        return out

    def drone_loop(self, dur=8.0):
        # All frequencies complete whole cycles in 8 s, so the loop is seamless.
        r, tau = self.rate, 2 * math.pi
        out = array.array("h")
        for i in range(int(r * dur)):
            t = i / r
            lfo = 0.5 + 0.5 * math.sin(tau * 0.25 * t)
            s = (math.sin(tau * 55 * t) + 0.7 * math.sin(tau * 55.5 * t)
                 + 0.45 * lfo * math.sin(tau * 82.5 * t)
                 + 0.2 * (1 - lfo) * math.sin(tau * 220.25 * t + 2 * math.sin(tau * 0.5 * t)))
            out.append(int(s / 2.4 * 0.22 * 32767))
        return out

    def music_loop(self):
        """Spooky-disco tune in A minor: octave-bouncing bass, square lead, hi-hats.
        Built by concatenating cached notes (fast enough for the Pi at startup)."""
        step = 0.2  # one eighth note at 150 BPM; 64 steps = 12.8 s loop
        # MIDI note numbers, one per eighth, 0 = rest
        lead = [57, 60, 64, 69, 68, 64, 60, 64,   53, 57, 60, 65, 64, 60, 57, 60,
                62, 65, 69, 65, 62, 65, 64, 62,   64, 68, 71, 68, 64, 0, 62, 59,
                57, 60, 64, 69, 68, 64, 60, 64,   53, 57, 60, 65, 64, 60, 57, 60,
                62, 65, 69, 72, 71, 69, 68, 71,   69, 0, 64, 0, 57, 0, 0, 0]
        lead = [n + 12 if n else 0 for n in lead]
        roots = [45, 41, 38, 40, 45, 41, 38, 40]  # Am F Dm E, twice
        bass = [r + (12 if i % 2 else 0) for r in roots for i in range(8)]
        n = int(self.rate * step)
        cache = {}

        def note(m, wave, vol):
            key = (m, wave, vol)
            if key not in cache:
                if m:
                    f = 440 * 2 ** ((m - 69) / 12)
                    cache[key] = self.tone(f, f, step, wave, vol, attack=0.004)
                else:
                    cache[key] = array.array("h", bytes(2 * n))
            return cache[key]

        tracks = []
        for part, wave, vol in ((lead, "square", 0.09), (bass, "tri", 0.26)):
            tr = array.array("h")
            for m in part:
                tr.extend(note(m, wave, vol))
            tracks.append(tr)
        hat = self.tone(8000, 8000, 0.03, "sine", 0.05, noise=1.0)
        hat.extend(array.array("h", bytes(2 * (n - len(hat)))))
        tracks.append(note(0, "", 0) + hat)  # hat on every off-beat
        tracks[2] *= len(lead) // 2
        return array.array("h", map(sum, zip(*tracks)))

    def _sound(self, samples):
        if self.channels > 1:
            st = array.array("h", bytes(2 * len(samples) * self.channels))
            for c in range(self.channels):
                st[c::self.channels] = samples
            samples = st
        return pygame.mixer.Sound(buffer=samples.tobytes())

    def _build(self):
        T, S = self.tone, self._sound
        self.sounds["shoot"] = S(T(1200, 350, 0.08, "square", 0.10))
        self.sounds["explode"] = S(T(200, 30, 0.45, "square", 0.32, noise=0.85))
        self.sounds["hit"] = S(T(750, 110, 0.75, "saw", 0.28, vib=0.10, vibf=11))
        self.sounds["boo"] = S(T(200, 320, 0.9, "sine", 0.45, vib=0.06, vibf=5, attack=0.2))
        self.sounds["screech"] = S(T(2000, 900, 0.16, "saw", 0.06, vib=0.2, vibf=45))
        self.sounds["tick"] = S(T(1400, 1400, 0.05, "square", 0.12))
        self.sounds["whistle"] = S(T(700, 640, 0.7, "square", 0.12, vib=0.015, vibf=30, attack=0.05))
        self.sounds["start"] = S(self.seq([330, 392, 494, 659, 988], 0.09, "tri", 0.3))
        self.sounds["over"] = S(self.seq([392, 330, 262, 196, 131], 0.22, "saw", 0.22, vib=0.03))
        self.sounds["bonus"] = S(self.seq([523, 659, 784, 1047, 1319], 0.07, "square", 0.15))
        self.drone = S(self.drone_loop())
        self.music = S(self.music_loop())

    def play(self, name):
        if self.enabled and name in self.sounds:
            self.sounds[name].play()

    def _loop(self, snd):
        # channel 0 is reserved for the background loop: drone on title, music in rounds
        if self.enabled and snd:
            pygame.mixer.Channel(0).play(snd, loops=-1, fade_ms=400)

    def start_drone(self):
        self._loop(self.drone)

    def start_music(self):
        self._loop(self.music)


# ---------------------------------------------------------------------- input
class Input:
    def __init__(self):
        self.buttons = None
        try:
            from gpiozero import Button
            self.buttons = (Button(PIN_LEFT, pull_up=True, bounce_time=0.01),
                            Button(PIN_FIRE, pull_up=True, bounce_time=0.01),
                            Button(PIN_RIGHT, pull_up=True, bounce_time=0.01))
            print("GPIO buttons enabled on", PIN_LEFT, PIN_FIRE, PIN_RIGHT)
        except Exception as exc:
            print("GPIO not available, keyboard only (%s: %s)" % (exc.__class__.__name__, exc))
        self.left = self.right = self.fire = False
        self.any = self.any_pressed = False

    def poll(self):
        k = pygame.key.get_pressed()
        l = k[pygame.K_LEFT] or k[pygame.K_a]
        r = k[pygame.K_RIGHT] or k[pygame.K_d]
        f = k[pygame.K_UP] or k[pygame.K_w] or k[pygame.K_RETURN]
        if self.buttons:
            l = l or self.buttons[0].is_pressed
            f = f or self.buttons[1].is_pressed
            r = r or self.buttons[2].is_pressed
        prev = self.any
        self.left, self.right, self.fire = bool(l), bool(r), bool(f)
        self.any = self.left or self.right or self.fire
        self.any_pressed = self.any and not prev


# ----------------------------------------------------------------- background
class Background:
    def __init__(self):
        self.base = pygame.Surface((W, H))
        top, bottom = (6, 3, 18), (30, 8, 40)
        for y in range(H):
            pygame.draw.line(self.base, lerp_color(top, bottom, y / H), (0, y), (W, y))
        self._moon(self.base, 660, 105)
        self._graveyard(self.base)
        self.stars = [[random.uniform(0, W), random.uniform(0, H), random.choice((15, 35, 70)),
                       random.choice((1, 1, 2)), random.randint(90, 220)] for _ in range(90)]
        self.fog = [[random.uniform(-100, W), random.uniform(0, H), random.uniform(8, 18),
                     random.uniform(-6, 6)] for _ in range(5)]

    def _moon(self, s, x, y):
        s.blit(glow(110, (90, 80, 140), 60), (x - 110, y - 110))
        pygame.draw.circle(s, (225, 225, 200), (x, y), 46)
        for cx, cy, r in ((-14, -10, 9), (12, 8, 12), (-6, 20, 6), (18, -18, 5)):
            pygame.draw.circle(s, (195, 195, 175), (x + cx, y + cy), r)

    def _graveyard(self, s):
        labels = ["RIP", "EXCEL 97", "RIP", "LETARAD", "CSV", "RIP", "MAKRON", "RIP"]
        stone = (38, 28, 54)
        x = 20
        for label in labels:
            w = random.randint(54, 74) if len(label) > 3 else random.randint(38, 50)
            h = random.randint(38, 56)
            rect = pygame.Rect(x, H - h, w, h + 10)
            pygame.draw.rect(s, stone, rect, border_top_left_radius=w // 2, border_top_right_radius=w // 2)
            img = font(15).render(label, True, (85, 72, 110))
            s.blit(img, img.get_rect(center=(rect.centerx, H - h + 22)))
            x += w + random.randint(40, 70)
            if x > W - 40:
                break

    def update(self, dt):
        for st in self.stars:
            st[1] += st[2] * dt
            if st[1] > H:
                st[1] = 0
                st[0] = random.uniform(0, W)
        for f in self.fog:
            f[1] += f[2] * dt
            f[0] += f[3] * dt
            if f[1] > H + 140:
                f[1] = -140
                f[0] = random.uniform(-100, W)

    def draw(self, surf):
        surf.blit(self.base, (0, 0))
        for x, y, _, size, b in self.stars:
            pygame.draw.rect(surf, (b, b, min(255, b + 30)), (int(x), int(y), size, size))
        for x, y, _, _ in self.fog:
            surf.blit(glow(140, (70, 40, 95), 45), (int(x) - 140, int(y) - 140))


def make_vignette():
    v = pygame.Surface((W, H), pygame.SRCALPHA)
    v.fill((0, 0, 0, 200))
    steps = 24
    for i in range(steps):
        t = i / (steps - 1)
        ew = int(W * 1.5 - W * t)
        eh = int(H * 1.5 - H * t)
        a = int(200 * (1 - t) ** 1.5)
        pygame.draw.ellipse(v, (0, 0, 0, a), pygame.Rect(W // 2 - ew // 2, H // 2 - eh // 2, ew, eh))
    return v


def make_title():
    text = "QLIK OR TREAT"
    f = pygame.font.Font(None, 118)
    main = f.render(text, True, QLIK_GREEN)
    if main.get_width() > W - 60:
        scale = (W - 60) / main.get_width()
        f = pygame.font.Font(None, int(118 * scale))
        main = f.render(text, True, QLIK_GREEN)
    halo = f.render(text, True, (0, 60, 25))
    pad = 8
    surf = pygame.Surface((main.get_width() + pad * 2, main.get_height() + pad * 2), pygame.SRCALPHA)
    for dx in (-4, 0, 4):
        for dy in (-4, 0, 4):
            surf.blit(halo, (pad + dx, pad + dy))
    surf.blit(main, (pad, pad))
    # find where letters end, so slime can drip from them
    drips = []
    mw, mh = main.get_size()
    tries = 0
    while len(drips) < 11 and tries < 600:
        tries += 1
        x = random.randint(4, mw - 5)
        for y in range(mh - 1, -1, -1):
            if main.get_at((x, y)).a > 200:
                drips.append((x + pad, y + pad, random.uniform(0, 50), random.uniform(8, 20)))
                break
    return surf, drips


# -------------------------------------------------------------------- player
class Player:
    SPEED = 430

    def __init__(self):
        self.x, self.y = W / 2, H - 72
        self.cool = 0.0
        self.inv = 1.0
        self.tilt = 0.0

    def update(self, dt, inp, game):
        d = (1 if inp.right else 0) - (1 if inp.left else 0)
        self.x = clamp(self.x + d * self.SPEED * dt, 34, W - 34)
        self.tilt += (d - self.tilt) * min(1.0, dt * 10)
        self.cool -= dt
        self.inv = max(0.0, self.inv - dt)
        if inp.fire and self.cool <= 0:
            game.bullets.append(Bullet(self.x, self.y - 28))
            self.cool = 0.15
            game.sfx.play("shoot")

    def draw(self, s, clock):
        if self.inv > 0 and int(clock * 20) % 2 == 0:
            return
        x, y = int(self.x), int(self.y)
        fl = random.randint(10, 18)
        pygame.draw.polygon(s, ORANGE, [(x - 8, y + 20), (x + 8, y + 20), (x, y + 20 + fl)])
        pygame.draw.polygon(s, YELLOW, [(x - 4, y + 20), (x + 4, y + 20), (x, y + 20 + fl * 0.6)])
        blit_glow(s, x, y, 46, QLIK_GREEN, 70)
        t = self.tilt * 6
        for side in (-1, 1):
            pygame.draw.polygon(s, (90, 100, 110), [
                (x + side * 18, y + 2), (x + side * 38, y + 16 - side * t), (x + side * 20, y + 16)])
        pygame.draw.circle(s, QLIK_GREEN, (x, y), 23, 8)
        pygame.draw.line(s, QLIK_GREEN, (x + 10, y + 12), (x + 25, y + 29), 9)
        pygame.draw.circle(s, (200, 255, 215), (x, y - 3), 6)


class Bullet:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.dead = False

    def update(self, dt):
        self.y -= 760 * dt
        if self.y < -20:
            self.dead = True

    def draw(self, s):
        blit_glow(s, self.x, self.y, 12, QLIK_GREEN, 110)
        pygame.draw.rect(s, QLIK_LIGHT, (int(self.x) - 2, int(self.y) - 9, 4, 17))


class ErrorBlob:
    """Spreadsheet errors spat out by the Table-Ghoul."""
    TEXTS = ["#REFERENS!", "#SAKNAS!", "#DIVISION/0!", "#VÄRDEFEL!"]  # Swedish Excel

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.text = random.choice(self.TEXTS)
        self.t = 0.0
        self.dead = False

    def update(self, dt):
        self.t += dt
        self.y += 150 * dt
        self.x += math.sin(self.t * 6) * 50 * dt
        if self.y > H + 20:
            self.dead = True

    def draw(self, s):
        blit_glow(s, self.x, self.y, 26, RED, 90)
        draw_text(s, self.text, 26, RED, center=(self.x, self.y))


# ------------------------------------------------------------------- monsters
def draw_ghost(surf, x, y, r, color, t, flash=False):
    col = WHITE if flash else color
    cy = y - r * 0.2
    pts = [(x + r * math.cos(math.pi + math.pi * i / 12), cy + r * math.sin(math.pi + math.pi * i / 12))
           for i in range(13)]
    n = 6
    for i in range(n + 1):
        px = x + r - 2 * r * i / n
        py = y + r * 0.9 + (5 if i % 2 == 0 else -3) + 3 * math.sin(t * 8 + i)
        pts.append((px, py))
    pygame.draw.polygon(surf, col, pts)
    ex = r * 0.36
    for side in (-1, 1):
        pygame.draw.ellipse(surf, (20, 10, 35), (x + side * ex - r * 0.14, cy - r * 0.2, r * 0.28, r * 0.4))
    mouth = r * (0.22 + 0.08 * math.sin(t * 5))
    pygame.draw.ellipse(surf, (20, 10, 35), (x - mouth / 2, cy + r * 0.35, mouth, mouth * 1.3))


class Enemy:
    name = "?"
    tagline = ""
    hp = 1
    r = 20
    points = 100

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.t = random.uniform(0, 6)
        self.flash = 0.0
        self.dead = False
        self.hp = type(self).hp

    def active(self):
        return self.y > -30

    def update(self, dt, game):
        self.t += dt
        self.flash = max(0.0, self.flash - dt)
        self.move(dt, game)
        if self.y > H + 60:
            self.dead = True  # escaped - no penalty, it's a party

    def move(self, dt, game):
        pass

    def hit(self):
        self.hp -= 1
        self.flash = 0.08
        return self.hp <= 0


class Spooker(Enemy):
    name = "SPOOKER"
    tagline = "Lurar i ditt semantiska lager"
    points = 100
    color = (205, 220, 255)

    def __init__(self, x, y):
        super().__init__(x, y)
        self.bx = x
        self.vy = random.uniform(80, 120)

    def move(self, dt, game):
        boost = 1 + 0.6 * game.elapsed / ROUND_SECONDS if game.state == "playing" else 1
        self.y += self.vy * boost * dt
        self.x = self.bx + math.sin(self.t * 2) * 30

    def draw(self, s):
        blit_glow(s, self.x, self.y, 38, self.color, 45)
        draw_ghost(s, self.x, self.y, self.r, self.color, self.t, self.flash > 0)


class PowerBooI(Spooker):
    name = "POWER BOO-I"
    tagline = "Maktgalen och full av BU"
    points = 150
    color = YELLOW

    def move(self, dt, game):
        self.y += 105 * dt
        self.x = clamp(self.bx + math.sin(self.t * 2.6) * 130, 30, W - 30)

    def draw(self, s):
        for i, h in enumerate((10, 16, 22)):
            pygame.draw.rect(s, (200, 150, 0), (int(self.x) - 12 + i * 9, int(self.y - self.r * 1.15) - h + 4, 6, h))
        super().draw(s)


class Airbite(Enemy):
    name = "AIRBITE"
    tagline = "Biter i mer data än den kan tugga"
    r = 18
    points = 150

    def __init__(self, x, y):
        super().__init__(x, y)
        self.bx = x
        self.target_y = random.uniform(90, 220)
        self.wait = random.uniform(1.2, 2.6)
        self.vx = self.vy = 0.0
        self.diving = False

    def move(self, dt, game):
        if not self.diving:
            if self.y < self.target_y:
                self.y += 130 * dt
            else:
                self.wait -= dt
                if self.wait <= 0:
                    self.diving = True
                    tx = game.player.x if game.player and game.state == "playing" else random.uniform(50, W - 50)
                    dx, dy = tx - self.x, (H - 60) - self.y
                    d = math.hypot(dx, dy) or 1
                    sp = 300 + game.elapsed * 1.5
                    self.vx, self.vy = dx / d * sp, dy / d * sp
                    if game.state == "playing":
                        game.sfx.play("screech")
            self.x = self.bx + math.sin(self.t * 3) * 25
        else:
            self.x += self.vx * dt
            self.y += self.vy * dt

    def draw(self, s):
        x, y = int(self.x), int(self.y)
        flap = math.sin(self.t * 18)
        fl = self.flash > 0
        body = WHITE if fl else (70, 25, 95)
        wing = WHITE if fl else (45, 15, 65)
        blit_glow(s, x, y, 34, (150, 40, 200), 50)
        for side in (-1, 1):
            pygame.draw.polygon(s, wing, [
                (x + side * 6, y - 6), (x + side * 18, y - 12 + flap * 10), (x + side * 34, y - 8 + flap * 14),
                (x + side * 26, y + 4 + flap * 8), (x + side * 20, y + 6 + flap * 6), (x + side * 12, y + 10),
                (x + side * 6, y + 6)])
            pygame.draw.polygon(s, body, [(x + side * 10, y - 8), (x + side * 7, y - 20), (x + side * 2, y - 10)])
        pygame.draw.circle(s, body, (x, y), 13)
        for side in (-1, 1):
            pygame.draw.circle(s, RED, (x + side * 5, y - 3), 3)
            pygame.draw.polygon(s, WHITE, [(x + side * 4, y + 6), (x + side * 2, y + 12), (x, y + 6)])


class TableGhoul(Enemy):
    """A walking haunted spreadsheet: coin eyes, zigzag mouth, robot legs."""
    name = "TABLE-GHOUL"
    tagline = "Dra, släpp... och DREGLA"
    hp = 4
    r = 44
    points = 400
    CHARGE = 0.7  # seconds of warning (siren, formula, gaping mouth) before it spits
    FORMULAS = ["=SUMMA(A1:C1)", "=LETARAD(BU)", "=OM(SPÖK;BU)", "=PIVOT(???)", "=MEDEL(GRAV)"]
    _sprites = None

    @classmethod
    def sprites(cls):
        """Static parts, drawn once: cabinet + headers, gridlines, scrolling 'matrix' rain."""
        if cls._sprites is None:
            base = pygame.Surface((106, 84), pygame.SRCALPHA)
            pygame.draw.rect(base, (45, 100, 180), (0, 0, 106, 84), border_radius=7)
            pygame.draw.line(base, (110, 170, 240), (7, 2), (98, 2), 2)
            pygame.draw.rect(base, (14, 30, 66), (6, 6, 94, 72))
            pygame.draw.rect(base, (30, 64, 120), (6, 6, 94, 12))
            pygame.draw.rect(base, (30, 64, 120), (6, 6, 13, 72))
            pygame.draw.rect(base, (20, 45, 95), (0, 0, 106, 84), 3, border_radius=7)
            grid = pygame.Surface((106, 84), pygame.SRCALPHA)
            for i in range(4):
                pygame.draw.line(grid, (75, 125, 205), (19 + 27 * i, 6), (19 + 27 * i, 77))
            for j in range(4):
                pygame.draw.line(grid, (75, 125, 205), (6, 18 + 20 * j), (99, 18 + 20 * j))
            pygame.draw.rect(grid, (110, 160, 235), (6, 6, 94, 72), 1)
            for i, ch in enumerate("ABC"):
                img = font(17).render(ch, True, (225, 235, 255))
                grid.blit(img, img.get_rect(center=(33 + 27 * i, 13)))
            for j, ch in enumerate("123"):
                img = font(17).render(ch, True, (225, 235, 255))
                grid.blit(img, img.get_rect(center=(13, 29 + 20 * j)))
            rain = pygame.Surface((81, 120), pygame.SRCALPHA)  # 60 px tall, stored twice to wrap
            rng = random.Random(7)
            for cx in range(2, 81, 4):
                for _ in range(rng.randint(1, 3)):
                    y0, ln = rng.randint(0, 59), rng.randint(4, 12)
                    for k in range(0, ln, 2):
                        a = 40 + 90 * k // ln
                        for wrap in (0, 60):
                            rain.set_at((cx, (y0 + k) % 60 + wrap), (70, 210, 170, a))
            cls._sprites = base, grid, rain
        return cls._sprites

    def __init__(self, x, y):
        super().__init__(x, y)
        self.bx = clamp(x, 100, W - 100)
        self.shoot = random.uniform(1.5, 2.5)
        self.charge = self.gape = 0.0
        self.formula = random.choice(self.FORMULAS)
        self.look = 0.0
        self.spin, self.spin_wait = 0.0, random.uniform(1, 3)
        self.sel, self.sel_to, self.sel_wait = [0.0, 0.0], (0, 0), 1.5

    def move(self, dt, game):
        self.y += 40 * dt
        self.x = self.bx + math.sin(self.t * 0.8) * 60
        # idle animation: coin eyes flip now and then, cell selection hops around
        self.spin = max(0.0, self.spin - dt)
        self.spin_wait -= dt
        if self.spin_wait <= 0:
            self.spin, self.spin_wait = 0.4, random.uniform(2, 4)
        self.sel_wait -= dt
        if self.sel_wait <= 0:
            self.sel_to = random.choice([(0, 0), (1, 0), (2, 0), (0, 1), (2, 1)])
            self.sel_wait = random.uniform(1.2, 2.5)
        tx, ty = (1, 1) if self.charge > 0 else self.sel_to
        k = min(1.0, dt * 12)
        self.sel[0] += (tx - self.sel[0]) * k
        self.sel[1] += (ty - self.sel[1]) * k
        self.gape = max(0.0, self.gape - dt)
        if game.player and game.state == "playing":
            self.look = clamp((game.player.x - self.x) / 150, -1, 1)
        if game.state != "playing":
            return
        self.shoot -= dt
        in_range = 30 < self.y < H - 220
        self.charge = clamp(1 - self.shoot / self.CHARGE, 0, 1) if in_range else 0.0
        if self.shoot <= 0 and in_range:
            game.blobs.append(ErrorBlob(self.x, self.y + 32))
            self.shoot = random.uniform(2.2, 3.4)
            self.charge, self.gape = 0.0, 0.3
            self.formula = random.choice(self.FORMULAS)

    def draw(self, s):
        base, grid, rain = self.sprites()
        x, y = int(self.x), int(self.y)
        ox, oy = x - 53, y - 42
        fl = self.flash > 0
        t = self.t
        blit_glow(s, x, y, 72, (60, 120, 220), 45)
        # robot legs, stomping alternately
        for i, lx in enumerate((ox + 24, ox + 82)):
            lift = int(max(0.0, math.sin(t * 5 + i * math.pi)) * 5)
            pygame.draw.rect(s, (60, 140, 75), (lx - 5, oy + 80, 10, 12))
            pygame.draw.circle(s, (40, 100, 55), (lx, oy + 92 - lift // 2), 5)
            pygame.draw.rect(s, (70, 160, 85), (lx - 4, oy + 93 - lift, 8, 9))
            pygame.draw.rect(s, (40, 100, 55), (lx - 9, oy + 101 - lift, 18, 7), border_radius=3)
            pygame.draw.line(s, (110, 200, 120), (lx - 7, oy + 102 - lift), (lx + 7, oy + 102 - lift), 1)
        # siren on top (blinks fast while charging) + calculator keypad
        on = math.sin(t * (22 if self.charge > 0 else 4)) > 0
        if on:
            blit_glow(s, ox + 44, oy - 4, 20, RED, 120 if self.charge > 0 else 60)
        pygame.draw.circle(s, (255, 70, 70) if on else (120, 20, 25), (ox + 44, oy - 3), 6)
        pygame.draw.circle(s, (255, 200, 200), (ox + 42, oy - 5), 2)
        pygame.draw.rect(s, (60, 60, 75), (ox + 37, oy - 2, 14, 4))
        pygame.draw.rect(s, (150, 160, 180), (ox + 64, oy - 7, 34, 9), border_radius=2)
        pygame.draw.rect(s, (80, 220, 120), (ox + 67, oy - 5, 7, 5))
        for i in range(4):
            for j in range(2):
                col = RED if (i, j) == (3, 1) else (60, 70, 90)
                pygame.draw.rect(s, col, (ox + 77 + i * 5, oy - 6 + j * 4, 4, 3))
        for i in range(self.hp):
            pygame.draw.rect(s, RED, (ox + 4 + i * 8, oy - 9, 6, 5))
        # the sheet itself
        if fl:
            pygame.draw.rect(s, WHITE, (ox, oy, 106, 84), border_radius=7)
        else:
            s.blit(base, (ox, oy))
            s.blit(rain, (ox + 19, oy + 18), (0, 60 - int(t * 25) % 60, 81, 60))
            s.blit(grid, (ox, oy))
            self.draw_cells(s, ox, oy)

        def cell(c, r):
            return ox + 32 + 27 * c, oy + 28 + 20 * r

        # coin eyes in A1 and C1, pupils follow the player, flip like a coin to blink
        squash = abs(math.cos((1 - self.spin / 0.4) * 2 * math.pi)) if self.spin > 0 else 1.0
        for c in (0, 2):
            cx, cy = cell(c, 0)
            w = max(1.0, 8 * squash)
            pts = [(cx + w * math.cos(a), cy + 8 * math.sin(a)) for a in (math.pi / 8 + k * math.pi / 4 for k in range(8))]
            pygame.draw.polygon(s, (245, 190, 40), pts)
            pygame.draw.polygon(s, (150, 90, 10), pts, 2)
            if squash > 0.6:
                pygame.draw.circle(s, (205, 135, 20), (cx, cy), 5, 1)
                pygame.draw.circle(s, (25, 10, 35), (int(cx + self.look * 3 * squash), cy + 1), 3)
                pygame.draw.circle(s, (255, 245, 180), (int(cx - w * 0.45), cy - 4), 2)
        # zigzag mouth across row 3: chews idly, gapes open before spitting
        opn = max(self.charge, self.gape / 0.3)
        zig = 5 + 1.5 * math.sin(t * 6) - opn
        mx0, my = ox + 24, oy + 68 - int(6 * opn)
        up = [(mx0 + i * 12, my + (-zig if i % 2 else zig)) for i in range(7)]
        if opn > 0.05:
            # gaping maw: dark inside, teeth top and bottom
            gap = 18 * opn
            lo = [(px, py + gap) for px, py in up]
            top, bot = my - zig, my + zig + gap
            pygame.draw.rect(s, (60, 0, 15), (mx0, top, 72, bot - top))
            pygame.draw.polygon(s, (235, 225, 200), up + [(mx0 + 72, top), (mx0, top)])
            pygame.draw.polygon(s, (235, 225, 200), lo + [(mx0 + 72, bot), (mx0, bot)])
            pygame.draw.lines(s, (215, 35, 45), False, lo, 4)
        pygame.draw.lines(s, (215, 35, 45), False, up, 4)
        # drool
        dl = 5 + 7 * (0.5 + 0.5 * math.sin(t * 1.7))
        dx, dy = mx0 + 48, oy + 78
        pygame.draw.line(s, (140, 230, 90), (dx, dy), (dx, dy + dl), 3)
        pygame.draw.circle(s, (140, 230, 90), (dx, int(dy + dl)), 3)
        if fl:
            return
        # selection brackets (jumps to B2 while charging a formula)
        sx, sy = cell(self.sel[0], self.sel[1])
        L = 5
        for ex, ey, hx, vy in ((-13, -9, 1, 1), (13, -9, -1, 1), (-13, 9, 1, -1), (13, 9, -1, -1)):
            px, py = sx + ex, sy + ey
            pygame.draw.line(s, YELLOW, (px, py), (px + hx * L, py), 2)
            pygame.draw.line(s, YELLOW, (px, py), (px, py + vy * L), 2)
        # telegraph: the formula it is about to "calculate"
        if self.charge > 0:
            img = render(self.formula, 18, WHITE)
            bx, by = cell(1, 1)
            box = img.get_rect(center=(bx, by)).inflate(8, 4)
            pygame.draw.rect(s, (10, 10, 15), box)
            pygame.draw.rect(s, QLIK_GREEN, box, 1)
            s.blit(img, img.get_rect(center=(bx, by)))
            self.draw_cursor(s, box.right - 2, box.bottom - 6)

    def draw_cells(self, s, ox, oy):
        t = self.t
        damaged = 4 - self.hp  # cells overflow to ##### as it takes damage

        def cell(c, r):
            return ox + 32 + 27 * c, oy + 28 + 20 * r

        for n, (c, r) in enumerate(((1, 0), (0, 1), (2, 1))):
            cx, cy = cell(c, r)
            if n < damaged:
                draw_text(s, "####", 16, (255, 120, 120), center=(cx, cy), shadow=False)
            elif n < 2:
                pygame.draw.rect(s, (150, 190, 240), (cx - 11, cy - 3, 22, 7), 1)
                for k in range(int((t * 0.9 + n * 0.4) % 1 * 5)):
                    pygame.draw.rect(s, (210, 230, 255), (cx - 9 + k * 4, cy - 1, 3, 3))
            else:
                for k in range(3):
                    bh = 4 + int(7 * abs(math.sin(t * 3 + k)))
                    pygame.draw.rect(s, (150, 200, 245), (cx - 8 + k * 6, cy + 7 - bh, 4, bh), 1)
        if self.charge <= 0:
            bx, by = cell(1, 1)
            self.draw_cursor(s, bx + int(6 * math.sin(t * 1.3)), by - 4 + int(3 * math.sin(t * 2.1)))

    @staticmethod
    def draw_cursor(s, x, y):
        pts = [(x, y), (x, y + 10), (x + 3, y + 7), (x + 5, y + 11), (x + 7, y + 10), (x + 5, y + 6), (x + 9, y + 6)]
        pygame.draw.polygon(s, (110, 230, 140), pts)
        pygame.draw.polygon(s, (0, 0, 0), pts, 1)


class TrainCar(Enemy):
    name = "FIVETRAIN"
    tagline = "Alla ombord på spökpipelinen!"
    r = 22
    points = 120

    def __init__(self, idx, group, phase, amp):
        super().__init__(W / 2, -200)
        self.idx, self.group, self.phase, self.amp = idx, group, phase, amp
        self.u = -idx * 0.42
        self.smoke = 0.0
        if idx == 0:
            self.hp, self.points, self.r = 2, 250, 26

    def move(self, dt, game):
        self.u += dt
        self.x = W / 2 + self.amp * math.sin(self.u * 0.9 + self.phase)
        self.y = -50 + self.u * 58
        if self.idx == 0 and self.y > -20:
            self.smoke -= dt
            if self.smoke <= 0:
                self.smoke = 0.07
                game.particles.append([self.x, self.y - 30, random.uniform(-15, 15), -40,
                                       1.2, 1.2, (110, 100, 120), 6, 1])

    def draw(self, s):
        if self.y < -60:
            return
        x, y = int(self.x), int(self.y)
        fl = self.flash > 0
        if self.idx == 0:
            pygame.draw.rect(s, (60, 60, 70), (x - 6, y - 32, 12, 16))
            pygame.draw.rect(s, WHITE if fl else (125, 30, 35), (x - 26, y - 18, 52, 36), border_radius=6)
            pygame.draw.rect(s, (80, 15, 20), (x - 26, y - 18, 52, 8), border_radius=4)
            for side in (-1, 1):
                pygame.draw.circle(s, YELLOW, (x + side * 10, y - 2), 5)
                pygame.draw.circle(s, (0, 0, 0), (x + side * 10, y), 2)
            pygame.draw.arc(s, (0, 0, 0), (x - 10, y, 20, 12), math.pi, 2 * math.pi, 2)
            blit_glow(s, x, y + 22, 28, YELLOW, 90)
            pygame.draw.circle(s, YELLOW, (x, y + 18), 5)
            draw_text(s, "FIVETRAIN", 20, ORANGE, center=(x, y - 44))
        else:
            pygame.draw.rect(s, WHITE if fl else (60, 58, 78), (x - 22, y - 15, 44, 30), border_radius=4)
            pygame.draw.rect(s, (40, 38, 55), (x - 22, y - 15, 44, 6), border_radius=3)
            for wx in (x - 17, x + 3):
                pygame.draw.rect(s, (255, 215, 90), (wx, y - 6, 14, 12))
                pygame.draw.circle(s, (0, 0, 0), (wx + 4, y - 1), 2)
                pygame.draw.circle(s, (0, 0, 0), (wx + 10, y - 1), 2)
        for side in (-1, 1):
            pygame.draw.circle(s, (30, 30, 35), (x + side * 14, y + 17), 6)
            pygame.draw.circle(s, (120, 120, 130), (x + side * 14, y + 17), 6, 2)


# ----------------------------------------------------------------------- game
class Game:
    def __init__(self, screen, sfx, inp):
        self.screen, self.sfx, self.inp = screen, sfx, inp
        self.world = pygame.Surface((W, H))
        self.bg = Background()
        self.vignette = make_vignette()
        self.title_img, self.drips = make_title()
        self.scores = load_scores()
        self.clock = 0.0
        self.particles, self.floats = [], []
        self.enemies, self.bullets, self.blobs = [], [], []
        self.player = None
        self.shake = 0.0
        self.banner, self.banner_queue = None, []
        self.score, self.elapsed, self.kills, self.hits = 0, 0.0, 0, 0
        self.attract_t = 0.0
        self.new_best, self.rank = False, ""
        self.state, self.state_t = "title", 0.0
        self.sfx.start_drone()

    def set_state(self, state):
        self.state, self.state_t = state, 0.0

    # ---- round lifecycle
    def start_round(self):
        self.enemies.clear(); self.bullets.clear(); self.blobs.clear()
        self.player = Player()
        self.score, self.elapsed, self.kills, self.hits = 0, 0.0, 0, 0
        self.spawn_t = 1.0
        self.seen, self.trains_sent = set(), set()
        self.last_tick = None
        self.banner, self.banner_queue = None, []
        self.sfx.play("start")
        self.sfx.start_music()
        self.set_state("playing")

    def end_round(self):
        for e in self.enemies:
            if e.active():
                self.explode(e.x, e.y, n=16)
        self.enemies.clear(); self.blobs.clear(); self.bullets.clear()
        self.banner, self.banner_queue = None, []
        self.sfx.play("explode")
        self.sfx.play("over")
        self.sfx.start_drone()
        self.shake = 10
        best = self.scores[0] if self.scores else 0
        self.new_best = self.score > 0 and self.score > best
        self.scores = sorted(self.scores + [self.score], reverse=True)[:10]
        save_scores(self.scores)
        self.rank = rank_for(self.score)
        self.set_state("over")

    # ---- update
    def update(self, dt):
        self.clock += dt
        self.state_t += dt
        self.bg.update(dt)
        self.shake = max(0.0, self.shake - dt * 30)
        if self.state == "title":
            self.update_title(dt)
        elif self.state == "playing":
            self.update_play(dt)
        else:
            self.update_over(dt)
        self.update_effects(dt)

    def update_title(self, dt):
        self.attract_t -= dt
        if self.attract_t <= 0:
            self.attract_t = random.uniform(0.6, 1.4)
            cls = random.choice([Spooker, Spooker, Airbite, PowerBooI])
            self.enemies.append(cls(random.uniform(60, W - 60), -40))
        for e in self.enemies:
            e.update(dt, self)
        self.enemies = [e for e in self.enemies if not e.dead]
        if self.inp.any_pressed and self.state_t > 0.5:
            self.start_round()

    def update_over(self, dt):
        if self.state_t > 3.0 and self.inp.any_pressed:
            self.start_round()
        elif self.state_t > 12.0:
            self.set_state("title")

    def update_play(self, dt):
        self.elapsed += dt
        remaining = ROUND_SECONDS - self.elapsed
        if remaining <= 0:
            self.end_round()
            return
        if remaining <= 10:
            sec = math.ceil(remaining)
            if sec != self.last_tick:
                self.last_tick = sec
                self.sfx.play("tick")
        self.spawn(dt)
        self.player.update(dt, self.inp, self)
        for b in self.bullets:
            b.update(dt)
        for e in self.enemies:
            e.update(dt, self)
        for b in self.blobs:
            b.update(dt)
        self.collide()
        self.bullets = [b for b in self.bullets if not b.dead]
        self.enemies = [e for e in self.enemies if not e.dead]
        self.blobs = [b for b in self.blobs if not b.dead]

    def spawn(self, dt):
        el = self.elapsed
        for at in TRAIN_TIMES:
            if el >= at and at not in self.trains_sent:
                self.trains_sent.add(at)
                self.spawn_train()
        self.spawn_t -= dt
        if self.spawn_t > 0:
            return
        interval = max(0.40, 1.2 - el * 0.009)
        self.spawn_t = interval * random.uniform(0.7, 1.3)
        pool = [(Spooker, 5)]
        if el > 6:
            pool.append((Airbite, 3))
        if el > 16:
            pool.append((PowerBooI, 4))
        if el > 26:
            pool.append((TableGhoul, 1.5))
        cls = random.choices([c for c, _ in pool], [w for _, w in pool])[0]
        self.add_enemy(cls(random.uniform(50, W - 50), -40))

    def spawn_train(self):
        group = {"killed": 0}
        amp, phase = random.uniform(220, 300), random.uniform(0, 2 * math.pi)
        for i in range(5):
            self.add_enemy(TrainCar(i, group, phase, amp))
        self.sfx.play("whistle")

    def add_enemy(self, e):
        self.enemies.append(e)
        if e.name not in self.seen:
            self.seen.add(e.name)
            self.banner_queue.append((e.name, e.tagline))

    def collide(self):
        p = self.player
        for b in self.bullets:
            for e in self.enemies:
                if e.dead or not e.active():
                    continue
                if (b.x - e.x) ** 2 + (b.y - e.y) ** 2 < (e.r + 6) ** 2:
                    b.dead = True
                    if e.hit():
                        self.kill(e)
                    else:
                        self.explode(b.x, b.y, colors=[WHITE, QLIK_LIGHT], n=5, speed=120)
                    break
        if p.inv <= 0:
            for e in self.enemies:
                if not e.dead and e.active() and (p.x - e.x) ** 2 + (p.y - e.y) ** 2 < (e.r + 16) ** 2:
                    e.dead = True
                    self.explode(e.x, e.y, n=14)
                    self.player_hit()
                    break
        if p.inv <= 0:
            for bl in self.blobs:
                if (p.x - bl.x) ** 2 + (p.y - bl.y) ** 2 < 30 ** 2:
                    bl.dead = True
                    self.player_hit()
                    break

    def kill(self, e):
        e.dead = True
        self.kills += 1
        self.score += e.points
        self.explode(e.x, e.y)
        self.sfx.play("explode")
        self.shake = max(self.shake, 4)
        self.add_float(e.x, e.y - 10, "+%d" % e.points, QLIK_LIGHT, 30)
        if random.random() < 0.22:
            self.add_float(e.x, e.y + 20, random.choice(KILL_QUIPS), WHITE, 24)
        if isinstance(e, TrainCar):
            e.group["killed"] += 1
            if e.group["killed"] == 5:
                self.score += 500
                self.add_float(W / 2, H / 2, "TÅGKRASCH!  +500", YELLOW, 52, life=2.2)
                self.sfx.play("bonus")

    def player_hit(self):
        p = self.player
        p.inv = 1.6
        self.hits += 1
        self.score = max(0, self.score - HIT_PENALTY)
        self.shake = 14
        self.sfx.play("hit")
        self.explode(p.x, p.y, colors=[RED, ORANGE, WHITE], n=20)
        self.add_float(p.x, p.y - 45, "-%d" % HIT_PENALTY, RED, 32)
        self.add_float(p.x, p.y - 75, random.choice(HIT_QUIPS), RED, 26)

    # ---- effects
    def explode(self, x, y, colors=None, n=26, speed=260):
        colors = colors or CONFETTI
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            v = random.uniform(speed * 0.25, speed)
            life = random.uniform(0.4, 0.9)
            self.particles.append([x, y, math.cos(a) * v, math.sin(a) * v, life, life,
                                   random.choice(colors), random.uniform(2, 5), 0])
        if len(self.particles) > 700:
            del self.particles[:len(self.particles) - 700]

    def add_float(self, x, y, text, color, size, life=1.0):
        self.floats.append([clamp(x, 130, W - 130), y, text, color, life, size, life])

    def update_effects(self, dt):
        for p in self.particles:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            if p[8] == 0:
                p[3] += 160 * dt
                p[2] *= 0.98
            p[4] -= dt
        self.particles = [p for p in self.particles if p[4] > 0]
        for f in self.floats:
            f[1] -= 40 * dt
            f[4] -= dt
        self.floats = [f for f in self.floats if f[4] > 0]
        if self.banner:
            self.banner[2] -= dt
            if self.banner[2] <= 0:
                self.banner = None
        if not self.banner and self.banner_queue and self.state == "playing":
            name, tag = self.banner_queue.pop(0)
            self.banner = [name, tag, 2.6]
            self.sfx.play("boo")

    # ---- draw
    def draw(self):
        w = self.world
        self.bg.draw(w)
        for e in self.enemies:
            e.draw(w)
        for b in self.blobs:
            b.draw(w)
        for b in self.bullets:
            b.draw(w)
        if self.state == "playing":
            self.player.draw(w, self.clock)
        for x, y, _, _, life, ml, col, size, kind in self.particles:
            f = life / ml
            if kind == 0:
                pygame.draw.circle(w, col, (int(x), int(y)), max(1, int(size * f)))
            else:
                pygame.draw.circle(w, lerp_color(col, (15, 8, 25), 1 - f), (int(x), int(y)),
                                   int(size * (1 + (1 - f) * 2)))
        w.blit(self.vignette, (0, 0))
        for x, y, text, col, life, size, ml in self.floats:
            draw_text(w, text, size, col, center=(x, y))
        if self.state == "playing":
            self.draw_hud(w)
        elif self.state == "title":
            self.draw_title(w)
        else:
            self.draw_over(w)
        ox = oy = 0
        if self.shake > 0:
            ox = int(random.uniform(-self.shake, self.shake))
            oy = int(random.uniform(-self.shake, self.shake))
        self.screen.fill((0, 0, 0))
        self.screen.blit(w, (ox, oy))

    def draw_hud(self, w):
        draw_text(w, "POÄNG %d" % self.score, 36, WHITE, topleft=(16, 12))
        best = max(self.scores[0] if self.scores else 0, self.score)
        draw_text(w, "REKORD %d" % best, 36, QLIK_LIGHT, topright=(W - 16, 12))
        remaining = max(0.0, ROUND_SECONDS - self.elapsed)
        sec = math.ceil(remaining)
        if remaining <= 10:
            pulse = 1 - (sec - remaining)
            draw_text(w, str(sec), int(56 + 22 * pulse), RED, center=(W / 2, 36))
        else:
            draw_text(w, str(sec), 52, WHITE, center=(W / 2, 32))
        if self.banner:
            name, tag, _ = self.banner
            draw_text(w, "NYTT SPÖKE UPPTÄCKT", 26, ORANGE, center=(W / 2, 110))
            draw_text(w, name, 64, QLIK_LIGHT, center=(W / 2, 152))
            draw_text(w, tag, 28, WHITE, center=(W / 2, 194))

    def draw_title(self, w):
        rect = self.title_img.get_rect(center=(W / 2, 150 + math.sin(self.clock * 1.5) * 6))
        for dx, dy, off, spd in self.drips:
            length = (self.clock * spd + off) % 55
            sx, sy = rect.x + dx, rect.y + dy - 2
            pygame.draw.line(w, QLIK_GREEN, (sx, sy), (sx, sy + length), 4)
            pygame.draw.circle(w, QLIK_GREEN, (sx, int(sy + length)), 4)
        w.blit(self.title_img, rect)
        draw_text(w, "Det spökar i din data. Vi kan hjälpa till.", 32, WHITE, center=(W / 2, 255))
        if int(self.clock * 2) % 2 == 0:
            draw_text(w, "TRYCK PÅ VALFRI KNAPP", 44, YELLOW, center=(W / 2, 320))
        draw_text(w, "VÄNSTER / HÖGER för att styra   -   MITTEN för att skjuta", 26, GREY, center=(W / 2, 362))
        draw_text(w, "TOPPLISTA", 30, ORANGE, center=(W / 2, 412))
        if self.scores:
            for i, s in enumerate(self.scores[:5]):
                draw_text(w, "%d.  %d" % (i + 1, s), 28, WHITE, center=(W / 2, 442 + i * 24))
        else:
            draw_text(w, "Inga offer än...", 28, GREY, center=(W / 2, 442))

    def draw_over(self, w):
        draw_text(w, "TIDEN ÄR UTE!", 84, ORANGE, center=(W / 2, 130))
        draw_text(w, str(self.score), 120, WHITE, center=(W / 2, 235))
        draw_text(w, "POÄNG", 30, GREY, center=(W / 2, 300))
        draw_text(w, "Rang: " + self.rank, 42, QLIK_LIGHT, center=(W / 2, 355))
        if self.new_best and int(self.clock * 3) % 2 == 0:
            draw_text(w, "NYTT REKORD!", 52, YELLOW, center=(W / 2, 415))
        draw_text(w, "Monster nedskjutna: %d     Gånger skrämd: %d" % (self.kills, self.hits), 28, WHITE,
                  center=(W / 2, 470))
        if self.state_t > 3.0 and int(self.clock * 2) % 2 == 0:
            draw_text(w, "TRYCK PÅ VALFRI KNAPP FÖR ATT SPELA IGEN", 32, YELLOW, center=(W / 2, 520))


# ----------------------------------------------------------------------- main
def main():
    windowed = "--window" in sys.argv
    if not windowed and sys.platform.startswith("linux"):
        # Pi 4 + kmsdrm: SDL's default renderer shows a black screen, GLES2 works
        os.environ.setdefault("SDL_RENDER_DRIVER", "opengles2")
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    flags = pygame.SCALED | (0 if windowed else pygame.FULLSCREEN)
    screen = pygame.display.set_mode((W, H), flags)
    print("pygame %s, SDL %s, video driver %s, display %s" % (
        pygame.version.ver, ".".join(map(str, pygame.get_sdl_version())),
        pygame.display.get_driver(), pygame.display.get_desktop_sizes()))
    pygame.display.set_caption("Qlik or Treat")
    pygame.mouse.set_visible(False)
    game = Game(screen, Sfx(), Input())
    clock = pygame.time.Clock()
    while True:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 20)
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                pygame.quit()
                return
        game.inp.poll()
        steps = FAST_FORWARD if pygame.key.get_pressed()[pygame.K_SPACE] else 1
        for i in range(steps):
            game.update(dt)
            game.inp.any_pressed = False  # edge only counts once per frame
        game.draw()
        pygame.display.flip()


if __name__ == "__main__":
    main()
