# Qlik or Treat — project brief

A spooky, silly, Qlik-themed 3-button arcade shooter for the Qlik company Halloween party.
Runs on a Raspberry Pi 4 Model B in a home-built wooden cabinet. **Deadline: 2026-10-20** (3 days from 2026-10-17).
Day 1 prototype and day 2 content are done (`src/qlik_or_treat.py`, ~1900 lines, single file, branch `day2-content`). Keep it a single file unless it really hurts.

## Dev commands
- Install deps (laptop): `uv sync` (Python 3.11 pinned, matching the Pi's Bookworm python3)
- Play on laptop: `uv run src/qlik_or_treat.py --window`
- Headless test (run after every change): `uv run src/headless_test.py [--rounds N] [--seed S] [--no-shots] [--wide]`
  - bot plays full rounds at dt=1/60, saves screenshots to `shots/` (gitignored), prints score/rank and frame time
  - uses a temp high-score file, never touches `highscores.json`
  - look at the screenshots after visual changes

## Audience and tone
- Players from age 5 to adults, at a party, often with a crowd watching.
- Fun and laughs over balance. Not meant to be taken seriously.
- Dark and spooky, but cartoonish, not scary-scary.
- **On-screen text is Swedish** (monster names stay English parodies). Excel errors use Swedish Excel names (#REFERENS!, LETARAD...).
- Parody, never real logos. Competitor jokes stay gentle (it may end up on LinkedIn).

## Hardware
- Raspberry Pi 4 Model B, Raspberry Pi OS (Lite is fine), HDMI screen, speaker on 3.5 mm jack or HDMI audio.
- Three arcade buttons on GPIO with internal pull-ups, other leg to GND (COM + NO on microswitches):
  - LEFT = GPIO17 (pin 11), FIRE = GPIO27 (pin 13), RIGHT = GPIO22 (pin 15)
  - Overridable via env vars `PIN_LEFT`, `PIN_FIRE`, `PIN_RIGHT`.
- The HAT currently on the Pi must come off (it covers the header).
- Autostart via systemd (`qlik-or-treat.service`, `SDL_VIDEODRIVER=kmsdrm`).

## Tech
- Python 3 + Pygame (Pi: `python3-pygame` from apt, pygame 2.1.x — avoid APIs newer than that; laptop has 2.6, so be careful). `gpiozero` for buttons, optional.
- Logical resolution 800×600, `pygame.SCALED | FULLSCREEN` on the Pi; `--window` flag for laptop dev.
- `--wide` flag: logical width grows to the screen's aspect (window: 16:9 → 1066×600, max 1100), H stays 600. Spawn rate, train amplitude, stars/fog scale with `wide_factor()`; always use `W`, never hardcode 800. Headless: `--wide`.
- Keyboard fallback: arrows/A/D move, UP/W/ENTER fire (hold = auto-fire), hold SPACE = 8× fast-forward (testing), ESC quit.
- Admin keys (`Game.admin_key`, ignored while typing initials): L = Swedish/English, N = new game, M = expert mode (`EXPERT_SPEED` scales dt during rounds), R = rename the last saved high score. Lang + mode persist in `settings.json`.
- Translation: write on-screen text in Swedish; `render()` passes everything through `tr()`, which looks up `EN`. Add every new string to `EN`. Composite strings: translate the template/parts before formatting.
- Input: `Controls` holds held state + press edges (`*_pressed`) + typed letters; `Input(Controls)` adds keyboard/GPIO polling. Headless test uses `Controls` directly.
- No asset files: all graphics drawn procedurally, all sounds synthesised at startup with `array` (no numpy).
- Background loop on mixer channel 0: ambient drone on title/game over, 12.8 s A-minor music loop during rounds (`Sfx.music_loop`). Channel 1: Pipeline beam hum.
- Must hold 60 fps on the Pi 4. Laptop: ~0.7 ms avg/frame in the headless test (Pi is maybe 5–10× slower).
- High scores in `highscores.json` next to the script (`src/` on the laptop, the install dir on the Pi). Format: list of `{"score", "name"}` (old plain-int lists still load).

## Game design (current)
- Vertical shooter. Ship = green Qlik "Q" (ring + tail), moves left/right at the bottom, fires up.
- 90-second rounds. **You never die**: a hit costs 100 points, 1.6 s invulnerability, silly quip ("Ouch! Manual refresh!").
- Enemies escaping off the bottom: no penalty.
- Difficulty ramps: spawn interval 1.2 s → 0.4 s; new monster types unlock over time.
- "NEW SPOOK DETECTED" banner + tagline the first time each monster appears.
- Last 10 s: red pulsing timer + ticks.
- States: title/attract (title "QLIK OR TREAT", dripping slime, top 10 scores with initials in two columns, monsters drifting) → playing → initials (only if the score makes the top 10) → game over (score, rank, "NEW HIGH SCORE!", stats). Any button restarts after 3 s; back to title after 12 s.
- Initials: 3 slots; LEFT/RIGHT cycle A–Ö (hold repeats), FIRE confirms a letter, FIRE twice within 0.35 s skips (saved as "---"); a keyboard can type letters (Backspace undoes). Input ignored for the first 1 s (button mashing), auto-saves after 25 s idle.
- Mid-boss: Inferno-matica at 46 s (`MID_BOSS_TIME`), 14 HP, fireball fans (shootable, +25) after a "Laddar... 99%" bar (`draw_loading`). Kill = +1000. Times out and flies off after 14 s (`MID_BOSS_STAY`, no points).
- Final boss: Mega Power BOO-I at 75 s (`BOSS_TIME`), 34 HP. "Uppdaterar datamängd..." bar, then either a fan of falling bar charts (`Fireball(style="bar")`, shootable) or yellow licence `ErrorBlob`s ("LICENS KRÄVS", "DAX?!"). Every 5 s publishes 2 labelled `PowerBooI` copies ("Rapport_FINAL_v2", "Kopia av Kopia (3)") that zig-zag in lockstep - great Associative Blast targets. Crown loses a bar per 20 % HP. At half HP: "UPPGRADERAR TILL PREMIUM-KAPACITET!", faster sweep/charge, 3 copies. Kill = +3000.
- Only one boss at a time (`Game.boss`); spawns halve and Table-Ghoul/Sick-Sense stop while one lives. `boss_killed` is a list of beaten boss titles.
- Power-ups (`PowerUp`, 7 % drop per kill, 35 % from Table-Ghoul, 5 s cooldown, max 2 on screen): Pipeline beam (5 s, replaces bullets while FIRE is held), Insight Shield (absorbs one hit). From 60 s (`LATE_POWERUPS`): Qlik Engine Associative Blast (8 s: hit ghost = green, same type (min 3, padded with nearest) = white, chain-pop; rest = grey, slowed) and Qlik Answers Bot (10 s helper drone, chatty speech bubbles). `SCHEDULED_DROPS` guarantees one Associative Blast at 62 s and one Answers Bot at 76.5 s.
- Ranks: Spreadsheet Survivor (0), Dashboard Defender (2500), Insight Hunter (6000), Data Ghostbuster (10000), Chief Ghostbusting Officer (15000). Tune after real playtests.
- Look: dark purple gradient, scrolling stars, fog, moon, vignette, graveyard of tombstones (RIP, EXCEL 97, VLOOKUP, CSV, MACROS). Confetti explosions in Qlik colours, screen shake, floating "+points" and kill quips.

## Monster roster
Implemented:
| Name | Parody of | Behaviour | HP | Points |
|---|---|---|---|---|
| Spooker | Looker | Pale ghost, drifts down with wobble, speeds up over the round | 1 | 100 |
| Airbite | Airbyte | Vampire bat, hovers then dive-bombs at the player (screech) | 1 | 150 |
| SlopSpot | ThoughtSpot | Pink search-slime, hops; splits big → 2 medium → 2 small each (from 12 s) | 1 | 150/100/75 |
| Power BOO-I | Power BI | Yellow ghost with bar-chart crown, wide zig-zag | 1 | 150 |
| Table-Ghoul | Tableau | Blue zombie table, slow tank, spits `#REF!` `#N/A` `#DIV/0!` `#VALUE!` | 4 | 400 |
| Boomoo | Domo | Pumpkin-cow. Shot: blast kills neighbours (4 dmg to boss). Gets low: moos, swells, self-detonates and can hit the player (from 42 s) | 1 | 200 |
| Sick-Sense | Sisense | Eyeball ghost, teleports (invulnerable mid-jump, shimmer telegraphs target), squints "A... a..." then sneezes slime (from 52 s) | 2 | 250 |
| Fivetrain | Fivetran | 5-car ghost train snaking down (at 35 s and 65 s); +500 bonus "TRAIN WRECK!" for all 5 | 2 head / 1 cars | 250 / 120 |
| Inferno-matica | Informatica | **Mid-boss** at 46 s, see above | 14 | 1000 |
| Mega Power BOO-I | Power BI | **Final boss** at 75 s, see above | 34 | 3000 |

Planned / alternatives:
| Name | Parody of | Idea |
|---|---|---|
| Informummy-ca | Informatica | Alt mid-boss: mummy wrapped in XML |
| The Legacy Data Warehouse | — | Alt boss: haunted mainframe spitting zombies |

Also BI-problem monsters if needed: Spreadsheet Zombie, Siloed Data Ghost (flickers in/out), Stale Dashboard Mummy ("Last refreshed: 2019"), Dirty Data Slime, Manual Refresh Bat, Pivot Table Spider.

## Remaining work
**Day 2 — content** (done on `day2-content`; needs a real playtest)
- Rank thresholds not retuned yet: the headless bot now scores ~25–33k (was ~20k) with boss + power-ups.
- Optional: between-round taglines, tweak glow strength (currently subtle).

**Day 3 — hardware and polish**
1. Fresh SD card, install, systemd autostart, verify GPIO + sound on the real cabinet.
2. Playtest with a 5-year-old and an adult; tune speeds, hit radius, rank thresholds, volume.
3. Hidden admin: e.g. hold LEFT+RIGHT 5 s on title to reset high scores.
4. Make sure it recovers from anything (service `Restart=always`, no crash on missing audio/GPIO).

## Files
- `src/qlik_or_treat.py` — the game
- `src/headless_test.py` — headless bot test + screenshots + frame timing
- `README.md` — wiring table, laptop/Pi run, autostart
- `qlik-or-treat.service` — systemd unit (replace `pi` with the actual username)
- `pyproject.toml` / `uv.lock` — laptop dev env only; the Pi uses apt packages
