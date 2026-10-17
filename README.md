# Qlik or Treat 👻

A spooky, silly, Qlik-themed 3-button arcade shooter for Raspberry Pi 4.
90-second rounds, you never die (getting hit costs 100 points), high scores saved to `highscores.json`.

## Wiring (Pi 4, 40-pin header)

Each button: one leg to the GPIO pin, the other leg to any GND. For 3-tab microswitches use **COM** and **NO**.
No resistors needed (internal pull-ups).

| Button | GPIO   | Physical pin |
|--------|--------|--------------|
| LEFT   | GPIO17 | 11           |
| FIRE   | GPIO27 | 13           |
| RIGHT  | GPIO22 | 15           |
| GND    | —      | 9, 14, 20 …  |

Different pins? Change `PIN_LEFT/PIN_FIRE/PIN_RIGHT` at the top of the script, or set env vars of the same name.
Remember to take the HAT off the Pi, it covers the header.

## Run on your laptop

```
uv sync
uv run src/qlik_or_treat.py --window
```
(or `pip install pygame` and `python3 src/qlik_or_treat.py --window`)
Add `--wide` for widescreen (16:9 in a window; fullscreen matches the screen's aspect ratio).
Arrows (or A/D) to move, UP/W/ENTER to fire (hold = auto-fire), hold SPACE to fast-forward (testing), ESC to quit.

Admin keys (plug a keyboard into the cabinet): **L** Swedish/English, **N** new game (throws away a round in progress), **M** basic/expert mode (the whole round runs 1.3× faster), **R** rename the most recent high score (for when someone enters something rude). Language and mode are saved in `settings.json` next to the script.

Headless smoke test (bot plays a round, screenshots in `shots/`, frame timing):
`uv run src/headless_test.py`

## Run on the Pi

1. Flash Raspberry Pi OS (Lite is fine) with Raspberry Pi Imager, enable SSH.
2. Install:
   ```
   sudo apt update
   sudo apt install -y python3-pygame python3-gpiozero
   ```
3. Copy the game:
   ```
   mkdir -p ~/qlik-or-treat
   scp src/qlik_or_treat.py qlik-or-treat.service <user>@<pi>:~/qlik-or-treat/
   ```
4. Test once from the console (not over SSH-only, it needs the screen):
   `python3 ~/qlik-or-treat/qlik_or_treat.py` — should print `GPIO buttons enabled`.

### Autostart on boot

Edit `qlik-or-treat.service` and replace `pi` with your username (in `User=` and the paths), then:
```
sudo cp ~/qlik-or-treat/qlik-or-treat.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now qlik-or-treat
```
Logs: `journalctl -u qlik-or-treat -f`. Stop it for maintenance: `sudo systemctl stop qlik-or-treat`.

If there's no sound, add `Environment=SDL_AUDIODRIVER=alsa` to the service.
If sound goes to HDMI instead of the jack (or vice versa), pick the output with `sudo raspi-config` → System Options → Audio.

## What's in the game

- Monsters: Spooker, Airbite (dive-bombing bat), Power BOO-I (zig-zag), SlopSpot (slime that splits when shot),
  Table-Ghoul (tank, spits `#REF!` errors), Boomoo (exploding pumpkin-cow, chain-blasts its neighbours),
  Sick-Sense (teleporting eyeball that sneezes slime), Fivetrain (5-car ghost train, +500 for wrecking all cars)
- Mid-boss at 46 s: Inferno-matica, with a very slow "Laddar..." bar before each fireball volley (leaves after 14 s if not beaten)
- Boss for the last 15 s: Mega Power BOO-I, rains bar charts and licence errors, publishes copies of itself, upgrades to Premium at half HP
- Power-ups dropped by kills: Pipeline beam (5 s laser), Insight Shield (absorbs one hit), and from 60 s on
  Qlik Engine Associative Blast (8 s: shot ghost turns green, associated ones chain-pop, the rest go grey)
  and Qlik Answers Bot (helper drone that shoots for 10 s). One of each of the last two always drops (62 s, 76.5 s).
- "NEW SPOOK DETECTED" banner the first time each monster shows up
- High-score initials: LEFT/RIGHT pick a letter, FIRE confirms, or type on a keyboard; FIRE twice quickly skips
- Title/attract screen with top 10 scores, game-over screen with funny ranks
- All sounds synthesised in code, spooky drone loop
