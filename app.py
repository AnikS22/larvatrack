"""Upload a clip, pick the dish, get how far the larva walked - and watch it.

One larva at a time.  The tracker finds the animal itself, so there is nothing to
box; what it needs from you is which dish to look in and how wide that dish is,
because everything downstream is measured in millimetres.

    .venv-track/bin/python app.py        # then open http://localhost:8020

Must run under .venv-track - the measurement needs trackpy, which the main
environment does not have.
"""
import html
import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np

import larvatrack as lt
import tptrack

HERE = os.path.dirname(os.path.abspath(__file__))
UPLOADS = os.path.join(HERE, "uploads")
REPLAYS = os.path.join(HERE, "replays")
PORT = 8020
# The page may be served from Vercel while the work happens here, so the browser
# calls this server cross-origin. Nothing here is private to a user and there is
# no session to steal, so any origin may call it.
# Allow-Headers has to name every custom header the page sends, or the browser
# blocks the request at the preflight and the page reports the machine as
# offline having never reached it. Listing them by hand went stale the moment a
# header was added, so the preflight echoes back whatever was asked for.
CORS = {"Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Max-Age": "86400"}
MAX_UPLOAD = 2 * 1024 ** 3          # 2GB; a 8min 4K clip is well under this
JOBS = {}
JOBS_LOCK = threading.Lock()
EXPECTED = {}                       # upload id -> byte count the client promised
# ponytail: one worker. The measurement is CPU-bound on every core already, so a
# second job in parallel finishes both later than running them in turn.
QUEUE = []
QUEUE_CV = threading.Condition()


def safe_id(name):
    """An upload id that cannot climb out of the uploads directory."""
    stem = re.sub(r"[^A-Za-z0-9_.-]", "_", os.path.basename(name))[-60:]
    return "%s_%s" % (time.strftime("%H%M%S"), stem or "clip")


def first_frame(path, t=0.0):
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        raise ValueError("cannot open that video")
    cap.set(cv2.CAP_PROP_POS_MSEC, max(0.0, t) * 1000.0)
    ok, f = cap.read()
    if not ok:                      # a seek past the end lands here
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, f = cap.read()
    dur = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / max(cap.get(cv2.CAP_PROP_FPS) or 30.0, 1e-6)
    cap.release()
    if not ok:
        raise ValueError("cannot read a frame from that video")
    return f, dur


def dishes_in(frame):
    """Circles the auto-detector can see, biggest first, so one can be clicked."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    try:
        found = lt.find_plates(gray)
    except Exception:
        found = []
    h, w = gray.shape[:2]
    out = []
    for c in found or []:
        cx, cy, r = float(c[0]), float(c[1]), float(c[2])
        # The detector also fires on dish edges clipped by the frame border. A
        # dish we can only see a sliver of cannot be measured, so drop any whose
        # centre sits outside the frame or whose disc is mostly off it.
        if not (0 <= cx <= w and 0 <= cy <= h):
            continue
        inset = min(cx, w - cx, cy, h - cy)
        if inset < 0.35 * r:
            continue
        out.append({"cx": round(cx, 1), "cy": round(cy, 1), "r": round(r, 1)})
    out.sort(key=lambda d: -d["r"])
    return out


def run_job(job_id):
    job = JOBS[job_id]
    lines = []

    def log(*a):
        lines.append(" ".join(str(x) for x in a))
        job["log"] = lines[-40:]

    try:
        job["state"] = "running"
        circle = (job["cx"], job["cy"], job["r"])
        out = os.path.join(REPLAYS, job_id + ".mp4")
        # Detect and link once, then measure and replay off the same result -
        # doing it twice doubled the wait and proved nothing.
        mpp = job["dish_mm"] / (2.0 * circle[2])
        trs = tptrack.trajectories(job["path"], circle, mm_per_px=mpp, log=log,
                                   steady=job["steady"])
        total, seen, bridged = tptrack.measure(
            job["path"], job["dish_mm"], circle, log=log, steady=job["steady"], trs=trs)
        tptrack.replay(job["path"], job["dish_mm"], circle, out, larvae=1,
                       steady=job["steady"], log=log, trs=trs)
        job.update(state="done", mm=round(total, 1), seen=round(seen, 1),
                   bridged=round(bridged, 1), replay="/replay?id=" + job_id)
    except Exception as e:
        job["state"] = "error"
        job["error"] = "%s: %s" % (type(e).__name__, e)
        log(traceback.format_exc()[-800:])


def worker():
    while True:
        with QUEUE_CV:
            while not QUEUE:
                QUEUE_CV.wait()
            job_id = QUEUE.pop(0)
        run_job(job_id)


def enqueue(job_id):
    with QUEUE_CV:
        QUEUE.append(job_id)
        JOBS[job_id]["ahead"] = len(QUEUE) - 1
        QUEUE_CV.notify()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *a):      # quieter than the default access log
        sys.stderr.write("  %s\n" % (fmt % a))

    def send(self, code, body, ctype="application/json", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode()
        elif isinstance(body, str):
            body = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in dict(CORS, **(extra or {})).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def fail(self, code, msg):
        self.send(code, {"error": msg})

    def do_OPTIONS(self):
        # Safari does not accept "*" here, so echo the exact list requested.
        asked = self.headers.get("Access-Control-Request-Headers")
        self.send(204, b"", "text/plain",
                  {"Access-Control-Allow-Headers": asked} if asked else None)

    # ---- GET ----------------------------------------------------------
    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        one = lambda k, d=None: (q.get(k) or [d])[0]

        if u.path in ("/", "/index.html"):
            return self.send(200, open(os.path.join(HERE, "app.html"), "rb").read(),
                             "text/html; charset=utf-8")
        if u.path == "/frame":
            job = self._upload(one("id"))
            if job is None:
                return self.fail(404, "unknown upload")
            try:
                f, _ = first_frame(job, float(one("t", "0") or 0))
            except ValueError as e:
                return self.fail(400, str(e))
            ok, buf = cv2.imencode(".jpg", f, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return self.send(200, buf.tobytes(), "image/jpeg")
        if u.path == "/health":
            with QUEUE_CV:
                waiting = len(QUEUE)
            busy = sum(1 for j in JOBS.values() if j["state"] == "running")
            return self.send(200, {"ok": True, "queued": waiting, "running": busy})
        if u.path == "/job":
            job = JOBS.get(one("id"))
            if job is None:
                return self.fail(404, "unknown job")
            out = {k: v for k, v in job.items() if k != "path"}
            if job["state"] == "queued":
                # Live position, not the one captured at submission - the people
                # ahead finish while this one waits.
                with QUEUE_CV:
                    out["ahead"] = QUEUE.index(one("id")) if one("id") in QUEUE else 0
            return self.send(200, out)
        if u.path == "/replay":
            p = os.path.join(REPLAYS, os.path.basename(one("id") or "") + ".mp4")
            if not os.path.isfile(p):
                return self.fail(404, "no replay yet")
            data = open(p, "rb").read()
            return self.send(200, data, "video/mp4",
                             {"Accept-Ranges": "none",
                              "Content-Disposition": 'inline; filename="replay.mp4"'})
        return self.fail(404, "no such page")

    def _upload(self, upload_id):
        if not upload_id:
            return None
        p = os.path.join(UPLOADS, os.path.basename(upload_id))
        return p if os.path.isfile(p) else None

    # ---- POST ---------------------------------------------------------
    def do_POST(self):
        u = urllib.parse.urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD:
            return self.fail(413, "that clip is over the %dGB limit"
                             % (MAX_UPLOAD // 1024 ** 3))

        if u.path == "/upload/start":
            name = self.headers.get("X-Filename") or "clip.mp4"
            upload_id = safe_id(name)
            open(os.path.join(UPLOADS, upload_id), "wb").close()
            try:
                want = int(self.headers.get("X-Filesize") or 0)
            except ValueError:
                want = 0
            if want > MAX_UPLOAD:
                return self.fail(413, "that clip is over the %dGB limit"
                                 % (MAX_UPLOAD // 1024 ** 3))
            EXPECTED[upload_id] = want
            return self.send(200, {"id": upload_id})

        if u.path == "/upload/chunk":
            q = urllib.parse.parse_qs(u.query)
            upload_id = (q.get("id") or [""])[0]
            path = os.path.join(UPLOADS, os.path.basename(upload_id))
            if not upload_id or not os.path.isfile(path):
                self.rfile.read(n)          # drain, or the connection desyncs
                return self.fail(404, "unknown upload")
            # Append at the offset the client claims. Re-sending a chunk that
            # already landed overwrites the same bytes instead of duplicating
            # them, so a retry after a dropped connection is safe.
            try:
                off = int((q.get("offset") or ["0"])[0])
            except ValueError:
                self.rfile.read(n)
                return self.fail(400, "bad offset")
            left, buf = n, []
            while left > 0:
                chunk = self.rfile.read(min(1 << 20, left))
                if not chunk:
                    break
                buf.append(chunk)
                left -= len(chunk)
            with open(path, "r+b") as fh:
                fh.seek(off)
                fh.write(b"".join(buf))
            return self.send(200, {"ok": True, "size": os.path.getsize(path)})

        if u.path == "/upload/finish":
            q = urllib.parse.parse_qs(u.query)
            upload_id = (q.get("id") or [""])[0]
            path = os.path.join(UPLOADS, os.path.basename(upload_id))
            if not upload_id or not os.path.isfile(path):
                return self.fail(404, "unknown upload")
            # A truncated upload still opens: an MP4 carries its duration in a
            # header, so a quarter of a file reports the full 300s and then gets
            # silently measured short. Check the bytes all arrived.
            want = EXPECTED.get(upload_id, 0)
            got = os.path.getsize(path)
            if want and got != want:
                return self.fail(400, "upload is incomplete (%d of %d bytes) - "
                                      "please try again" % (got, want))
            try:
                frame, dur = first_frame(path)
            except ValueError as e:
                os.remove(path)
                return self.fail(400, str(e))
            EXPECTED.pop(upload_id, None)
            h, w = frame.shape[:2]
            return self.send(200, {"id": upload_id, "w": w, "h": h,
                                   "dur": round(dur, 1),
                                   "dishes": dishes_in(frame)})

        if u.path == "/upload":
            name = self.headers.get("X-Filename") or "clip.mp4"
            upload_id = safe_id(name)
            path = os.path.join(UPLOADS, upload_id)
            # Stream to disk: a phone clip does not belong in memory.
            left = n
            with open(path, "wb") as fh:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    fh.write(chunk)
                    left -= len(chunk)
            try:
                frame, dur = first_frame(path)
            except ValueError as e:
                os.remove(path)
                return self.fail(400, str(e))
            h, w = frame.shape[:2]
            return self.send(200, {"id": upload_id, "w": w, "h": h,
                                   "dur": round(dur, 1),
                                   "dishes": dishes_in(frame)})

        if u.path == "/measure":
            body = json.loads(self.rfile.read(n) or b"{}")
            path = self._upload(body.get("id"))
            if path is None:
                return self.fail(404, "unknown upload")
            try:
                dish_mm = float(body["dish_mm"])
                cx, cy, r = float(body["cx"]), float(body["cy"]), float(body["r"])
            except (KeyError, TypeError, ValueError):
                return self.fail(400, "need dish_mm and a dish circle")
            if not (5.0 <= dish_mm <= 500.0) or r < 20:
                return self.fail(400, "dish diameter or circle looks wrong")
            job_id = safe_id(os.path.basename(path))
            with JOBS_LOCK:
                JOBS[job_id] = {"state": "queued", "path": path, "cx": cx, "cy": cy,
                                "r": r, "dish_mm": dish_mm,
                                "steady": bool(body.get("steady")), "log": []}
            enqueue(job_id)
            return self.send(200, {"job": job_id})

        return self.fail(404, "no such endpoint")


def main():
    os.makedirs(UPLOADS, exist_ok=True)
    os.makedirs(REPLAYS, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("larvatrack  ->  http://localhost:%d   (one larva per dish)" % PORT)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
