#!/usr/bin/env python3
"""
Headless smoke test: plays a full round with a simple bot, no window or audio.

  uv run src/headless_test.py            # one round, screenshots in shots/
  uv run src/headless_test.py --rounds 3 --seed 1
  uv run src/headless_test.py --wide     # 16:9 widescreen
  uv run src/headless_test.py --english --expert

Steps the Game at dt=1/60, saves screenshots at fixed moments, writes high
scores and settings to a temp dir (never the real highscores.json / settings.json),
exercises the admin keys, and reports frame time.
"""
import argparse
import os
import random
import sys
import tempfile
import time

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

SRC = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(SRC)
sys.path.insert(0, SRC)

import pygame  # noqa: E402

import qlik_or_treat as q  # noqa: E402

DT = 1 / 60


def bot(game, inp):
    """Grab falling power-ups, then deal with low enemies, then the boss, then the lowest enemy.
    Always fires."""
    p = game.player
    targets = [e for e in game.enemies if e.active() and e.y < p.y - 40]
    pickups = [pu for pu in game.powerups if pu.y > 250]
    left = right = False
    t = None
    threats = [e for e in targets if e.y > 300]
    boss = game.boss if game.boss and not game.boss.dead and game.boss.active() else None
    if pickups:
        t = max(pickups, key=lambda pu: pu.y)
    elif boss and not threats:
        t = boss
    elif targets:
        t = max(targets, key=lambda e: e.y)
    if t:
        if t.x < p.x - 8:
            left = True
        elif t.x > p.x + 8:
            right = True
    inp.set(left, right, True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=1)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--shots", default=os.path.join(ROOT, "shots"))
    ap.add_argument("--no-shots", action="store_true")
    ap.add_argument("--wide", action="store_true", help="16:9 widescreen")
    ap.add_argument("--english", action="store_true", help="English text (admin key L)")
    ap.add_argument("--expert", action="store_true", help="expert mode (admin key M)")
    args = ap.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    if args.wide:
        q.set_width(16 / 9)
    tmp = tempfile.mkdtemp()
    q.SCORE_FILE = os.path.join(tmp, "highscores.json")
    q.SETTINGS_FILE = os.path.join(tmp, "settings.json")
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    screen = pygame.display.set_mode((q.W, q.H))
    inp = q.Controls()
    game = q.Game(screen, q.Sfx(), inp)
    if args.english:
        game.admin_key(pygame.K_l)
    if args.expert:
        game.admin_key(pygame.K_m)
    assert q.LANG == ("en" if args.english else "sv") and game.expert == args.expert
    assert q.load_settings() == ({"lang": q.LANG, "expert": game.expert} if args.english or args.expert else {})
    if not args.no_shots:
        os.makedirs(args.shots, exist_ok=True)

    def shot(name):
        if not args.no_shots:
            pygame.image.save(screen, os.path.join(args.shots, name + ".png"))

    def step():
        t0 = time.perf_counter()
        game.update(DT)
        game.draw()
        return time.perf_counter() - t0

    # title screen for a second, then press fire
    for _ in range(60):
        inp.set()
        step()
    shot("title")

    frame_times = []
    for rnd in range(1, args.rounds + 1):
        while game.state != "playing":
            inp.set(fire=True)
            step()
            inp.set()
            step()
        snaps = {int(s * 60) for s in (10, 30, 48, 55, 63, 70, 78, 84)}
        frame = 0
        while game.state == "playing":
            bot(game, inp)
            frame_times.append(step())
            frame += 1
            if rnd == 1 and frame in snaps:
                shot("play_%02ds" % (frame // 60))
        for _ in range(70):
            inp.set()
            step()
        if game.state == "initials":
            if rnd == 1:
                shot("initials")
                for ch in "BO\bOO":  # type on the keyboard, with a backspace
                    inp.typed.append(ch)
                    for _ in range(5):
                        step()
            else:
                inp.set(fire=True); step(); inp.set(); step()  # double tap FIRE = skip
                inp.set(fire=True); step(); inp.set(); step()
            assert game.state == "over", game.state
        for _ in range(60):
            inp.set()
            step()
        if rnd == 1:
            shot("game_over")
        print("round %d: score %d  rank %-26s kills %d  hits %d  bosses: %s  name %r"
              % (rnd, game.score, game.rank, game.kills, game.hits,
                 ", ".join(game.boss_killed) or "none killed", game.name))
        # wait out the 3 s restart lock
        for _ in range(int(3.2 * 60)):
            inp.set()
            step()

    print("top 10:", game.scores)

    # admin: rename the last high score, then N starts a round and N again restarts it
    last = game.last_entry
    if last:
        game.admin_key(pygame.K_r)
        assert game.state == "initials" and game.renaming is last
        for _ in range(70):
            inp.set()
            step()
        shot("rename")
        inp.typed.extend("ZZZ")
        step()
        assert game.state == "title" and (last[0], "ZZZ") in game.scores, game.scores
        assert q.load_scores() == game.scores
        print("renamed", last, "->", game.last_entry)
    game.admin_key(pygame.K_n)
    assert game.state == "playing"
    for _ in range(120):
        bot(game, inp)
        step()
    game.admin_key(pygame.K_n)
    assert game.state == "playing" and game.elapsed == 0
    game.set_state("title")
    for _ in range(int(13 * 60)):  # back to the title screen with initials
        inp.set()
        step()
    shot("title_scores")
    frame_times.sort()
    n = len(frame_times)
    print("frames %d  avg %.2f ms  p95 %.2f ms  max %.2f ms  (budget 16.7 ms)"
          % (n, 1000 * sum(frame_times) / n, 1000 * frame_times[int(n * 0.95)], 1000 * frame_times[-1]))
    if not args.no_shots:
        print("screenshots in", args.shots)
    pygame.quit()


if __name__ == "__main__":
    main()
