# Roadmap

## Done (v0.1)
- Microphone level + voice filter, guided calibration, 2-4 alert levels, blinking, per-monitor border,
  night mode, optional sound, ES/EN interface, tray icon, installer, CI build.

## Next: game themes (Phase 3)
- **Themes**: a theme = frame artwork + colours + animation (for example a sci-fi cockpit HUD frame for space games).
  Original artwork only; no logos or assets copied from games.
- **Per-game profiles**: detect the active game (foreground process name) and switch theme and sensitivity automatically.
- **Import**: drop your own PNG frames in a folder and pick them from the list (the *custom image* style already
  accepts a PNG file).
- Keep the idle cost at zero: themes are rendered once per alert, like today.

## Ideas
- Per-monitor border settings.
- Short "calm down" hint text in the corner of the screen.
- Statistics: how often and how loud, per day.
- Code signing of the installer, to avoid SmartScreen warnings.
