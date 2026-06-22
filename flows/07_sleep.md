# Flow 07 — Sleep mode (business card + profile-specific sleep)

User said "息屏" / "sleep the card" / "show my business card". Push the
sleep-card frame. M5Paper V1.1 then enters firmware deep sleep. PaperS3
shows the sleep-card frame only; do not promise deep sleep or 0 W for
PaperS3.

## Step 1 — Verify the profile

Sleep-card content lives in `assets/profile.yaml`. Check it exists and
has at least a name + tagline:

```bash
cat assets/profile.yaml
```

If missing or default placeholders ("Your Name"), ask the user:

> "I'll show your business card on the device while it sleeps. Quick
> profile (one line each):
> - Name?
> - One-line tagline / what you do?
> - Job title + city + website?
>
> Optional: I can use an avatar PNG / a QR code PNG if you have them."

Then write `assets/profile.yaml` (see existing structure as the
template).

## Step 2 — Push sleep frame

```bash
curl -sf -X POST "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/sleep" \
  -H 'Content-Type: application/json' \
  -d '{}'
```

The daemon:
1. Renders the name-card from `assets/profile.yaml` (using
   `daemon/card_render_sleep.py`)
2. Pushes it as a normal frame
3. If the selected profile supports deep sleep, sends `cmd:sleep_now`

- **M5Paper V1.1:** enters deep sleep and keeps the e-ink frame visible.
  Battery loss is very low.
- **PaperS3:** returns `mode: sleep-card`, `deep_sleep: false`, and keeps the
  daemon/device in the normal always-on PaperS3 path. It does not send
  `cmd:sleep_now`.

## Step 3 — Waking back up

- **M5Paper V1.1 side touch / rotary press** wakes the device + brings up the
  splash, then waits for daemon.
- **M5Paper V1.1 auto-wake via BLE** (architecture C): daemon sends
  `cmd:wifi_wake_now` over BLE → device brings Wi-Fi up → daemon pushes fresh
  frames → device drops Wi-Fi after 30 s linger.
- **PaperS3:** tap a visible action chip while awake, push any widget, or
  restart/reconnect the daemon. If the device was power-cycled, push a fresh
  frame after it reports status.

Tell the user how to wake the device based on the architecture they
chose:

- USB-powered (architecture A): never sleeps deeply, always-on
- USB-only (architecture B): just unplug + plug — device boots
- Battery + BLE (architecture C): tap / rotary to wake, then run any
  /card command to push
- PaperS3: sleep-card only; keep using Wi-Fi/USB daemon commands.

## Quiet-hours auto-sleep (handled by the daemon)

If `~/.ai-desk-card/interests.yaml` has `quiet_hours.enabled: true`, the
**daemon** auto-fires this flow when wall-clock crosses
`quiet_hours.start`. No agent action required.

- Fires at most once per calendar day (so user touching the device after
  quiet_hours doesn't trigger another auto-sleep that day)
- Skips if `_device_alive()` is false (no point pushing a name card to
  an offline device)
- Re-reads the YAML on every check so edits take effect within ~45 s

If you want the device to wake fresh at `quiet_hours.end`, that part
still requires the agent — schedule a push in your loop (flow 06) at
the end time. For PaperS3 this is just a fresh push over the active
Wi-Fi/USB daemon path. For M5Paper V1.1 deep-sleep on battery, the daemon
doesn't auto-wake because that would consume current to keep BLE listening.
