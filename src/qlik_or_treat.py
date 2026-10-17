#!/usr/bin/env python3
"""
QLIK OR TREAT  -  a spooky, silly, Qlik-themed arcade shooter for Raspberry Pi.

Controls (3 buttons):  LEFT  |  FIRE  |  RIGHT
  Keyboard:  arrows or A/D to move, UP/W/ENTER to fire (hold for auto-fire), ESC to quit
             type letters for high-score initials (or press FIRE twice quickly to skip)
             hold SPACE to fast-forward (for testing)
  Admin keys: L = Swedish/English, N = new game, M = basic/expert mode (everything faster),
              R = rename the last high score. Language and mode are kept in settings.json.
  GPIO:      one leg of each button to the pin below, other leg to GND
             (internal pull-ups are used, no resistors needed)

Run:
  python3 qlik_or_treat.py            fullscreen (on the Pi)
  python3 qlik_or_treat.py --window   windowed (on your laptop)
  add --wide for widescreen: fullscreen matches the screen's aspect ratio, windowed is 16:9

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
W, H = 800, 600  # W grows with --wide (see set_width); H is always 600
FPS = 60
FAST_FORWARD = 8  # game speed multiplier while SPACE is held (testing aid)
ROUND_SECONDS = 90
HIT_PENALTY = 100
TRAIN_TIMES = (35, 65)  # seconds into the round when the Fivetrain arrives
MID_BOSS_TIME = 46  # Inferno-matica drops by mid-round...
MID_BOSS_STAY = 14  # ...and gives up ("Timeout!") if it isn't beaten by then
BOSS_TIME = 75  # Mega Power BOO-I arrives for the last 15 s
LATE_POWERUPS = 60  # Associative Blast and Answers Bot only drop from here on
SCHEDULED_DROPS = ((62, "assoc"), (BOSS_TIME + 1.5, "bot"))  # everyone gets to see them
EXPERT_SPEED = 1.3  # expert mode: the whole round runs this much faster
ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZÅÄÖ"

PIN_LEFT = int(os.environ.get("PIN_LEFT", 17))    # physical pin 11
PIN_FIRE = int(os.environ.get("PIN_FIRE", 27))    # physical pin 13
PIN_RIGHT = int(os.environ.get("PIN_RIGHT", 22))  # physical pin 15

HERE = os.path.dirname(os.path.abspath(__file__))
SCORE_FILE = os.path.join(HERE, "highscores.json")
SETTINGS_FILE = os.path.join(HERE, "settings.json")  # admin choices: language, expert mode

# -------------------------------------------------------------------- palette
QLIK_GREEN = (0, 152, 69)
QLIK_LIGHT = (130, 230, 150)
WHITE = (240, 240, 250)
GREY = (180, 180, 200)
RED = (235, 50, 60)
ORANGE = (255, 140, 20)
YELLOW = (242, 200, 17)
SICK = (150, 200, 60)
ANSWERS = (175, 130, 255)
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

# All on-screen text is written in Swedish; with LANG = "en", render() swaps it for these.
LANG = "sv"
EN = {
    # quips and ranks
    "Datasilo krossad!": "Data silo smashed!", "Dashboard uppdaterad!": "Dashboard refreshed!",
    "Insikt upplåst!": "Insight unlocked!", "Pipeline rensad!": "Pipeline cleared!",
    "Associerad & eliminerad!": "Associated & eliminated!", "Bu-ja!": "Boo-yah!",
    "Spöket under kontroll!": "Ghost under control!",
    "Aj! Manuell uppdatering!": "Ouch! Manual refresh!", "Datakvalitetsproblem!": "Data quality issue!",
    "Buu! Skrämd!": "Boo! Scared!", "Vilse i en silo!": "Lost in a silo!",
    "Vem beställde en CSV?!": "Who ordered a CSV?!",
    "Kalkylarksöverlevare": "Spreadsheet Survivor", "Dashboardförsvarare": "Dashboard Defender",
    "Insiktsjägare": "Insight Hunter", "Dataspökjägare": "Data Ghostbuster",
    "Chefsspökjägare": "Chief Ghostbusting Officer",
    # power-ups and the Answers Bot
    "PIPELINE-STRÅLE!": "PIPELINE BEAM!", "SKÖLD": "SHIELD", "INSIKTSSKÖLD!": "INSIGHT SHIELD!",
    "QLIK ENGINE: ASSOCIATIV SPRÄNGNING!": "QLIK ENGINE: ASSOCIATIVE BLAST!",
    "QLIK ANSWERS-BOT TILL UNDSÄTTNING!": "QLIK ANSWERS BOT TO THE RESCUE!",
    "Hej! Jag är Qlik Answers!": "Hi! I'm Qlik Answers!",
    "Fråga: var är spöket? Svar: DÄR!": "Q: Where's the ghost? A: THERE!",
    "Enligt dina data: BU!": "According to your data: BOO!",
    "Källa: din egen dashboard": "Source: your own dashboard",
    "Ingen hallucination - det ÄR ett spöke!": "Not a hallucination - it IS a ghost!",
    "Bra fråga! PANG!": "Great question! BANG!", "Svaret är 42... spöken": "The answer is 42... ghosts",
    "Hej då! Fler frågor?": "Bye! Any more questions?",
    "Skjut ett spöke - alla associerade poppar!": "Shoot a ghost - everything associated pops!",
    "VALD!": "SELECTED!", "ASSOCIERAD!": "ASSOCIATED!", "SKÖLDEN HÖLL!": "SHIELD HELD!",
    # monsters
    "#REFERENS!": "#REF!", "#SAKNAS!": "#N/A", "#DIVISION/0!": "#DIV/0!", "#VÄRDEFEL!": "#VALUE!",
    "=SUMMA(A1:C1)": "=SUM(A1:C1)", "=LETARAD(BU)": "=VLOOKUP(BOO)", "=OM(SPÖK;BU)": "=IF(SPOOK,BOO)",
    "=MEDEL(GRAV)": "=AVERAGE(GRAVE)",
    "Lurar i ditt semantiska lager": "Lurking in your semantic layer",
    "Maktgalen och full av BU": "Power-mad and full of BOO",
    "Biter i mer data än den kan tugga": "Bites off more data than it can chew",
    "Dra, släpp... och DREGLA": "Drag, drop... and DROOL",
    "Alla ombord på spökpipelinen!": "All aboard the ghost pipeline!",
    "Sök efter insikter. Hitta slem.": "Search for insights. Find slime.",
    "Mu-hahaha! Spränger dina dashboards": "Moo-hahaha! Blows up your dashboards",
    "Jag ser döda dashboards...": "I see dead dashboards...",
    "MUUU!": "MOOO!", "ATJO!": "ACHOO!", "A... a...": "Ah... ah...",
    "TÅGKRASCH!  +500": "TRAIN WRECK!  +500", "NYTT SPÖKE UPPTÄCKT": "NEW SPOOK DETECTED",
    # bosses
    "MELLANBOSS!": "MID-BOSS!", "Laddar... var god vänta": "Loading... please wait",
    "INFERNO-MATICA RADERAD!": "INFERNO-MATICA DELETED!", "Laddning klar: 100%": "Loading complete: 100%",
    "Timeout! Försöker igen senare...": "Timeout! Retrying later...",
    "BOSS UPPTÄCKT!": "BOSS DETECTED!", "Nu med 47 nya visualiseringar!": "Now with 47 new visuals!",
    "POWER BOO-I AVPUBLICERAD!": "POWER BOO-I UNPUBLISHED!",
    "Uppdatering lyckades: 100%": "Refresh succeeded: 100%",
    "LICENS KRÄVS": "LICENSE REQUIRED", "MÅTT SAKNAS": "MISSING MEASURE", "PRO KRÄVS": "PRO REQUIRED",
    "OGILTIG RELATION": "INVALID RELATIONSHIP",
    "Rapport_FINAL": "Report_FINAL", "Rapport_FINAL_v2": "Report_FINAL_v2",
    "Kopia av Kopia (3)": "Copy of Copy (3)", "Rapport_FINAL_FINAL": "Report_FINAL_FINAL",
    "Rapport (1)": "Report (1)", "Ny rapport 7": "New report 7", "Rapport_ANVÄND_DENNA": "Report_USE_THIS_ONE",
    "UPPGRADERAR TILL PREMIUM-KAPACITET!": "UPGRADING TO PREMIUM CAPACITY!",
    "Uppdatering misslyckades!": "Refresh failed!", "Uppdaterar datamängd...": "Refreshing dataset...",
    # HUD and screens
    "POÄNG": "SCORE", "REKORD": "BEST", "STRÅLE": "BEAM", "ASSOCIATIV": "ASSOC.",
    "Det spökar i din data. Vi kan hjälpa till.": "Your data is haunted. We can help.",
    "TRYCK PÅ VALFRI KNAPP": "PRESS ANY BUTTON",
    "VÄNSTER / HÖGER för att styra   -   MITTEN för att skjuta": "LEFT / RIGHT to steer   -   MIDDLE to shoot",
    "TOPPLISTA": "HIGH SCORES", "Inga offer än...": "No victims yet...",
    "NYTT REKORD!": "NEW HIGH SCORE!", "DU KOM MED PÅ TOPPLISTAN!": "YOU MADE THE TOP 10!",
    "Rang:": "Rank:", "SKRIV DINA INITIALER": "ENTER YOUR INITIALS",
    "VÄNSTER / HÖGER: byt bokstav     MITTEN: välj": "LEFT / RIGHT: change letter     MIDDLE: select",
    "...eller skriv på tangentbordet": "...or type on the keyboard",
    "Tryck MITTEN två gånger snabbt för att hoppa över": "Press MIDDLE twice quickly to skip",
    "TIDEN ÄR UTE!": "TIME'S UP!",
    "Monster nedskjutna: %d     Gånger skrämd: %d": "Monsters zapped: %d     Times scared: %d",
    "%s besegrad!": "%s defeated!", "%s besegrade!": "%s defeated!",
    "TRYCK PÅ VALFRI KNAPP FÖR ATT SPELA IGEN": "PRESS ANY BUTTON TO PLAY AGAIN",
    # admin
    "EXPERTLÄGE": "EXPERT MODE", "BASLÄGE": "BASIC MODE", "BYT NAMN": "RENAME",
    "Inget resultat att byta namn på": "No score to rename",
}


def tr(text):
    return EN.get(text, text) if LANG == "en" else text


def set_lang(lang):
    global LANG
    LANG = "en" if lang == "en" else "sv"


def set_width(aspect):
    """Widen the logical screen to the given aspect ratio (4:3 up to ~16:9)."""
    global W
    W = int(clamp(H * aspect, 800, 1100)) // 2 * 2


def wide_factor():
    return W / 800


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
    """List of (score, initials), best first. Also reads the old format (plain ints)."""
    try:
        with open(SCORE_FILE) as f:
            data = json.load(f)
        scores = []
        for item in data:
            if isinstance(item, dict):
                scores.append((int(item["score"]), str(item.get("name", ""))[:3]))
            else:
                scores.append((int(item), ""))
        return sorted(scores, key=lambda s: -s[0])[:10]
    except Exception:
        return []


def save_scores(scores):
    try:
        with open(SCORE_FILE, "w") as f:
            json.dump([{"score": s, "name": n} for s, n in scores], f)
    except Exception as exc:
        print("Could not save scores:", exc)


def load_settings():
    try:
        with open(SETTINGS_FILE) as f:
            return dict(json.load(f))
    except Exception:
        return {}


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f)
    except Exception as exc:
        print("Could not save settings:", exc)


# ---------------------------------------------------------------- text / glow
_fonts, _text_cache, _glows = {}, {}, {}


def font(size):
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def render(text, size, color):
    text = tr(text)  # every on-screen string passes through here, so this is the one place to translate
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
            pygame.mixer.set_reserved(2)
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

    def beam_loop(self, dur=0.4):
        # buzzy laser hum, whole cycles in 0.4 s so it loops cleanly
        r, tau = self.rate, 2 * math.pi
        out = array.array("h")
        for i in range(int(r * dur)):
            t = i / r
            s = 0.6 * (2 * (110 * t % 1.0) - 1) + 0.4 * math.sin(tau * 440 * t) * math.sin(tau * 5 * t)
            out.append(int(s * 0.1 * 32767))
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
        self.sounds["powerup"] = S(self.seq([523, 784, 1047, 1568], 0.06, "tri", 0.3))
        self.sounds["shield"] = S(T(500, 1000, 0.4, "tri", 0.25, vib=0.1, vibf=20))
        self.sounds["pop"] = S(T(900, 1500, 0.08, "sine", 0.3))
        self.sounds["blip"] = S(T(1800, 900, 0.05, "tri", 0.07))
        self.sounds["hello"] = S(self.seq([660, 880, 1320], 0.08, "sine", 0.25))
        self.sounds["moo"] = S(T(190, 120, 0.7, "saw", 0.22, vib=0.05, vibf=6, attack=0.08))
        self.sounds["boom"] = S(T(120, 25, 0.9, "square", 0.4, noise=0.9))
        self.sounds["splat"] = S(T(400, 120, 0.15, "sine", 0.4, noise=0.3))
        self.sounds["teleport"] = S(T(300, 1500, 0.3, "sine", 0.2, vib=0.3, vibf=30))
        self.sounds["sneeze"] = S(T(900, 200, 0.3, "saw", 0.2, noise=0.7, attack=0.02))
        self.sounds["roar"] = S(T(110, 55, 1.4, "saw", 0.35, vib=0.12, vibf=9, noise=0.3, attack=0.1))
        self.sounds["charge"] = S(T(200, 900, 1.2, "square", 0.07, vib=0.05, vibf=12, attack=0.9))
        self.sounds["fireball"] = S(T(600, 150, 0.35, "saw", 0.14, noise=0.5))
        self.beam_hum = S(self.beam_loop())
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

    def beam(self, on):
        # channel 1 is reserved for the Pipeline beam hum
        if not self.enabled:
            return
        ch = pygame.mixer.Channel(1)
        if on and not ch.get_busy():
            ch.play(self.beam_hum, loops=-1)
        elif not on and ch.get_busy():
            ch.stop()


# ---------------------------------------------------------------------- input
class Controls:
    """Held state + press edges for the three buttons, plus typed keyboard letters."""

    def __init__(self):
        self.left = self.right = self.fire = self.any = False
        self.left_pressed = self.right_pressed = self.fire_pressed = self.any_pressed = False
        self.text_mode = False  # while typing initials, A/D/W are letters, not controls
        self.typed = []  # letters (and "\b" for backspace) typed since last update

    def set(self, left=False, right=False, fire=False):
        pl, pr, pf, pa = self.left, self.right, self.fire, self.any
        self.left, self.right, self.fire = bool(left), bool(right), bool(fire)
        self.any = self.left or self.right or self.fire
        self.left_pressed = self.left and not pl
        self.right_pressed = self.right and not pr
        self.fire_pressed = self.fire and not pf
        self.any_pressed = self.any and not pa

    def clear_edges(self):
        self.left_pressed = self.right_pressed = self.fire_pressed = self.any_pressed = False


class Input(Controls):
    def __init__(self):
        super().__init__()
        self.buttons = None
        try:
            from gpiozero import Button
            self.buttons = (Button(PIN_LEFT, pull_up=True, bounce_time=0.01),
                            Button(PIN_FIRE, pull_up=True, bounce_time=0.01),
                            Button(PIN_RIGHT, pull_up=True, bounce_time=0.01))
            print("GPIO buttons enabled on", PIN_LEFT, PIN_FIRE, PIN_RIGHT)
        except Exception as exc:
            print("GPIO not available, keyboard only (%s: %s)" % (exc.__class__.__name__, exc))

    def poll(self):
        k = pygame.key.get_pressed()
        wasd = not self.text_mode
        l = k[pygame.K_LEFT] or (wasd and k[pygame.K_a])
        r = k[pygame.K_RIGHT] or (wasd and k[pygame.K_d])
        f = k[pygame.K_UP] or (wasd and k[pygame.K_w]) or k[pygame.K_RETURN] or k[pygame.K_KP_ENTER]
        if self.buttons:
            l = l or self.buttons[0].is_pressed
            f = f or self.buttons[1].is_pressed
            r = r or self.buttons[2].is_pressed
        self.set(l, r, f)

    def key_down(self, e):
        if e.key == pygame.K_BACKSPACE:
            self.typed.append("\b")
            return
        ch = (getattr(e, "unicode", "") or "").upper()
        if not ch:
            name = pygame.key.name(e.key)
            ch = name.upper() if len(name) == 1 else ""
        if ch and ch in ALPHABET:
            self.typed.append(ch)


# ----------------------------------------------------------------- background
class Background:
    def __init__(self):
        self.base = pygame.Surface((W, H))
        top, bottom = (6, 3, 18), (30, 8, 40)
        for y in range(H):
            pygame.draw.line(self.base, lerp_color(top, bottom, y / H), (0, y), (W, y))
        self._moon(self.base, W - 140, 105)
        self._graveyard(self.base)
        self.stars = [[random.uniform(0, W), random.uniform(0, H), random.choice((15, 35, 70)),
                       random.choice((1, 1, 2)), random.randint(90, 220)] for _ in range(int(90 * wide_factor()))]
        self.fog = [[random.uniform(-100, W), random.uniform(0, H), random.uniform(8, 18),
                     random.uniform(-6, 6)] for _ in range(round(5 * wide_factor()))]

    def _moon(self, s, x, y):
        s.blit(glow(110, (90, 80, 140), 60), (x - 110, y - 110))
        pygame.draw.circle(s, (225, 225, 200), (x, y), 46)
        for cx, cy, r in ((-14, -10, 9), (12, 8, 12), (-6, 20, 6), (18, -18, 5)):
            pygame.draw.circle(s, (195, 195, 175), (x + cx, y + cy), r)

    def _graveyard(self, s):
        labels = ["RIP", "COGNOS", "EXCEL 97", "CRYSTAL REPORTS", "LOOKER", "CSV", "BUSINESS OBJECTS", "TABLEAU", "RIP"]
        stone = (38, 28, 54)
        x = 20
        for label in labels * 2:  # repeat so wide screens are filled too
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
        self.speed = self.SPEED * wide_factor() ** 0.5  # a bit faster on a wider screen
        self.cool = 0.0
        self.inv = 1.0
        self.tilt = 0.0

    def update(self, dt, inp, game):
        d = (1 if inp.right else 0) - (1 if inp.left else 0)
        self.x = clamp(self.x + d * self.speed * dt, 34, W - 34)
        self.tilt += (d - self.tilt) * min(1.0, dt * 10)
        self.cool -= dt
        self.inv = max(0.0, self.inv - dt)
        game.beam_on = inp.fire and game.beam_t > 0  # the Pipeline beam replaces bullets
        if inp.fire and not game.beam_on and self.cool <= 0:
            game.bullets.append(Bullet(self.x, self.y - 28, kind="sel" if game.assoc_t > 0 else "q"))
            self.cool = 0.15
            game.sfx.play("shoot")

    def draw(self, s, clock, shield=False):
        x, y = int(self.x), int(self.y)
        if shield:
            pulse = int(clock * 6) % 2
            blit_glow(s, x, y, 58, YELLOW, 50 + 20 * pulse)
            pygame.draw.circle(s, YELLOW, (x, y + 4), 44 + pulse * 2, 2)
        if self.inv > 0 and int(clock * 20) % 2 == 0:
            return
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
    """kind: "q" normal, "sel" Associative Blast selection, "bot" fired by the Answers Bot."""

    def __init__(self, x, y, vx=0.0, vy=-760.0, kind="q"):
        self.x, self.y, self.vx, self.vy, self.kind = x, y, vx, vy, kind
        self.dead = False

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y < -20 or self.x < -20 or self.x > W + 20:
            self.dead = True

    def draw(self, s):
        x, y = int(self.x), int(self.y)
        if self.kind == "bot":
            blit_glow(s, x, y, 12, ANSWERS, 120)
            pygame.draw.circle(s, (225, 210, 255), (x, y), 4)
        elif self.kind == "sel":
            blit_glow(s, x, y, 18, QLIK_GREEN, 140)
            pygame.draw.rect(s, WHITE, (x - 3, y - 10, 6, 19), border_radius=3)
        else:
            blit_glow(s, x, y, 12, QLIK_GREEN, 110)
            pygame.draw.rect(s, QLIK_LIGHT, (x - 2, y - 9, 4, 17))


class SlimeBlob:
    """Snot sneezed by Sick-Sense."""
    shootable = False

    def __init__(self, x, y, vx):
        self.x, self.y, self.vx = x, y, vx
        self.t = 0.0
        self.dead = False

    def update(self, dt):
        self.t += dt
        self.x += self.vx * dt
        self.y += 190 * dt
        if self.y > H + 20:
            self.dead = True

    def draw(self, s):
        x, y = int(self.x), int(self.y)
        blit_glow(s, x, y, 24, SICK, 90)
        wob = int(2 * math.sin(self.t * 14))
        pygame.draw.polygon(s, SICK, [(x - 8, y), (x, y - 18 - wob), (x + 8, y)])
        pygame.draw.circle(s, SICK, (x, y + 2), 9 + wob // 2)
        pygame.draw.circle(s, (215, 245, 150), (x - 3, y - 1), 3)


class Fireball:
    """Boss attack (fireballs or bar charts). Can be shot down."""
    shootable = True

    def __init__(self, x, y, vx, vy, style="fire"):
        self.x, self.y, self.vx, self.vy = x, y, vx, vy
        self.style = style  # "fire" (Inferno-matica) or "bar" (Mega Power BOO-I's bar charts)
        self.t = random.uniform(0, 3)
        self.dead = False

    def update(self, dt):
        self.t += dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.y > H + 30 or self.x < -30 or self.x > W + 30:
            self.dead = True

    def draw(self, s):
        x, y = int(self.x), int(self.y)
        if self.style == "bar":
            blit_glow(s, x, y, 28, YELLOW, 90)
            h = 22 + int(4 * math.sin(self.t * 12))
            pygame.draw.rect(s, (200, 150, 0), (x - 8, y - h // 2, 16, h))
            pygame.draw.rect(s, YELLOW, (x - 5, y - h // 2 + 3, 10, h - 6))
            return
        blit_glow(s, x, y, 30, ORANGE, 110)
        for k in (3, 2, 1):
            pygame.draw.circle(s, (200, 60, 10), (int(x - self.vx * 0.025 * k), int(y - self.vy * 0.025 * k)), 9 - 2 * k)
        pygame.draw.circle(s, (255, 90, 20), (x, y), 11 + int(math.sin(self.t * 20) > 0))
        pygame.draw.circle(s, YELLOW, (x, y), 6)


class PowerUp:
    KINDS = {  # kind: (capsule label, colour, pickup text)
        "beam": ("PIPELINE", (70, 170, 255), "PIPELINE-STRÅLE!"),
        "shield": ("SKÖLD", YELLOW, "INSIKTSSKÖLD!"),
        "assoc": ("QLIK ENGINE", QLIK_GREEN, "QLIK ENGINE: ASSOCIATIV SPRÄNGNING!"),
        "bot": ("QLIK ANSWERS", ANSWERS, "QLIK ANSWERS-BOT TILL UNDSÄTTNING!"),
    }

    def __init__(self, x, y, kind):
        self.x, self.y, self.bx, self.kind = x, y, x, kind
        self.t = 0.0
        self.dead = False

    def update(self, dt):
        self.t += dt
        self.y += 105 * dt
        self.x = clamp(self.bx + math.sin(self.t * 2.5) * 18, 30, W - 30)
        if self.y > H + 30:
            self.dead = True

    def draw(self, s):
        label, col, _ = self.KINDS[self.kind]
        x, y = int(self.x), int(self.y)
        blit_glow(s, x, y, 42, col, 70 + 25 * (int(self.t * 8) % 3))
        pygame.draw.circle(s, (20, 12, 35), (x, y), 19)
        pygame.draw.circle(s, col, (x, y), 19, 3)
        draw_powerup_icon(s, self.kind, x, y, col)
        draw_text(s, label, 20, col, center=(x, y + 33))


def draw_powerup_icon(s, kind, x, y, col):
    if kind == "beam":
        pygame.draw.rect(s, (160, 215, 255), (x - 5, y - 11, 10, 22))
        pygame.draw.rect(s, WHITE, (x - 2, y - 11, 4, 22))
    elif kind == "shield":
        pts = [(x - 9, y - 10), (x + 9, y - 10), (x + 9, y), (x, y + 11), (x - 9, y)]
        pygame.draw.polygon(s, col, pts)
        pygame.draw.line(s, (20, 12, 35), (x, y - 6), (x, y + 4), 3)
    elif kind == "assoc":
        # green / white / grey - the three selection states
        a, b, c = (x - 8, y + 6), (x + 8, y + 6), (x, y - 8)
        pygame.draw.line(s, WHITE, a, b, 2)
        pygame.draw.line(s, WHITE, a, c, 2)
        pygame.draw.circle(s, QLIK_GREEN, a, 5)
        pygame.draw.circle(s, WHITE, b, 5)
        pygame.draw.circle(s, (120, 120, 130), c, 5)
    else:
        pygame.draw.rect(s, WHITE, (x - 11, y - 9, 22, 15), border_radius=5)
        pygame.draw.polygon(s, WHITE, [(x - 6, y + 5), (x - 8, y + 11), (x + 1, y + 5)])
        for dx in (-4, 4):
            pygame.draw.circle(s, col, (x + dx, y - 2), 2)


class AnswersBot:
    """Qlik Answers: a chatty helper drone that flies next to you and shoots for 10 s."""
    LIFE = 10.0
    QUIPS = [
        "Hej! Jag är Qlik Answers!", "Fråga: var är spöket? Svar: DÄR!", "Enligt dina data: BU!",
        "Källa: din egen dashboard", "Ingen hallucination - det ÄR ett spöke!", "Bra fråga! PANG!",
        "Svaret är 42... spöken",
    ]

    def __init__(self, player):
        self.x, self.y = player.x, player.y - 80
        self.side = -1 if player.x > W / 2 else 1
        self.left = self.LIFE
        self.t = self.cool = 0.0
        self.quips = self.QUIPS[1:]
        random.shuffle(self.quips)
        self.say, self.say_t, self.qi = self.QUIPS[0], 2.4, 0

    def update(self, dt, game):
        self.t += dt
        self.left -= dt
        p = game.player
        if p.x < 130:
            self.side = 1
        elif p.x > W - 130:
            self.side = -1
        k = min(1.0, dt * 5)
        self.x += (p.x + self.side * 75 - self.x) * k
        self.y += (p.y - 85 + math.sin(self.t * 3) * 8 - self.y) * k
        self.say_t -= dt
        if self.left < 1.6 and self.say != "Hej då! Fler frågor?":
            self.say, self.say_t = "Hej då! Fler frågor?", 1.6
        elif self.say_t < -0.8 and self.left > 3:
            self.say, self.say_t = self.quips[self.qi % len(self.quips)], 2.2
            self.qi += 1
        self.cool -= dt
        if self.cool > 0:
            return
        targets = [e for e in game.enemies if e.active() and not e.dead and e.y < self.y - 30]
        if targets:
            urgent = [e for e in targets if e.y > 300]
            boss = [e for e in targets if e.boss]
            t = max(urgent or boss or targets, key=lambda e: e.y)
            dx, dy = t.x - self.x, t.y - self.y
            d = math.hypot(dx, dy) or 1
            game.bullets.append(Bullet(self.x, self.y - 14, dx / d * 720, dy / d * 720, kind="bot"))
            self.cool = 0.22
            game.sfx.play("blip")

    def draw(self, s):
        if self.left < 2 and int(self.t * 12) % 2 == 0:
            return
        x, y = int(self.x), int(self.y)
        blit_glow(s, x, y, 44, ANSWERS, 70)
        fl = random.randint(6, 12)
        pygame.draw.polygon(s, (120, 200, 255), [(x - 6, y + 16), (x + 6, y + 16), (x, y + 16 + fl)])
        pygame.draw.line(s, (200, 200, 220), (x, y - 16), (x, y - 25), 2)
        pygame.draw.circle(s, RED if int(self.t * 3) % 2 else ANSWERS, (x, y - 26), 4)
        pygame.draw.rect(s, (235, 235, 250), (x - 23, y - 16, 46, 32), border_radius=10)
        pygame.draw.polygon(s, (235, 235, 250), [(x - 14 * self.side, y + 12), (x - 20 * self.side, y + 22),
                                                 (x - 4 * self.side, y + 14)])
        pygame.draw.rect(s, (30, 20, 55), (x - 17, y - 10, 34, 20), border_radius=6)
        blink = int(self.t * 10) % 25 == 0
        for dx in (-7, 7):
            if blink:
                pygame.draw.line(s, (120, 230, 255), (x + dx - 3, y), (x + dx + 3, y), 2)
            else:
                pygame.draw.circle(s, (120, 230, 255), (x + dx, y - 1), 4)
        pygame.draw.arc(s, (120, 230, 255), (x - 6, y + 1, 12, 7), math.pi, 2 * math.pi, 2)
        if self.say_t > 0:
            img = render(self.say, 22, (30, 20, 55))
            box = img.get_rect()
            box.inflate_ip(14, 8)
            box.midbottom = (int(clamp(x, box.width / 2 + 6, W - box.width / 2 - 6)), y - 34)
            pygame.draw.rect(s, WHITE, box, border_radius=8)
            pygame.draw.rect(s, ANSWERS, box, 2, border_radius=8)
            s.blit(img, img.get_rect(center=box.center))


class ErrorBlob:
    """Spreadsheet errors spat out by the Table-Ghoul."""
    shootable = False
    TEXTS = ["#REFERENS!", "#SAKNAS!", "#DIVISION/0!", "#VÄRDEFEL!"]  # Swedish Excel

    def __init__(self, x, y, texts=None, color=RED):
        self.x, self.y = x, y
        self.text = random.choice(texts or self.TEXTS)
        self.color = color
        self.t = random.uniform(0, 1)
        self.dead = False

    def update(self, dt):
        self.t += dt
        self.y += 150 * dt
        self.x += math.sin(self.t * 6) * 50 * dt
        if self.y > H + 20:
            self.dead = True

    def draw(self, s):
        blit_glow(s, self.x, self.y, 26, self.color, 90)
        draw_text(s, self.text, 26, self.color, center=(self.x, self.y))


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
    boss = False

    def __init__(self, x, y):
        self.x, self.y = x, y
        self.t = random.uniform(0, 6)
        self.flash = 0.0
        self.dead = False
        self.hp = type(self).hp
        # Associative Blast: ring colour (green selected / white associated / grey excluded)
        self.mark, self.mark_t, self.frozen, self.chained = None, 0.0, 0.0, False

    def active(self):
        return self.y > -30

    def update(self, dt, game):
        self.mark_t -= dt
        if self.frozen > 0:  # excluded values slow to a crawl
            self.frozen -= dt
            dt *= 0.2
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
    label = None  # copies summoned by Mega Power BOO-I carry a file name

    def move(self, dt, game):
        self.y += 105 * dt
        self.x = clamp(self.bx + math.sin(self.t * 2.6) * 130, 30, W - 30)

    def draw(self, s):
        for i, h in enumerate((10, 16, 22)):
            pygame.draw.rect(s, (200, 150, 0), (int(self.x) - 12 + i * 9, int(self.y - self.r * 1.15) - h + 4, 6, h))
        super().draw(s)
        if self.label:
            draw_text(s, self.label, 18, YELLOW, center=(self.x, self.y + self.r + 14))


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


class SlopSpot(Enemy):
    """A hopping slime that splits in two when shot (big -> medium -> small)."""
    name = "SLOPSPOT"
    tagline = "Sök efter insikter. Hitta slem."
    SIZES = {3: (26, 150), 2: (19, 100), 1: (13, 75)}  # size: (radius, points)

    def __init__(self, x, y, size=3, vx=0.0):
        super().__init__(x, y)
        self.size = size
        self.r, self.points = self.SIZES[size]
        self.vx = vx
        self.pop = -140.0 if vx else 0.0  # children jump up a little when they split off

    def move(self, dt, game):
        self.pop = min(0.0, self.pop + 300 * dt)
        hop = max(0.0, math.sin(self.t * 5)) * 70
        self.y += (60 + hop + self.pop) * dt
        self.x += self.vx * dt
        self.vx *= max(0.0, 1 - 1.5 * dt)
        if not 20 < self.x < W - 20:
            self.vx = -self.vx
            self.x = clamp(self.x, 20, W - 20)

    def split(self, game):
        if self.size > 1:
            for side in (-1, 1):
                game.add_enemy(SlopSpot(self.x + side * 8, self.y, self.size - 1, side * 160))
            game.sfx.play("splat")

    def draw(self, s):
        x, y, r = self.x, self.y, self.r
        sq = 1 + 0.15 * math.sin(self.t * 10)
        w, h = r * 2 * sq, r * 1.7 / sq
        col = WHITE if self.flash > 0 else (235, 85, 175)
        blit_glow(s, x, y, int(r * 1.7), (235, 85, 175), 45)
        for k, dx in enumerate((-0.5, 0.1, 0.55)):
            dl = r * (0.35 + 0.25 * abs(math.sin(self.t * 2 + k)))
            pygame.draw.line(s, col, (x + dx * r, y), (x + dx * r, y + h / 2 + dl), max(2, r // 5))
            pygame.draw.circle(s, col, (int(x + dx * r), int(y + h / 2 + dl)), max(2, r // 6))
        pygame.draw.ellipse(s, col, (x - w / 2, y - h / 2, w, h))
        pygame.draw.ellipse(s, (255, 170, 220), (x - w * 0.32, y - h * 0.38, w * 0.25, h * 0.2))
        for side, er in ((-1, 0.27), (1, 0.2)):  # googly eyes of different sizes
            ex, ey = int(x + side * r * 0.38), int(y - h * 0.08)
            pygame.draw.circle(s, WHITE, (ex, ey), int(r * er) + 1)
            pygame.draw.circle(s, (20, 10, 35), (ex + int(math.sin(self.t * 3) * 2), ey + 1), max(1, int(r * er * 0.5)))
        pygame.draw.arc(s, (90, 10, 60), (x - r * 0.35, y + h * 0.05, r * 0.7, h * 0.3), math.pi, 2 * math.pi, 2)
        if self.size == 3:  # a magnifying glass, it's a search slime
            gx, gy = int(x + r * 1.05), int(y - r * 0.15)
            pygame.draw.line(s, (120, 80, 50), (gx + 4, gy + 5), (gx + 11, gy + 14), 4)
            pygame.draw.circle(s, (200, 230, 255), (gx, gy), 7)
            pygame.draw.circle(s, (90, 90, 110), (gx, gy), 7, 2)


class Boomoo(Enemy):
    """Exploding pumpkin-cow. Shoot it and it takes its neighbours with it;
    let it get low and it moos, swells up and blows up by itself."""
    name = "BOOMOO"
    tagline = "Mu-hahaha! Spränger dina dashboards"
    r = 24
    points = 200
    BLAST = 115

    def __init__(self, x, y):
        super().__init__(x, y)
        self.bx = clamp(x, 60, W - 60)
        self.vy = random.uniform(55, 75)
        self.fuse = None

    def move(self, dt, game):
        if self.fuse is None:
            self.y += self.vy * dt
            self.x = self.bx + math.sin(self.t * 1.6) * 40
            if game.state == "playing" and self.y > H - 260:
                self.fuse = 1.3
                game.sfx.play("moo")
                game.add_float(self.x, self.y - 50, "MUUU!", ORANGE, 34)
        else:
            self.fuse -= dt
            if self.fuse <= 0:
                game.blast(self, by_player=False)

    def draw(self, s):
        armed = self.fuse is not None
        sw = 1 + (0.25 * (1 - self.fuse / 1.3) + 0.06 * math.sin(self.t * 40) if armed else 0)
        r = self.r * sw
        x, y = self.x, self.y
        blink = armed and int(self.t * (8 + 20 * (1 - self.fuse / 1.3))) % 2 == 0
        fl = self.flash > 0
        body = WHITE if fl else RED if blink else ORANGE
        dark = WHITE if fl else (150, 40, 20) if blink else (200, 90, 10)
        if armed:
            blit_glow(s, x, y, int(self.BLAST * 0.8), RED, 50)
        blit_glow(s, x, y, int(r * 1.8), ORANGE, 55)
        for side in (-1, 1):
            pygame.draw.polygon(s, (240, 230, 200), [(x + side * r * 0.45, y - r * 0.65), (x + side * r * 1.0, y - r * 1.25),
                                                     (x + side * r * 0.75, y - r * 0.55)])
            pygame.draw.ellipse(s, (240, 150, 170), (x + side * r * 1.05 - r * 0.25, y - r * 0.45, r * 0.5, r * 0.3))
        for dx in (-0.4, 0.4):  # pumpkin lobes
            pygame.draw.ellipse(s, dark, (x + dx * r - r * 0.6, y - r * 0.8, r * 1.2, r * 1.6))
        pygame.draw.ellipse(s, body, (x - r * 0.55, y - r * 0.84, r * 1.1, r * 1.68))
        if not fl:  # cow spots
            pygame.draw.ellipse(s, (40, 20, 20), (x - r * 0.85, y - r * 0.55, r * 0.45, r * 0.35))
            pygame.draw.ellipse(s, (40, 20, 20), (x + r * 0.45, y + r * 0.05, r * 0.35, r * 0.4))
        for side in (-1, 1):
            pygame.draw.polygon(s, (40, 10, 0), [(x + side * r * 0.15, y - r * 0.15), (x + side * r * 0.55, y - r * 0.15),
                                                 (x + side * r * 0.35, y - r * 0.45)])
        pygame.draw.ellipse(s, (245, 160, 180), (x - r * 0.45, y + r * 0.1, r * 0.9, r * 0.5))
        for side in (-1, 1):
            pygame.draw.circle(s, (120, 40, 60), (int(x + side * r * 0.2), int(y + r * 0.35)), max(2, int(r * 0.08)))
        # fuse on top
        fx, fy = x + r * 0.1, y - r * 0.8
        pygame.draw.line(s, (90, 70, 40), (fx, fy), (fx + 5, fy - 9), 3)
        if int(self.t * 20) % 2 or armed:
            blit_glow(s, fx + 5, fy - 10, 12, YELLOW, 160)
        pygame.draw.circle(s, YELLOW, (int(fx + 5), int(fy - 10)), 3)


class SickSense(Enemy):
    """Sickly psychic eyeball ghost: teleports around and sneezes slime at you."""
    name = "SICK-SENSE"
    tagline = "Jag ser döda dashboards..."
    hp = 2
    r = 24
    points = 250
    TP = 0.7  # teleport takes this long (fade out, move, fade in)

    def __init__(self, x, y):
        super().__init__(x, y)
        self.bx = x
        self.tp, self.tp_wait, self.dest = 0.0, random.uniform(1.6, 2.4), (x, y)
        self.sneeze = random.uniform(2.0, 3.0)
        self.look = 0.0

    def fade(self):
        return clamp(abs(self.tp - self.TP / 2) / (self.TP / 2), 0, 1) if self.tp > 0 else 1.0

    def active(self):
        return self.y > -30 and self.fade() > 0.5  # can't be hit mid-teleport

    def move(self, dt, game):
        if game.player and game.state == "playing":
            self.look = clamp((game.player.x - self.x) / 200, -1, 1)
        if self.tp > 0:
            half = self.tp > self.TP / 2
            self.tp -= dt
            if half and self.tp <= self.TP / 2:
                self.bx, self.y = self.dest
        else:
            self.y += 40 * dt
            self.tp_wait -= dt
            if self.tp_wait <= 0 and 20 < self.y < H - 300:
                self.tp, self.tp_wait = self.TP, random.uniform(1.8, 2.8)
                self.dest = (random.uniform(60, W - 60), min(self.y + random.uniform(20, 80), H - 280))
                if game.state == "playing":
                    game.sfx.play("teleport")
        self.x = self.bx + math.sin(self.t * 1.5) * 20
        if game.state != "playing" or self.tp > 0:
            return
        self.sneeze -= dt
        if self.sneeze <= 0 and 40 < self.y < H - 240:
            vx = clamp((game.player.x - self.x) * 0.4, -120, 120)
            game.blobs.append(SlimeBlob(self.x, self.y + 22, vx))
            game.add_float(self.x, self.y - 40, "ATJO!", SICK, 30, life=0.8)
            game.sfx.play("sneeze")
            self.sneeze = random.uniform(2.6, 4.0)

    def draw(self, s):
        if self.tp > 0:  # shimmer where it is going to appear
            dx, dy = self.dest
            for k in range(3):
                rr = int(8 + 10 * k + 6 * math.sin(self.t * 12 + k))
                pygame.draw.circle(s, SICK, (int(dx), int(dy)), rr, 1)
        a = self.fade()
        if a < 0.1:
            return
        x, y = int(self.x), int(self.y)
        r = int(self.r * (0.3 + 0.7 * a))
        fl = self.flash > 0
        blit_glow(s, x, y, int(r * 2), SICK, 50)
        # ghostly wisps
        pts = [(x - r * 0.8, y)]
        for i in range(7):
            px = x - r * 0.8 + r * 1.6 * i / 6
            pts.append((px, y + r * 1.4 + (6 if i % 2 else -2) + 4 * math.sin(self.t * 7 + i)))
        pts.append((x + r * 0.8, y))
        pygame.draw.polygon(s, WHITE if fl else (110, 160, 45), pts)
        pygame.draw.circle(s, WHITE if fl else (225, 235, 175), (x, y), r)
        if fl:
            return
        for k in range(4):  # bloodshot
            ang = 0.4 + k * 1.6
            pygame.draw.line(s, (210, 60, 60), (x + math.cos(ang) * r * 0.95, y + math.sin(ang) * r * 0.95),
                             (x + math.cos(ang + 0.3) * r * 0.55, y + math.sin(ang + 0.3) * r * 0.55), 1)
        ix = int(x + self.look * r * 0.35)
        pygame.draw.circle(s, (100, 160, 30), (ix, y + 2), int(r * 0.45))
        pygame.draw.circle(s, (15, 10, 20), (ix, y + 2), int(r * 0.22))
        pygame.draw.circle(s, WHITE, (ix - int(r * 0.15), y - int(r * 0.12)), max(1, int(r * 0.1)))
        # droopy sick eyelid; it squints right before a sneeze
        lid = 0.75 if self.sneeze < 0.6 else 0.35
        pygame.draw.ellipse(s, (130, 175, 55), (x - r, y - r, 2 * r, int(2 * r * lid)))
        pygame.draw.circle(s, (80, 120, 30), (x, y), r, 2)
        if self.sneeze < 0.6 and self.y < H - 240:
            draw_text(s, "A... a...", 22, SICK, center=(x, y - r - 16))


def draw_loading(s, x, y, charge, text, color):
    """Boss attack telegraph: the world's slowest loading bar. Sits at 99% for ages, of course."""
    pct = min(99, int(charge * 160))
    bw = 150
    bx = x - bw // 2
    pygame.draw.rect(s, (20, 10, 20), (bx - 2, y - 2, bw + 4, 18))
    pygame.draw.rect(s, color, (bx, y, int(bw * min(charge, 0.99)), 14))
    pygame.draw.rect(s, WHITE, (bx - 2, y - 2, bw + 4, 18), 2)
    draw_text(s, "%s  %d%%" % (tr(text), pct), 22, WHITE, center=(x, y + 30))


class Infernomatica(Enemy):
    """Mid-boss: a big fire demon that takes forever to load its fireballs. Times out and
    leaves after MID_BOSS_STAY seconds if nobody beats it."""
    name = "INFERNO-MATICA"
    title = "Inferno-matica"
    header = "MELLANBOSS!"
    tagline = "Laddar... var god vänta"
    kill_text = "INFERNO-MATICA RADERAD!"
    kill_sub = "Laddning klar: 100%"
    hp = 14
    r = 60
    points = 1000
    boss = True
    glow = ORANGE
    CHARGE = 1.5

    def __init__(self):
        super().__init__(W / 2, -110)
        self.maxhp = self.hp
        self.mt = 0.0
        self.wait = 1.0
        self.charge = 0.0  # 0 = idle, else 0..1 loading
        self.volley = 0
        self.stay = MID_BOSS_STAY
        self.leaving = False

    def active(self):
        return self.y > -40

    def move(self, dt, game):
        self.stay -= dt
        if self.stay <= 0 and not self.leaving and game.state == "playing":
            self.leaving, self.charge = True, 0.0
            game.add_float(self.x, self.y + 90, "Timeout! Försöker igen senare...", ORANGE, 30, life=2.5)
        if self.leaving:
            self.y -= 160 * dt
            if self.y < -140:
                self.dead = True  # gone without a kill - no points
            return
        if self.y < 200:
            self.y += 90 * dt
        else:
            self.mt += dt
            self.x = W / 2 + math.sin(self.mt * 0.55) * (W / 2 - 150)
        if game.state != "playing" or self.y < 160:
            return
        if self.charge > 0:
            self.charge += dt / self.CHARGE
            if self.charge >= 1:
                self.fire(game)
        else:
            self.wait -= dt
            if self.wait <= 0:
                self.charge = 0.001
                game.sfx.play("charge")

    def fire(self, game):
        self.charge, self.wait = 0.0, random.uniform(0.9, 1.5)
        n = 5 if self.volley % 2 == 0 else 3
        self.volley += 1
        base = math.atan2(game.player.y - self.y, game.player.x - self.x)
        for i in range(n):
            a = base + (i - (n - 1) / 2) * 0.32
            game.blobs.append(Fireball(self.x, self.y + 40, math.cos(a) * 210, math.sin(a) * 210))
        game.sfx.play("fireball")
        game.shake = max(game.shake, 5)

    def draw(self, s):
        x, y, t = int(self.x), int(self.y), self.t
        fl = self.flash > 0
        blit_glow(s, x, y, 130, (255, 100, 20), 70)
        for i in range(11):  # flickering flames behind
            a = math.pi + math.pi * i / 10
            ln = 38 + 20 * math.sin(t * 9 + i * 1.7) + (12 if i % 2 else 0)
            col = (RED, ORANGE, YELLOW)[i % 3]
            pts = [(x + math.cos(a - 0.17) * 50, y + math.sin(a - 0.17) * 50),
                   (x + math.cos(a + 0.1 * math.sin(t * 5 + i)) * (52 + ln), y + math.sin(a) * (52 + ln)),
                   (x + math.cos(a + 0.17) * 50, y + math.sin(a + 0.17) * 50)]
            pygame.draw.polygon(s, col, pts)
        for side in (-1, 1):  # horns
            pygame.draw.polygon(s, (50, 20, 25), [(x + side * 30, y - 42), (x + side * 72, y - 100),
                                                  (x + side * 50, y - 40)])
        pygame.draw.circle(s, WHITE if fl else (150, 25, 15), (x, y), 58)
        if fl:
            return
        pygame.draw.ellipse(s, (195, 55, 20), (x - 40, y - 8, 80, 60))
        for side in (-1, 1):  # angry eyes and brows
            ex = x + side * 22
            pygame.draw.polygon(s, YELLOW, [(ex - 13, y - 18), (ex + 13, y - 18), (ex + side * 13, y - 4), (ex - side * 13, y - 10)])
            pygame.draw.circle(s, (20, 0, 0), (ex + side * 2, y - 12), 4)
            pygame.draw.line(s, (40, 0, 0), (x + side * 8, y - 22), (x + side * 38, y - 32), 6)
        opn = 10 + 14 * self.charge
        pygame.draw.ellipse(s, (60, 0, 10), (x - 30, y + 10, 60, opn + 10))
        if self.charge > 0:
            blit_glow(s, x, y + 18, 30, YELLOW, int(60 + 120 * self.charge))
        for k in range(5):
            fx = x - 24 + k * 12
            pygame.draw.polygon(s, (245, 235, 210), [(fx, y + 11), (fx + 8, y + 11), (fx + 4, y + 19)])
        if self.charge > 0:
            draw_loading(s, x, y + 74, self.charge, "Laddar... var god vänta", ORANGE)


class MegaPowerBooI(Enemy):
    """Final boss: a giant Power BOO-I. Loads its data forever, then rains bar charts or
    licence errors, and keeps publishing copies of itself. Loses a crown bar per 20 % HP;
    at half HP it upgrades to Premium and speeds up."""
    name = "MEGA POWER BOO-I"
    title = "Mega Power BOO-I"
    header = "BOSS UPPTÄCKT!"
    tagline = "Nu med 47 nya visualiseringar!"
    kill_text = "POWER BOO-I AVPUBLICERAD!"
    kill_sub = "Uppdatering lyckades: 100%"
    hp = 34
    r = 60
    points = 3000
    boss = True
    glow = YELLOW
    BARS = (34, 50, 66, 50, 38)  # the crown
    ERRORS = ["LICENS KRÄVS", "DAX?!", "MÅTT SAKNAS", "PRO KRÄVS", "OGILTIG RELATION"]
    COPIES = ["Rapport_FINAL", "Rapport_FINAL_v2", "Kopia av Kopia (3)", "Rapport_FINAL_FINAL",
              "Rapport (1)", "Ny rapport 7", "Rapport_ANVÄND_DENNA"]

    def __init__(self):
        super().__init__(W / 2, -120)
        self.maxhp = self.hp
        self.mt = 0.0
        self.wait = 1.2
        self.charge = 0.0
        self.published = 0
        self.summon = 2.0
        self.premium = False
        self.bars = len(self.BARS)
        self.copies = list(self.COPIES)
        random.shuffle(self.copies)

    def active(self):
        return self.y > -40

    def move(self, dt, game):
        if self.y < 225:  # low enough that the crown clears the HUD health bar
            self.y += 90 * dt
        else:
            self.mt += dt * (1.6 if self.premium else 1.0)
            self.x = W / 2 + math.sin(self.mt * 0.6) * (W / 2 - 150)
            self.y = 225 + math.sin(self.mt * 2.1) * 10
        if game.state != "playing" or self.y < 180:
            return
        bars = max(1, math.ceil(len(self.BARS) * self.hp / self.maxhp))
        if bars < self.bars:  # a crown bar falls off
            self.bars = bars
            game.explode(self.x, self.y - self.r - 20, colors=[YELLOW, (200, 150, 0), WHITE], n=18, speed=200)
            game.sfx.play("pop")
        if not self.premium and self.hp <= self.maxhp / 2:
            self.premium = True
            self.name = "MEGA POWER BOO-I PREMIUM"  # HUD only; the class name stays for `seen`
            self.charge, self.wait = 0.0, 2.0  # dramatic pause while it "upgrades"
            game.add_float(W / 2, H / 2 + 80, "UPPGRADERAR TILL PREMIUM-KAPACITET!", YELLOW, 40, life=2.4)
            game.rings.append([self.x, self.y, 20, 420, 0.5, 0.5, YELLOW])
            game.sfx.play("roar")
            game.shake = max(game.shake, 12)
        self.summon -= dt
        if self.summon <= 0:
            self.summon = 3.6 if self.premium else 5.0
            self.publish_copies(game)
        if self.charge > 0:
            self.charge += dt / (1.1 if self.premium else 1.6)
            if self.charge >= 1:
                self.fire(game)
        else:
            self.wait -= dt
            if self.wait <= 0:
                self.charge = 0.001
                game.sfx.play("charge")

    def publish_copies(self, game):
        t = random.uniform(0, 6)
        for side in (-1, 0, 1) if self.premium else (-1, 1):
            c = PowerBooI(self.x + side * 150, self.y + 30)
            c.t = t  # copies zig-zag in lockstep, so their labels never overlap
            c.label = self.copies[self.published % len(self.copies)]
            self.published += 1
            game.add_enemy(c)
        game.sfx.play("boo")

    def fire(self, game):
        self.charge, self.wait = 0.0, random.uniform(0.8, 1.3)
        game.add_float(self.x, self.y + 100, "Uppdatering misslyckades!", RED, 26, life=1.0)
        if random.random() < 0.6:  # a fan of falling bar charts, aimed at the player
            n = 6 if self.premium else 5
            base = math.atan2(game.player.y - self.y, game.player.x - self.x)
            for i in range(n):
                a = base + (i - (n - 1) / 2) * 0.3
                game.blobs.append(Fireball(self.x, self.y + 40, math.cos(a) * 200, math.sin(a) * 200, style="bar"))
            game.sfx.play("fireball")
        else:  # licence errors drift down (can't be shot, dodge them)
            for i in range(4 if self.premium else 3):
                game.blobs.append(ErrorBlob(self.x + (i - 1) * 110, self.y + 50, self.ERRORS, YELLOW))
            game.sfx.play("sneeze")
        game.shake = max(game.shake, 5)

    def draw(self, s):
        x, y, t, r = int(self.x), int(self.y), self.t, self.r
        fl = self.flash > 0
        blit_glow(s, x, y, 130, (255, 210, 40) if self.premium else YELLOW, 80 if self.premium else 55)
        bw = 16
        x0 = x - (self.bars * (bw + 6) - 6) // 2
        for i, h in enumerate(self.BARS[:self.bars]):  # bar-chart crown, one bar per 20 % HP
            h = int(h + 4 * math.sin(t * 4 + i))
            top = y - r - 2 - h
            pygame.draw.rect(s, (200, 150, 0), (x0 + i * (bw + 6), top, bw, h + 14))
            pygame.draw.rect(s, (255, 225, 90), (x0 + i * (bw + 6) + 3, top + 3, bw - 6, 6))
        draw_ghost(s, x, y, r, YELLOW, t, fl)
        if fl:
            return
        cy = y - r * 0.2
        for side in (-1, 1):  # angry brows
            pygame.draw.line(s, (90, 60, 0), (x + side * 8, cy - 18), (x + side * 36, cy - 28), 6)
        if self.charge > 0:
            draw_loading(s, x, y + r + 26, self.charge, "Uppdaterar datamängd...", YELLOW)


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
        self.particles, self.floats, self.rings = [], [], []
        self.enemies, self.bullets, self.blobs, self.powerups, self.chain = [], [], [], [], []
        self.player = self.boss = self.bot = self.boss_dying = None
        self.beam_t = self.assoc_t = 0.0
        self.beam_on = self.shield = False
        self.shake = 0.0
        self.banner, self.banner_queue = None, []
        self.score, self.elapsed, self.kills, self.hits = 0, 0.0, 0, 0
        self.boss_killed, self.name = [], ""
        self.attract_t = 0.0
        self.new_best, self.rank = False, ""
        self.toast_msg = None
        self.last_entry = self.renaming = None  # the most recently saved high score, for R (rename)
        settings = load_settings()
        self.expert = bool(settings.get("expert", False))
        set_lang(settings.get("lang", "sv"))
        self.state, self.state_t = "title", 0.0
        self.sfx.start_drone()

    def set_state(self, state):
        self.state, self.state_t = state, 0.0
        self.inp.text_mode = state == "initials"

    # ---- round lifecycle
    def start_round(self):
        self.enemies.clear(); self.bullets.clear(); self.blobs.clear()
        self.powerups.clear(); self.chain.clear()
        self.player = Player()
        self.boss = self.bot = self.boss_dying = None
        self.beam_t = self.assoc_t = self.beam_tick = 0.0
        self.beam_on = self.shield = False
        self.score, self.elapsed, self.kills, self.hits = 0, 0.0, 0, 0
        self.boss_killed, self.name = [], ""
        self.spawn_t = 1.0
        self.drop_cool = 0.0
        self.drops_due = list(SCHEDULED_DROPS)
        self.seen, self.trains_sent = set(), set()
        self.last_tick = None
        self.banner, self.banner_queue = None, []
        self.sfx.play("start")
        self.sfx.start_music()
        self.set_state("playing")

    def end_round(self):
        for e in self.enemies:
            if e.active():
                self.explode(e.x, e.y, n=60 if e.boss else 16)
        self.enemies.clear(); self.blobs.clear(); self.bullets.clear()
        self.powerups.clear(); self.chain.clear()
        self.boss = self.bot = self.boss_dying = None
        self.beam_on = False
        self.sfx.beam(False)
        self.banner, self.banner_queue = None, []
        self.sfx.play("explode")
        self.sfx.play("over")
        self.sfx.start_drone()
        self.shake = 10
        best = self.scores[0][0] if self.scores else 0
        self.new_best = self.score > 0 and self.score > best
        self.rank = rank_for(self.score)
        if self.score > 0 and (len(self.scores) < 10 or self.score > self.scores[-1][0]):
            self.begin_initials()
        else:
            self.set_state("over")

    def begin_initials(self, renaming=None):
        self.renaming = renaming
        self.letters, self.cur, self.last_fire, self.rep, self.idle = [], 0, -9.0, 0.0, 0.0
        self.set_state("initials")

    def save_score(self, name):
        if self.renaming:
            # admin rename: swap the name on the same entry, then show the list
            i = next((i for i, e in enumerate(self.scores) if e is self.renaming), None)
            if i is not None:
                self.scores[i] = self.last_entry = (self.renaming[0], name)
                save_scores(self.scores)
            self.renaming = None
            self.set_state("title")
            return
        self.name = name
        self.last_entry = (self.score, name)
        self.scores = sorted(self.scores + [self.last_entry], key=lambda s: -s[0])[:10]
        save_scores(self.scores)
        self.set_state("over")

    # ---- admin keys (keyboard only, hidden from players)
    def admin_key(self, key):
        """L = language, N = new game, M = basic/expert mode, R = rename the last high score.
        Ignored while initials are being typed, since those are letters too."""
        if self.inp.text_mode:
            return
        if key == pygame.K_l:
            set_lang("sv" if LANG == "en" else "en")
            self.save_settings()
            self.toast("SPRÅK: SVENSKA" if LANG == "sv" else "LANGUAGE: ENGLISH", QLIK_LIGHT)
        elif key == pygame.K_m:
            self.expert = not self.expert
            self.save_settings()
            self.toast("EXPERTLÄGE" if self.expert else "BASLÄGE", RED if self.expert else QLIK_LIGHT)
        elif key == pygame.K_n:
            self.start_round()  # a round in progress is simply thrown away
        elif key == pygame.K_r:
            if self.state == "playing":
                return  # don't throw away a round in progress
            if any(e is self.last_entry for e in self.scores):
                self.begin_initials(renaming=self.last_entry)
            else:
                self.toast("Inget resultat att byta namn på", GREY)

    def save_settings(self):
        save_settings({"lang": LANG, "expert": self.expert})

    def toast(self, text, color):
        self.toast_msg = [text, color, 2.0]  # drawn on top of everything, see draw_toast

    # ---- update
    def update(self, dt):
        if self.expert and self.state == "playing":
            dt *= EXPERT_SPEED  # everything speeds up, the round clock too
        self.clock += dt
        self.state_t += dt
        self.bg.update(dt)
        self.shake = max(0.0, self.shake - dt * 30)
        if self.state == "title":
            self.update_title(dt)
        elif self.state == "playing":
            self.update_play(dt)
        elif self.state == "initials":
            self.update_initials(dt)
        else:
            self.update_over(dt)
        self.inp.typed.clear()
        self.update_effects(dt)

    def update_title(self, dt):
        self.attract_t -= dt
        if self.attract_t <= 0:
            self.attract_t = random.uniform(0.6, 1.4) / wide_factor()
            cls = random.choice([Spooker, Spooker, Airbite, PowerBooI, SlopSpot, SickSense])
            self.enemies.append(cls(random.uniform(60, W - 60), -40))
        for e in self.enemies:
            e.update(dt, self)
        self.enemies = [e for e in self.enemies if not e.dead]
        if self.inp.any_pressed and self.state_t > 0.5:
            self.start_round()

    def update_initials(self, dt):
        """3 slots. LEFT/RIGHT cycle the letter (hold to repeat), FIRE confirms it,
        FIRE twice quickly skips. A keyboard can type letters directly (Backspace undoes)."""
        inp = self.inp
        if self.state_t < 1.0:  # ignore button mashing left over from the round
            return
        self.idle += dt
        if self.idle > 25:  # walked away: keep whatever was entered (a rename is cancelled)
            if self.renaming:
                self.renaming = None
                self.set_state("title")
            else:
                self.save_score("".join(self.letters))
            return
        for ch in inp.typed:
            self.idle = 0.0
            if ch == "\b":
                if self.letters:
                    self.cur = ALPHABET.index(self.letters.pop())
            else:
                self.letters.append(ch)
                self.cur = ALPHABET.index(ch)
                self.sfx.play("blip")
                if len(self.letters) == 3:
                    self.save_score("".join(self.letters))
                    self.sfx.play("bonus")
                    return
        if inp.fire_pressed:
            self.idle = 0.0
            if self.state_t - self.last_fire < 0.35:
                self.save_score("")
                self.sfx.play("pop")
                return
            self.last_fire = self.state_t
            self.letters.append(ALPHABET[self.cur])
            self.sfx.play("blip")
            if len(self.letters) == 3:
                self.save_score("".join(self.letters))
                self.sfx.play("bonus")
                return
        d = (1 if inp.right else 0) - (1 if inp.left else 0)
        if inp.left_pressed or inp.right_pressed:
            self.rep = 0.4
        elif d:
            self.rep -= dt
            if self.rep > 0:
                d = 0
            else:
                self.rep = 0.09
        else:
            d = 0
        if d:
            self.idle = 0.0
            self.cur = (self.cur + d) % len(ALPHABET)
            self.sfx.play("tick")

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
        self.update_powers(dt)
        for b in self.bullets:
            b.update(dt)
        for e in self.enemies:
            e.update(dt, self)
        for b in self.blobs:
            b.update(dt)
        self.update_chain(dt)
        self.collide()
        self.bullets = [b for b in self.bullets if not b.dead]
        self.enemies = [e for e in self.enemies if not e.dead]
        self.blobs = [b for b in self.blobs if not b.dead]
        self.powerups = [pu for pu in self.powerups if not pu.dead]

    def spawn(self, dt):
        el = self.elapsed
        for at in TRAIN_TIMES:
            if el >= at and at not in self.trains_sent:
                self.trains_sent.add(at)
                self.spawn_train()
        for at, cls in ((MID_BOSS_TIME, Infernomatica), (BOSS_TIME, MegaPowerBooI)):
            if el >= at and cls.name not in self.seen and (self.boss is None or self.boss.dead):
                self.spawn_boss(cls)
        for due in list(self.drops_due):
            if el >= due[0]:
                self.drops_due.remove(due)
                self.powerups.append(PowerUp(random.uniform(W * 0.3, W * 0.7), -20, due[1]))
        self.spawn_t -= dt
        if self.spawn_t > 0:
            return
        boss = self.boss is not None and not self.boss.dead
        interval = max(0.40, 1.2 - el * 0.009) / wide_factor()  # same density on wide screens
        if boss:
            interval *= 2.0  # give the player room to fight the boss
        self.spawn_t = interval * random.uniform(0.7, 1.3)
        pool = [(Spooker, 5)]
        if el > 6:
            pool.append((Airbite, 3))
        if el > 12:
            pool.append((SlopSpot, 2.5))
        if el > 18:
            pool.append((PowerBooI, 4))
        if el > 26 and not boss:
            pool.append((TableGhoul, 1.5))
        if el > 42:
            pool.append((Boomoo, 2))
        if el > 52 and not boss:
            pool.append((SickSense, 2))
        cls = random.choices([c for c, _ in pool], [w for _, w in pool])[0]
        self.add_enemy(cls(random.uniform(50, W - 50), -40))

    def spawn_train(self):
        group = {"killed": 0}
        amp, phase = random.uniform(220, 300) * wide_factor(), random.uniform(0, 2 * math.pi)
        for i in range(5):
            self.add_enemy(TrainCar(i, group, phase, amp))
        self.sfx.play("whistle")

    def spawn_boss(self, cls):
        self.boss = cls()
        self.seen.add(self.boss.name)
        self.add_enemy(self.boss)
        self.banner = [self.boss.header, self.boss.name, self.boss.tagline, 3.0, RED, 330]  # below the boss
        self.sfx.play("roar")
        self.shake = 12

    def add_enemy(self, e):
        self.enemies.append(e)
        if e.name not in self.seen:
            self.seen.add(e.name)
            self.banner_queue.append((e.name, e.tagline))

    # ---- power-ups
    def update_powers(self, dt):
        p = self.player
        self.drop_cool -= dt
        if self.beam_on:  # the beam only drains while FIRE is held
            self.beam_t = max(0.0, self.beam_t - dt)
        self.assoc_t = max(0.0, self.assoc_t - dt)
        self.sfx.beam(self.beam_on)
        if self.beam_on:
            self.beam_tick -= dt
            if self.beam_tick <= 0:
                self.beam_tick = 0.09
                for e in list(self.enemies):
                    if not e.dead and e.active() and abs(e.x - p.x) < e.r + 20 and e.y < p.y:
                        self.damage(e, 0.5 if e.boss else 1)
                for bl in self.blobs:
                    if abs(bl.x - p.x) < 26 and bl.y < p.y:
                        bl.dead = True
        if self.bot:
            self.bot.update(dt, self)
            if self.bot.left <= 0:
                self.explode(self.bot.x, self.bot.y, colors=[ANSWERS, WHITE], n=14, speed=150)
                self.bot = None
        if self.boss_dying:
            bd = self.boss_dying
            bd[2] -= dt
            if int(bd[2] / 0.07) != int((bd[2] + dt) / 0.07):
                self.explode(bd[0] + random.uniform(-60, 60), bd[1] + random.uniform(-50, 50), n=18)
                self.sfx.play("explode")
            if bd[2] <= 0:
                self.explode(bd[0], bd[1], n=140, speed=420)
                self.rings.append([bd[0], bd[1], 20, 520, 0.7, 0.7, bd[3]])
                self.sfx.play("boom")
                self.shake = 20
                self.boss_dying = None
        for pu in self.powerups:
            pu.update(dt)
            if (pu.x - p.x) ** 2 + (pu.y - p.y) ** 2 < 44 ** 2:
                pu.dead = True
                self.take_powerup(pu.kind)

    def maybe_drop(self, e):
        if e.boss or e.chained or self.drop_cool > 0 or len(self.powerups) >= 2:
            return
        if random.random() >= (0.35 if isinstance(e, TableGhoul) else 0.07):
            return
        kinds = ["beam", "shield"] + (["assoc", "bot"] if self.elapsed >= LATE_POWERUPS else [])
        self.powerups.append(PowerUp(e.x, e.y, random.choice(kinds)))
        self.drop_cool = 5.0

    def take_powerup(self, kind):
        p = self.player
        _, col, text = PowerUp.KINDS[kind]
        if kind == "beam":
            self.beam_t = 5.0
        elif kind == "shield":
            self.shield = True
        elif kind == "assoc":
            self.assoc_t = 8.0
            self.add_float(W / 2, H / 2 + 40, "Skjut ett spöke - alla associerade poppar!", WHITE, 28, life=2.2)
        else:
            self.bot = AnswersBot(p)
            self.sfx.play("hello")
        self.add_float(W / 2, H / 2, text, col, 40, life=2.0)
        self.explode(p.x, p.y - 10, colors=[col, WHITE], n=24, speed=200)
        self.rings.append([p.x, p.y, 10, 300, 0.4, 0.4, col])
        self.sfx.play("powerup")

    def associate(self, e):
        """Qlik Engine Associative Blast: the hit ghost is selected (green), ghosts of the
        same type are associated (white) and chain-pop, the rest are excluded (grey) and stall."""
        if e.boss:
            self.damage(e, 2)
            return
        others = [o for o in self.enemies if o is not e and not o.dead and o.active() and not o.boss and not o.chained]
        dist = lambda o: (o.x - e.x) ** 2 + (o.y - e.y) ** 2  # noqa: E731
        assoc = [o for o in others if type(o) is type(e)]
        if len(assoc) < 3:  # always pop at least a few
            assoc += sorted((o for o in others if o not in assoc), key=dist)[:3 - len(assoc)]
        assoc.sort(key=dist)
        fx, fy = e.x, e.y
        for i, o in enumerate(assoc):
            o.mark, o.mark_t, o.frozen, o.chained = WHITE, 9.0, 9.0, True
            self.chain.append([0.18 + i * 0.13, o, fx, fy])
            fx, fy = o.x, o.y
        for o in others:
            if o not in assoc:
                o.mark, o.mark_t, o.frozen = (120, 120, 130), 1.6, 1.6
        self.rings.append([e.x, e.y, 10, 380, 0.5, 0.5, QLIK_GREEN])
        self.add_float(e.x, e.y - 30, "VALD!", QLIK_GREEN, 30, life=0.8)
        self.kill(e)

    def update_chain(self, dt):
        for link in self.chain:
            link[0] -= dt
            o = link[1]
            if link[0] <= 0 and not o.dead:
                self.add_float(o.x, o.y - 24, "ASSOCIERAD!", WHITE, 22, life=0.7)
                self.rings.append([o.x, o.y, 6, 200, 0.3, 0.3, QLIK_GREEN])
                self.sfx.play("pop")
                self.kill(o)
        self.chain = [c for c in self.chain if c[0] > 0 and not c[1].dead]

    def blast(self, e, by_player):
        """A Boomoo goes off. Shot by the player it kills its neighbours (and hurts the
        boss); going off by itself it can scare the player instead."""
        e.dead = True
        self.explode(e.x, e.y, colors=[ORANGE, YELLOW, RED, WHITE], n=50, speed=340)
        self.rings.append([e.x, e.y, 10, 500, 0.35, 0.35, ORANGE])
        self.sfx.play("boom")
        self.shake = max(self.shake, 12)
        if by_player:
            for o in list(self.enemies):
                if not o.dead and o.active() and (o.x - e.x) ** 2 + (o.y - e.y) ** 2 < (Boomoo.BLAST + o.r) ** 2:
                    self.damage(o, 4 if o.boss else 99)
        else:
            p = self.player
            if p.inv <= 0 and (p.x - e.x) ** 2 + (p.y - e.y) ** 2 < (Boomoo.BLAST + 16) ** 2:
                self.player_hit()

    # ---- collisions and scoring
    def collide(self):
        p = self.player
        for b in self.bullets:
            for e in self.enemies:
                if e.dead or not e.active():
                    continue
                if (b.x - e.x) ** 2 + (b.y - e.y) ** 2 < (e.r + 6) ** 2:
                    b.dead = True
                    if b.kind == "sel":
                        self.associate(e)
                    else:
                        self.damage(e, 1, spark=(b.x, b.y))
                    break
            if b.dead:
                continue
            for bl in self.blobs:
                if bl.shootable and not bl.dead and (b.x - bl.x) ** 2 + (b.y - bl.y) ** 2 < 18 ** 2:
                    b.dead = bl.dead = True
                    self.score += 25
                    self.explode(bl.x, bl.y, colors=[ORANGE, YELLOW], n=10, speed=150)
                    self.add_float(bl.x, bl.y, "+25", ORANGE, 24, life=0.6)
                    break
        if p.inv <= 0:
            for e in self.enemies:
                if not e.dead and not e.boss and e.active() and (p.x - e.x) ** 2 + (p.y - e.y) ** 2 < (e.r + 16) ** 2:
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

    def damage(self, e, n, spark=None):
        if e.dead:
            return
        e.hp -= n
        e.flash = 0.08
        if e.hp <= 0:
            self.kill(e)
        elif spark:
            self.explode(spark[0], spark[1], colors=[WHITE, QLIK_LIGHT], n=5, speed=120)

    def kill(self, e):
        if isinstance(e, Boomoo) and not e.dead:
            self.blast(e, by_player=True)
        e.dead = True
        self.kills += 1
        self.score += e.points
        self.explode(e.x, e.y)
        self.sfx.play("explode")
        self.shake = max(self.shake, 4)
        self.add_float(e.x, e.y - 10, "+%d" % e.points, QLIK_LIGHT, 30)
        if random.random() < 0.22:
            self.add_float(e.x, e.y + 20, random.choice(KILL_QUIPS), WHITE, 24)
        if isinstance(e, SlopSpot):
            e.split(self)
        if isinstance(e, TrainCar):
            e.group["killed"] += 1
            if e.group["killed"] == 5:
                self.score += 500
                self.add_float(W / 2, H / 2, "TÅGKRASCH!  +500", YELLOW, 52, life=2.2)
                self.sfx.play("bonus")
        if e.boss:
            self.boss_killed.append(e.title)
            self.boss_dying = [e.x, e.y, 1.4, e.glow]
            for bl in self.blobs:
                bl.dead = True
                self.explode(bl.x, bl.y, colors=[GREY], n=6, speed=80)
            self.add_float(W / 2, H / 2 - 40, "%s  +%d" % (tr(e.kill_text), e.points), YELLOW, 46, life=3.0)
            self.add_float(W / 2, H / 2 + 10, e.kill_sub, WHITE, 30, life=3.0)
            self.sfx.play("roar")
            self.sfx.play("bonus")
            self.shake = 16
        self.maybe_drop(e)

    def player_hit(self):
        p = self.player
        if self.shield:
            self.shield = False
            p.inv = 1.0
            self.sfx.play("shield")
            self.explode(p.x, p.y, colors=[YELLOW, WHITE], n=20)
            self.rings.append([p.x, p.y, 30, 260, 0.35, 0.35, YELLOW])
            self.add_float(p.x, p.y - 60, "SKÖLDEN HÖLL!", YELLOW, 30)
            return
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
        for r in self.rings:
            r[2] += r[3] * dt
            r[4] -= dt
        self.rings = [r for r in self.rings if r[4] > 0]
        if self.toast_msg:
            self.toast_msg[2] -= dt
            if self.toast_msg[2] <= 0:
                self.toast_msg = None
        if self.banner:
            self.banner[3] -= dt
            if self.banner[3] <= 0:
                self.banner = None
        if not self.banner and self.banner_queue and self.state == "playing":
            name, tag = self.banner_queue.pop(0)
            self.banner = ["NYTT SPÖKE UPPTÄCKT", name, tag, 2.6, ORANGE, 110]
            self.sfx.play("boo")

    # ---- draw
    def draw(self):
        w = self.world
        playing = self.state == "playing"
        self.bg.draw(w)
        for e in self.enemies:
            e.draw(w)
        for _, o, fx, fy in self.chain:  # association links
            pygame.draw.line(w, QLIK_GREEN, (int(fx), int(fy)), (int(o.x), int(o.y)), 3)
        for e in self.enemies:
            if e.mark and e.mark_t > 0:
                pygame.draw.circle(w, e.mark, (int(e.x), int(e.y)), int(e.r + 10), 3)
        for pu in self.powerups:
            pu.draw(w)
        for b in self.blobs:
            b.draw(w)
        for b in self.bullets:
            b.draw(w)
        if playing:
            if self.beam_on:
                self.draw_beam(w)
            if self.bot:
                self.bot.draw(w)
            self.player.draw(w, self.clock, self.shield)
        for x, y, _, _, life, ml, col, size, kind in self.particles:
            f = life / ml
            if kind == 0:
                pygame.draw.circle(w, col, (int(x), int(y)), max(1, int(size * f)))
            else:
                pygame.draw.circle(w, lerp_color(col, (15, 8, 25), 1 - f), (int(x), int(y)),
                                   int(size * (1 + (1 - f) * 2)))
        for x, y, r, _, life, ml, col in self.rings:
            pygame.draw.circle(w, lerp_color(col, (15, 8, 25), 1 - life / ml), (int(x), int(y)), int(r), 4)
        w.blit(self.vignette, (0, 0))
        for x, y, text, col, life, size, ml in self.floats:
            draw_text(w, text, size, col, center=(x, y))
        if playing:
            self.draw_hud(w)
        elif self.state == "title":
            self.draw_title(w)
        elif self.state == "initials":
            self.draw_initials(w)
        else:
            self.draw_over(w)
        if self.toast_msg:
            self.draw_toast(w)
        ox = oy = 0
        if self.shake > 0:
            ox = int(random.uniform(-self.shake, self.shake))
            oy = int(random.uniform(-self.shake, self.shake))
        self.screen.fill((0, 0, 0))
        self.screen.blit(w, (ox, oy))

    def draw_toast(self, w):
        text, col, _ = self.toast_msg
        img = render(text, 48, col)
        box = img.get_rect(center=(W // 2, H // 2)).inflate(48, 28)
        pygame.draw.rect(w, (15, 8, 25), box, border_radius=12)
        pygame.draw.rect(w, col, box, 3, border_radius=12)
        w.blit(img, img.get_rect(center=box.center))

    def draw_beam(self, w):
        p = self.player
        x, top = int(p.x), int(p.y) - 26
        hw = 14 + int(4 * math.sin(self.clock * 50))
        pygame.draw.rect(w, (30, 90, 200), (x - hw - 6, 0, 2 * hw + 12, top))
        pygame.draw.rect(w, (90, 170, 255), (x - hw, 0, 2 * hw, top))
        pygame.draw.rect(w, WHITE, (x - 4, 0, 8, top))
        blit_glow(w, x, top, 40, (90, 170, 255), 160)
        for _ in range(3):
            sy = random.uniform(0, top)
            pygame.draw.circle(w, WHITE, (x + random.randint(-hw - 8, hw + 8), int(sy)), 2)

    def draw_hud(self, w):
        draw_text(w, "%s %d" % (tr("POÄNG"), self.score), 36, WHITE, topleft=(16, 12))
        best = max(self.scores[0][0] if self.scores else 0, self.score)
        draw_text(w, "%s %d" % (tr("REKORD"), best), 36, QLIK_LIGHT, topright=(W - 16, 12))
        remaining = max(0.0, ROUND_SECONDS - self.elapsed)
        sec = math.ceil(remaining)
        if remaining <= 10:
            pulse = 1 - (sec - remaining)
            draw_text(w, str(sec), int(56 + 22 * pulse), RED, center=(W / 2, 36))
        else:
            draw_text(w, str(sec), 52, WHITE, center=(W / 2, 32))
        # active power-ups under the score
        y = 52
        for label, left, total, col in (("STRÅLE", self.beam_t, 5.0, (90, 170, 255)),
                                        ("ASSOCIATIV", self.assoc_t, 8.0, QLIK_GREEN),
                                        ("ANSWERS", self.bot.left if self.bot else 0, AnswersBot.LIFE, ANSWERS)):
            if left > 0:
                draw_text(w, label, 22, col, topleft=(16, y))
                pygame.draw.rect(w, (40, 30, 60), (118, y + 3, 80, 10))
                pygame.draw.rect(w, col, (118, y + 3, int(80 * left / total), 10))
                y += 22
        if self.shield:
            draw_text(w, "SKÖLD", 22, YELLOW, topleft=(16, y))
        if self.expert:
            draw_text(w, "EXPERT", 22, RED, topright=(W - 16, 44))
        if self.boss and not self.boss.dead and self.boss.active():
            b = self.boss
            bw = 340
            draw_text(w, b.name, 24, ORANGE, center=(W / 2, 66))
            pygame.draw.rect(w, (40, 10, 10), (W // 2 - bw // 2, 78, bw, 12))
            pygame.draw.rect(w, RED, (W // 2 - bw // 2, 78, int(bw * max(0, b.hp) / b.maxhp), 12))
            pygame.draw.rect(w, WHITE, (W // 2 - bw // 2, 78, bw, 12), 1)
        if self.banner:
            header, name, tag, _, col, y = self.banner
            draw_text(w, header, 26, col, center=(W / 2, y))
            draw_text(w, name, 64, QLIK_LIGHT, center=(W / 2, y + 42))
            draw_text(w, tag, 28, WHITE, center=(W / 2, y + 84))

    def draw_title(self, w):
        rect = self.title_img.get_rect(center=(W / 2, 150 + math.sin(self.clock * 1.5) * 6))
        for dx, dy, off, spd in self.drips:
            length = (self.clock * spd + off) % 55
            sx, sy = rect.x + dx, rect.y + dy - 2
            pygame.draw.line(w, QLIK_GREEN, (sx, sy), (sx, sy + length), 4)
            pygame.draw.circle(w, QLIK_GREEN, (sx, int(sy + length)), 4)
        w.blit(self.title_img, rect)
        if self.expert:
            draw_text(w, "EXPERTLÄGE", 30, RED, center=(W / 2, 222))
        draw_text(w, "Det spökar i din data. Vi kan hjälpa till.", 32, WHITE, center=(W / 2, 255))
        if int(self.clock * 2) % 2 == 0:
            draw_text(w, "TRYCK PÅ VALFRI KNAPP", 44, YELLOW, center=(W / 2, 320))
        draw_text(w, "VÄNSTER / HÖGER för att styra   -   MITTEN för att skjuta", 26, GREY, center=(W / 2, 362))
        draw_text(w, "TOPPLISTA", 30, ORANGE, center=(W / 2, 410))
        if not self.scores:
            draw_text(w, "Inga offer än...", 28, GREY, center=(W / 2, 442))
        for i, (s, name) in enumerate(self.scores[:10]):
            col, row = divmod(i, 5)
            cx = W / 2 if len(self.scores) <= 5 else W / 2 + (col * 2 - 1) * 160
            y = 428 + row * 24
            c = YELLOW if i == 0 else WHITE
            draw_text(w, "%d." % (i + 1), 28, GREY, topright=(int(cx - 80), y))
            draw_text(w, name or "---", 28, c, topleft=(int(cx - 68), y))
            draw_text(w, str(s), 28, c, topright=(int(cx + 110), y))

    def draw_initials(self, w):
        score = self.renaming[0] if self.renaming else self.score
        if self.renaming:
            draw_text(w, "%s: %s" % (tr("BYT NAMN"), self.renaming[1] or "---"), 72, RED, center=(W / 2, 80))
        elif self.new_best:
            draw_text(w, "NYTT REKORD!", 72, YELLOW, center=(W / 2, 80))
        else:
            draw_text(w, "DU KOM MED PÅ TOPPLISTAN!", 60, ORANGE, center=(W / 2, 80))
        draw_text(w, str(score), 90, WHITE, center=(W / 2, 160))
        draw_text(w, tr("Rang:") + " " + tr(rank_for(score)), 36, QLIK_LIGHT, center=(W / 2, 222))
        draw_text(w, "SKRIV DINA INITIALER", 36, WHITE, center=(W / 2, 278))
        n = len(self.letters)
        for i in range(3):
            cx = W / 2 + (i - 1) * 124
            box = pygame.Rect(0, 0, 76, 88)
            box.center = (int(cx), 362)
            current = i == n and self.state_t >= 1.0
            pygame.draw.rect(w, (25, 15, 40), box, border_radius=8)
            pygame.draw.rect(w, QLIK_GREEN if current else (80, 70, 110), box, 4 if current else 2, border_radius=8)
            if i < n:
                draw_text(w, self.letters[i], 84, QLIK_LIGHT, center=box.center)
            elif current:
                if int(self.clock * 4) % 4:
                    draw_text(w, ALPHABET[self.cur], 84, WHITE, center=box.center)
                for side in (-1, 1):
                    ax = box.centerx + side * 52
                    pygame.draw.polygon(w, YELLOW, [(ax + side * 12, 362), (ax, 350), (ax, 374)])
        draw_text(w, "VÄNSTER / HÖGER: byt bokstav     MITTEN: välj", 26, GREY, center=(W / 2, 438))
        draw_text(w, "...eller skriv på tangentbordet", 26, GREY, center=(W / 2, 466))
        draw_text(w, "Tryck MITTEN två gånger snabbt för att hoppa över", 28, YELLOW, center=(W / 2, 512))

    def draw_over(self, w):
        draw_text(w, "TIDEN ÄR UTE!", 84, ORANGE, center=(W / 2, 130))
        draw_text(w, str(self.score), 120, WHITE, center=(W / 2, 235))
        draw_text(w, tr("POÄNG") + ("  -  " + self.name if self.name else ""), 30, GREY, center=(W / 2, 300))
        draw_text(w, tr("Rang:") + " " + tr(self.rank), 42, QLIK_LIGHT, center=(W / 2, 355))
        if self.new_best and int(self.clock * 3) % 2 == 0:
            draw_text(w, "NYTT REKORD!", 52, YELLOW, center=(W / 2, 410))
        draw_text(w, tr("Monster nedskjutna: %d     Gånger skrämd: %d") % (self.kills, self.hits), 28, WHITE,
                  center=(W / 2, 458))
        if self.boss_killed:
            done = tr("%s besegrade!" if len(self.boss_killed) > 1 else "%s besegrad!")
            draw_text(w, done % " + ".join(self.boss_killed), 28, ORANGE, center=(W / 2, 486))
        if self.state_t > 3.0 and int(self.clock * 2) % 2 == 0:
            draw_text(w, "TRYCK PÅ VALFRI KNAPP FÖR ATT SPELA IGEN", 32, YELLOW, center=(W / 2, 530))


# ----------------------------------------------------------------------- main
def main():
    windowed = "--window" in sys.argv
    wide = "--wide" in sys.argv
    if not windowed and sys.platform.startswith("linux"):
        # Pi 4 + kmsdrm: SDL's default renderer shows a black screen, GLES2 works
        os.environ.setdefault("SDL_RENDER_DRIVER", "opengles2")
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    if wide:
        aspect = 16 / 9
        if not windowed:
            try:
                dw, dh = pygame.display.get_desktop_sizes()[0]
                aspect = dw / dh
            except Exception:
                pass
        set_width(aspect)
    flags = pygame.SCALED | (0 if windowed else pygame.FULLSCREEN)
    screen = pygame.display.set_mode((W, H), flags)
    print("pygame %s, SDL %s, video driver %s, display %s" % (
        pygame.version.ver, ".".join(map(str, pygame.get_sdl_version())),
        pygame.display.get_driver(), pygame.display.get_desktop_sizes()), "logical %dx%d" % (W, H))
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
            if e.type == pygame.KEYDOWN:
                game.admin_key(e.key)
                game.inp.key_down(e)
        game.inp.poll()
        steps = FAST_FORWARD if pygame.key.get_pressed()[pygame.K_SPACE] else 1
        for i in range(steps):
            game.update(dt)
            game.inp.clear_edges()  # edges only count once per frame
        game.draw()
        pygame.display.flip()


if __name__ == "__main__":
    main()
