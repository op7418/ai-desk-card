# Flow 07 — Sleep mode (business card + deep-sleep)

User said "息屏" / "sleep the card" / "show my business card". Push the
sleep-card frame and tell the device to enter deep-sleep so it draws 0 W
while keeping the last frame visible.

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

## Step 2 — Push sleep frame + deep-sleep

```bash
curl -sf -X POST "${CARD_DAEMON_URL:-http://127.0.0.1:9877}/sleep" \
  -H 'Content-Type: application/json' \
  -d '{}'
```

The daemon:
1. Renders the name-card from `assets/profile.yaml` (using
   `daemon/card_render_sleep.py`)
2. Pushes it as a normal frame
3. Sends `cmd:sleep_now` so the firmware enters `deep_sleep()`

The device's e-ink retains the last frame at 0 W indefinitely. Battery
loss is essentially zero (1–2% per month from RTC + BLE standby).

## Step 3 — Waking back up

- **Side touch / rotary press** wakes the device + brings up the
  splash, then waits for daemon
- **Auto-wake via BLE** (architecture C): daemon sends
  `cmd:wifi_wake_now` over BLE → device brings Wi-Fi up → daemon pushes
  fresh frames → device drops Wi-Fi after 30 s linger

Tell the user how to wake the device based on the architecture they
chose:

- USB-powered (architecture A): never sleeps deeply, always-on
- USB-only (architecture B): just unplug + plug — device boots
- Battery + BLE (architecture C): tap / rotary to wake, then run any
  /card command to push

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
the end time. The daemon doesn't auto-wake because deep-sleep on
battery would consume current to keep BLE listening.
