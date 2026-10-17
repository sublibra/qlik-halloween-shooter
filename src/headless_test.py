#!/usr/bin/env python3
"""
Headless smoke test: plays a full round with a simple bot, no window or audio.

  uv run src/headless_test.py            # one round, screenshots in shots/
  uv run src/headless_test.py --rounds 3 --seed 1
  uv run src/headless_test.py --wide     # 16:9 widescreen

Steps the Game at dt=1/60, saves screenshots at fixed moments, writes high
scores to a temp file (never the real highscores.json), and reports frame time.
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


class FakeInput:
    def __init__(self):
        self.left = self.right = self.fire = False
        self.any = self.any_pressed = False

    def set(self, left=False, right=False, fire=False):
        prev = self.any
        self.left, self.right, self.fire = left, right, fire
        self.any = left or right or fire
        self.any_pressed = self.any and not prev


def bot(game, inp):
    """Chase the lowest active enemy, always fire."""
    p = game.player
    targets = [e for e in game.enemies if e.active() and e.y < p.y - 40]
    left = right = False
    if targets:
        t = max(targets, key=lambda e: e.y)
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
    args = ap.parse_args()
    if args.seed is not None:
        random.seed(args.seed)

    if args.wide:
        q.set_width(16 / 9)
    q.SCORE_FILE = os.path.join(tempfile.mkdtemp(), "highscores.json")
    pygame.mixer.pre_init(22050, -16, 1, 512)
    pygame.init()
    screen = pygame.display.set_mode((q.W, q.H))
    inp = FakeInput()
    game = q.Game(screen, q.Sfx(), inp)
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
        snaps = {int(s * 60) for s in (10, 30, 50, 70, 85)}
        frame = 0
        while game.state == "playing":
            bot(game, inp)
            frame_times.append(step())
            frame += 1
            if rnd == 1 and frame in snaps:
                shot("play_%02ds" % (frame // 60))
        for _ in range(60):
            inp.set()
            step()
        if rnd == 1:
            shot("game_over")
        print("round %d: score %d  rank %-26s kills %d  hits %d"
              % (rnd, game.score, game.rank, game.kills, game.hits))
        # wait out the 3 s restart lock
        for _ in range(int(3.2 * 60)):
            inp.set()
            step()

    frame_times.sort()
    n = len(frame_times)
    print("frames %d  avg %.2f ms  p95 %.2f ms  max %.2f ms  (budget 16.7 ms)"
          % (n, 1000 * sum(frame_times) / n, 1000 * frame_times[int(n * 0.95)], 1000 * frame_times[-1]))
    if not args.no_shots:
        print("screenshots in", args.shots)
    pygame.quit()


if __name__ == "__main__":
    main()
