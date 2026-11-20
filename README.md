# SmartDrop device software (Raspberry Pi)

Device firmware for the SmartDrop eye drop dispenser. On a button press it drives the
stepper motor until the camera sees a drop, records the dispense on video, analyses the
recording to count drops and estimate the drop trajectory angle, gives audio feedback,
stores the result locally, and pushes it to the companion app.

**No cloud services are used.** The Pi itself serves the companion app over the local
network and streams events to it (Server-Sent Events). Records live in a SQLite file on
the device.

---

## Repository structure

```
accessible-eyedrop-RaspPi/
├── main.py            # Entry point: button, motor, recording, analysis, feedback, app events
├── local_server.py    # Flask server: serves the companion app and the /api endpoints
├── store.py           # SQLite store for administration records (smartdrop.db)
├── raft_process.py    # Video analysis (frame differencing in a region of interest)
├── stepper_motor.py   # 28BYJ-48 / ULN2003 stepper control
├── buzzer.py          # Success / fail melodies
├── static/            # Built companion app (copied from the frontend's `out/` folder)
├── captured.mp4, outputcv.mp4   # A sample recording and its analysed output (overwritten on each dispense)
├── RAFT/              # Required: clone of the RAFT repository (git-ignored; imported by raft_process.py, see note)
└── raft-things.pth    # Required: RAFT weights (loaded on every dispense, see note)
```

**Note on RAFT.** `raft_process.py` imports and loads the RAFT optical-flow model, but the
drop detection actually used is frame differencing; the optical-flow function is never
called. The RAFT files are only needed because of that import, but without them `main.py`
does not start: run `git clone https://github.com/princeton-vl/RAFT.git` in this folder. `one_drop.py` and
`one_drop_greyScale.py` are earlier single-file prototypes and are not used by `main.py`.

---

## Dependencies

### System (Raspberry Pi 4B, Raspberry Pi OS Bullseye or later)

```bash
sudo apt-get update
sudo apt-get install -y python3-opencv ffmpeg python3-rpi.gpio python3-picamera2
```

### Python

```bash
python3 -m venv --system-site-packages venv
source venv/bin/activate
pip install flask numpy imageio "imageio[ffmpeg]" torch torchvision
```

`torch`/`torchvision` are only required because of the RAFT import (see note above).

---

## Hardware connections

- **Camera:** Raspberry Pi Camera v2 on the CSI port.
- **Button:** one terminal to **GPIO 4**, the other to ground (internal pull-up is used).
- **Buzzer:** GPIO 23.
- **Stepper (28BYJ-48 via ULN2003):** IN1→GPIO 17, IN2→GPIO 18, IN3→GPIO 27, IN4→GPIO 22,
  VCC→5V, GND→GND. 2038 steps ≈ one revolution ≈ 2 mm of plunger travel.

---

## Running

1. Build the companion app and copy it onto the device (see the frontend README), so that
   `static/index.html` exists next to `main.py`.
2. Start the firmware from a desktop session (`main.py` always opens two OpenCV preview
   windows, so it needs a display):

   ```bash
   source venv/bin/activate
   python3 main.py
   ```

3. On a phone on the same network (or the Pi's own hotspot), open
   `http://<pi-address>:8000`. With mDNS enabled, `http://raspberrypi.local:8000` works.

Without the `static/` folder the API still works; `/` returns a short message instead.

### Laptop testing without hardware

`local_server.py` and `store.py` have no hardware dependencies:

```bash
python3 local_server.py      # serves static/ and the API on http://localhost:8000
```

Call `local_server.record_attempt(drop_count, angle, success)` from the same process to
emit a fake dispense event.

---

## What happens on a button press

1. `status: dispensing` is pushed to the app. Video recording starts and the stepper
   advances in 100-step increments until the live detector sees a drop in the region of
   interest, then retracts the same number of steps.
2. `status: processing` is pushed. The recording is analysed (`process_video`), giving a
   drop count and the angle of the drop trajectory.
3. The result is written to `smartdrop.db` and pushed to the app as a `record` event with
   the eye the app currently has selected. `status: idle` follows.
4. The buzzer plays the success melody if at least one drop was counted, otherwise the
   fail melody.

---

## HTTP API

| Method | Path | Description |
|---|---|---|
| GET | `/` | The companion app |
| GET | `/api/state` | `{user, medication, status, eye, records}` |
| GET | `/api/records?limit=N` | Records, newest first (default 50, max 500) |
| GET | `/api/events` | SSE stream. Events: `status` `{status, eye}` and `record` `{id, timestamp, eye, drop_count, angle, success}` |
| POST | `/api/eye` | Body `{"eye": "left" \| "right"}`; sets the eye attached to the next records |

`timestamp` is Unix seconds. `angle` is degrees or `null` when no drop was detected.
`user` and `medication` are constants in `local_server.py`.

---

## Troubleshooting

- **Camera errors** (e.g. "Camera init sequence did not complete"): make sure no other
  program is using the camera.
- **Motor keeps running:** the motor loop only stops when the live detector reports a
  drop. Check the camera view and the region of interest in `image_processing_thread`.
- **Phone can't open the app:** confirm phone and Pi are on the same network and that
  port 8000 is reachable (`curl http://<pi-address>:8000/api/state`).
