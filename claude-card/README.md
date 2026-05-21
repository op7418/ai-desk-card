# claude-card

A glanceable e-ink副屏 for Claude Code. The M5Paper sits next to your
monitor and shows weather, todos, today's calendar, message previews, and
the running AI's status. Data is pushed by Claude (via a Skill); the device
just renders.

This is a v0.5 successor track to [`../src/`](../src/) (the original buddy
firmware). The two live side-by-side in this repo; flash whichever
personality you want.

```
You ──ask──▶ Claude ──push──▶ Skill ──HTTP──▶ daemon ──serial──▶ M5Paper
                                                                    │
                                                                    └──▶ 6 widgets across a 4-slot grid
```

## Quick start

```bash
# from claude-card/
pio run -e card -t uploadfs    # one-time: flash CJK font
pio run -e card -t upload      # flash firmware
python3 daemon/card_daemon.py --transport serial

# in another shell:
skill/scripts/push_widget.py weather --slot top-left --data-stdin <<EOF
{"location":"上海","current":{"temp_c":22,"condition":"多云"}}
EOF
```

Or install the Skill+plugin into Claude Code and let an AI session push
widgets naturally:

```
/card-install
```

See [PLAN.md](PLAN.md) for the full v0.5 architecture decisions, scope
boundaries, and what's deferred to v0.6.

## Layout

```
claude-card/
├── PLAN.md           ← architecture decisions + scope rules
├── platformio.ini    ← env:card (independent from parent's env:m5paper)
├── src/              ← firmware (vendored EPDGUI + 6 widget components)
├── daemon/           ← Python HTTP/serial bridge
├── skill/            ← Claude Code Skill + plugin (commands, schemas)
└── data/cjk.ttf -> ../../data/cjk.ttf
```

## License + attribution

- This sub-project: GPL-3.0 with attribution (same as parent repo)
- Vendored EPDGUI framework: MIT, © 2020 m5stack — see [NOTICE.md](../NOTICE.md)
