# local_server.py
# Serves the companion app from the Pi and streams device events to it.
#
#   GET  /                      built companion app (static/ folder)
#   GET  /api/state             current status, selected eye, recent records
#   GET  /api/records?limit=N   records, newest first
#   GET  /api/events            Server-Sent Events: "status" and "record" events
#   POST /api/eye  {"eye": ..}  app tells the device which eye is being treated
#
# Import `publish`, `set_status` and `run_in_thread` from main.py.
# No hardware dependencies, so this file also runs on a laptop for testing.
import json
import os
import queue
import threading

from flask import Flask, Response, abort, jsonify, request, send_from_directory

import store

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

app = Flask(__name__, static_folder=None)

_subscribers = []
_subscribers_lock = threading.Lock()
_state = {"status": "idle", "eye": "left"}
_state_lock = threading.Lock()

USER = {"name": "Julia"}
MEDICATION = {"name": "Azelastine 0.05%", "dosage": "3 drop each eye", "frequency": "twice a day", "target_drops": 3}


def publish(event, data):
    """Push one event to every connected app."""
    msg = f"event: {event}\ndata: {json.dumps(data)}\n\n"
    with _subscribers_lock:
        for q in list(_subscribers):
            try:
                q.put_nowait(msg)
            except queue.Full:
                pass


def set_status(status):
    """status: idle | dispensing | processing"""
    with _state_lock:
        _state["status"] = status
        snapshot = dict(_state)
    publish("status", snapshot)


def current_eye():
    with _state_lock:
        return _state["eye"]


def record_attempt(drop_count, angle, success):
    """Store a dispense result and notify the app. Called by main.py."""
    rec = store.add_record(drop_count, angle, success, eye=current_eye())
    publish("record", rec)
    return rec


@app.get("/api/state")
def api_state():
    with _state_lock:
        snapshot = dict(_state)
    return jsonify({
        "user": USER,
        "medication": MEDICATION,
        "status": snapshot["status"],
        "eye": snapshot["eye"],
        "records": store.list_records(limit=50),
    })


@app.get("/api/records")
def api_records():
    limit = request.args.get("limit", default=50, type=int)
    return jsonify(store.list_records(limit=max(1, min(limit, 500))))


@app.post("/api/eye")
def api_eye():
    body = request.get_json(silent=True) or {}
    eye = body.get("eye")
    if eye not in ("left", "right"):
        abort(400, "eye must be 'left' or 'right'")
    with _state_lock:
        _state["eye"] = eye
        snapshot = dict(_state)
    publish("status", snapshot)
    return jsonify(snapshot)


@app.get("/api/events")
def api_events():
    q = queue.Queue(maxsize=100)
    with _subscribers_lock:
        _subscribers.append(q)

    def stream():
        try:
            with _state_lock:
                snapshot = dict(_state)
            yield f"event: status\ndata: {json.dumps(snapshot)}\n\n"
            while True:
                try:
                    yield q.get(timeout=15)
                except queue.Empty:
                    yield ": keepalive\n\n"
        finally:
            with _subscribers_lock:
                if q in _subscribers:
                    _subscribers.remove(q)

    return Response(stream(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/")
@app.get("/<path:path>")
def static_app(path="index.html"):
    """Serve the exported Next.js app. `/administration` -> administration.html."""
    if not os.path.isdir(STATIC_DIR):
        return ("Companion app not built. Run `npm run build` in the frontend and copy `out/` to `static/`.", 503)
    full = os.path.join(STATIC_DIR, path)
    if os.path.isfile(full):
        return send_from_directory(STATIC_DIR, path)
    if os.path.isfile(full + ".html"):
        return send_from_directory(STATIC_DIR, path + ".html")
    if os.path.isfile(os.path.join(full, "index.html")):
        return send_from_directory(os.path.join(STATIC_DIR, path), "index.html")
    abort(404)


def run_in_thread(host="0.0.0.0", port=8000):
    t = threading.Thread(
        target=lambda: app.run(host=host, port=port, threaded=True, use_reloader=False, debug=False),
        daemon=True,
    )
    t.start()
    print(f"Companion app server listening on http://{host}:{port}")
    return t


if __name__ == "__main__":
    # Laptop test: python local_server.py, then open http://localhost:8000
    app.run(host="0.0.0.0", port=8000, threaded=True)
