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
import shutil
import subprocess
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
RESULTS = os.path.join(HERE, "results")
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
# Measured, not guessed. The same clip downscaled, against its full-res answer
# of 72.1mm:
#     dish 534px  71.4mm   -1%
#     dish 445px  72.3mm   +0%
#     dish 392px 112.4mm  +56%
#     dish 297px 174.0mm +141%
#     dish 148px   nothing found
# It does not degrade gracefully - below the cliff it returns confident nonsense
# rather than an imprecise answer, which is far worse than refusing.
MIN_DISH_PX = 440
JOBS = {}
JOBS_LOCK = threading.Lock()
# Files already on this machine, offered instead of an upload. Only enabled with
# --local, and the server then binds to localhost: this hands out the contents of
# real directories, which has no business being reachable through a tunnel.
LOCAL = False
LOCAL_DIRS = []
LOCAL_IDS = {}
VIDEO_EXT = (".mp4", ".mov", ".m4v", ".avi", ".mkv")
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
        anchors = job.get("anchors") or None
        if job.get("manual"):
            # Hand-traced: the clicked points ARE the path. No detection, no
            # trajectory picking - the operator has already decided where the
            # animal was, and the job is only to add the distance up.
            per = tptrack.manual_paths(job["dish_mm"], circle, anchors, log=log)
            total = sum(per.values())
            # Written to disk the moment it is computed. A tab was closed once
            # and took an afternoon of tracing with it; the numbers are cheap to
            # store and the tracing is not.
            rec = {"saved": time.strftime("%Y-%m-%d %H:%M:%S"),
                   "video": os.path.basename(job["path"]),
                   "circle": [circle[0], circle[1], circle[2]],
                   "dish_mm": job["dish_mm"], "method": "hand-traced",
                   "per_larva_mm": {str(k): round(v, 1) for k, v in per.items()},
                   "per_larva_cm": {str(k): round(v / 10.0, 3) for k, v in per.items()},
                   "plate_total_mm": round(total, 1),
                   "points": len(anchors),
                   "anchors": [list(a) for a in anchors]}
            os.makedirs(RESULTS, exist_ok=True)
            fp = os.path.join(RESULTS, job_id + ".json")
            with open(fp, "w") as fh:
                json.dump(rec, fh, indent=1)
            log("saved %s" % fp)
            job.update(state="done", mm=round(total, 1), seen=round(total, 1),
                       bridged=0.0, manual=True, saved_to=fp,
                       per_larva={str(k): round(v, 1) for k, v in per.items()},
                       per_larva_cm={str(k): round(v / 10.0, 3) for k, v in per.items()})
            return
        if not trs:
            raise tptrack.NoLarva(
                "no larva found in that dish. The dish circle is %d px across; if "
                "that is smaller than the dish in the frame, set it again. "
                "Otherwise the larva may be too faint to pick out." % int(2 * circle[2]))
        total, seen, bridged = tptrack.measure(
            job["path"], job["dish_mm"], circle, log=log, steady=job["steady"],
            trs=trs, anchors=anchors)
        tptrack.replay(job["path"], job["dish_mm"], circle, out, larvae=1,
                       steady=job["steady"], log=log, trs=trs, anchors=anchors)
        job.update(state="done", mm=round(total, 1), seen=round(seen, 1),
                   bridged=round(bridged, 1), replay="/replay?id=" + job_id)
    except tptrack.NoLarva as e:
        job["state"] = "error"
        job["error"] = str(e)
    except BaseException as e:
        # BaseException on purpose. A SystemExit raised down in the tracker used
        # to slip past "except Exception", kill this thread, and leave the job
        # stuck on "running" with every later upload queued behind it forever.
        job["state"] = "error"
        job["error"] = "%s: %s" % (type(e).__name__, e)
        log(traceback.format_exc()[-800:])


def worker():
    while True:
        try:
            with QUEUE_CV:
                while not QUEUE:
                    QUEUE_CV.wait()
                job_id = QUEUE.pop(0)
            run_job(job_id)
        except BaseException:
            # Whatever happened to one job, the queue has to keep moving.
            traceback.print_exc()


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
        if u.path == "/local":
            if not LOCAL:
                return self.fail(403, "local files are off on this server")
            out = []
            for rank, d in enumerate(LOCAL_DIRS):
                for name in sorted(os.listdir(d)):
                    if not name.lower().endswith(VIDEO_EXT) or name.startswith("."):
                        continue
                    p = os.path.realpath(os.path.join(d, name))
                    if not os.path.isfile(p):
                        continue
                    out.append({"path": p, "name": name, "rank": rank,
                                "dir": os.path.basename(d.rstrip("/")) or d,
                                "mb": round(os.path.getsize(p) / 1048576.0)})
            # Assay recordings first, then by name. Sorting by size just floated
            # unrelated 6GB video projects to the top of the list.
            out.sort(key=lambda r: (r["rank"], r["name"].lower()))
            return self.send(200, {"files": out[:400]})

        if u.path == "/jobs":
            out = []
            for jid, j in JOBS.items():
                out.append({k: v for k, v in j.items()
                            if k not in ("path", "log", "anchors")}
                           | {"id": jid, "video": os.path.basename(j["path"]),
                              "pins": len(j.get("anchors") or [])})
            return self.send(200, {"jobs": out})

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
        if u.path == "/clip":
            # The dish on its own, to be played and followed with the mouse.
            # Cached: cropping a 5-minute clip takes a few seconds and the same
            # plate gets re-watched once per animal.
            src = self._upload(one("id"))
            if src is None:
                return self.fail(404, "unknown upload")
            try:
                cx, cy, r = (int(float(one(k, "0"))) for k in ("cx", "cy", "r"))
            except ValueError:
                return self.fail(400, "bad circle")
            try:
                speed = max(1.0, min(40.0, float(one("speed", "1"))))
            except ValueError:
                speed = 1.0
            tag = "clip_%s_%d_%d_%d_x%g.mp4" % (
                re.sub(r"[^A-Za-z0-9]", "", os.path.basename(src))[-24:],
                cx, cy, r, speed)
            path = os.path.join(REPLAYS, tag)
            if not os.path.isfile(path):
                ff = shutil.which("ffmpeg")
                if not ff:
                    return self.fail(500, "ffmpeg is needed to crop the clip")
                side = 2 * r
                # Negative offsets are legal here: pad rather than refuse, so a
                # plate against the frame edge still plays centred.
                vf = ("pad=iw+%d:ih+%d:%d:%d:gray,crop=%d:%d:%d:%d"
                      % (2 * side, 2 * side, side, side,
                         side, side, cx - r + side, cy - r + side))
                # Speed is baked in rather than left to the browser. Asking a
                # video element for playbackRate 10 makes it drop frames it
                # cannot decode in time, and the plate visibly jumps - which is
                # exactly what you cannot follow with a pointer. setpts rewrites
                # the timestamps, so the result plays at 1x, every frame shown.
                if speed > 1.0:
                    vf += ",setpts=PTS/%g" % speed
                cmd = [ff, "-y", "-v", "error", "-i", src, "-vf", vf,
                       "-an", "-c:v", "libx264", "-preset", "veryfast",
                       "-crf", "26"]
                if speed > 1.0:
                    cmd += ["-r", "30"]     # constant rate, so it plays smooth
                cmd += ["-movflags", "+faststart", path]
                r_ = subprocess.run(cmd, capture_output=True)
                if r_.returncode != 0:
                    log_err = r_.stderr.decode()[-300:]
                    sys.stderr.write("ffmpeg: %s\n" % log_err)
            if not os.path.isfile(path):
                return self.fail(500, "could not crop that clip")
            data = open(path, "rb").read()
            return self.send(200, data, "video/mp4",
                             {"Accept-Ranges": "none"})

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
        if upload_id in LOCAL_IDS:
            p = LOCAL_IDS[upload_id]
            return p if os.path.isfile(p) else None
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

        if u.path == "/local/pick":
            if not LOCAL:
                return self.fail(403, "local files are off on this server")
            body = json.loads(self.rfile.read(n) or b"{}")
            want = os.path.realpath(body.get("path") or "")
            # Must sit inside a directory that was explicitly offered.
            if not any(want.startswith(os.path.realpath(d) + os.sep)
                       for d in LOCAL_DIRS) or not os.path.isfile(want):
                return self.fail(404, "that file is not one of the offered ones")
            try:
                frame, dur = first_frame(want)
            except ValueError as e:
                return self.fail(400, str(e))
            token = "local:" + safe_id(os.path.basename(want))
            LOCAL_IDS[token] = want
            h, w = frame.shape[:2]
            return self.send(200, {"id": token, "w": w, "h": h,
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
            if 2 * r < MIN_DISH_PX:
                return self.fail(400,
                    "the dish is only %d px across; below about %d px the "
                    "measurement is not just rough, it is wrong - the same clip "
                    "at this size reads 141%% too long. Either the dish circle is "
                    "set too small, or the video was downscaled before upload "
                    "(AirDrop, iMessage and iCloud all do this). Send the "
                    "original recording." % (2 * r, MIN_DISH_PX))
            try:
                anchors = [(float(a["t"]), float(a["x"]), float(a["y"]),
                            int(a.get("larva", 1)))
                           # 0.4s sampling over a 5-minute plate is ~750 points
                           # per animal; five of them need room, and a silent
                           # truncation here would quietly shorten a path.
                           for a in (body.get("anchors") or [])][:8000]
            except (KeyError, TypeError, ValueError):
                return self.fail(400, "a correction is missing t, x or y")
            manual = bool(body.get("manual"))
            if manual and len(anchors) < 2:
                return self.fail(400, "hand tracing needs at least two points")
            job_id = safe_id(os.path.basename(path))
            with JOBS_LOCK:
                JOBS[job_id] = {"state": "queued", "path": path, "cx": cx, "cy": cy,
                                "r": r, "dish_mm": dish_mm,
                                "steady": bool(body.get("steady")),
                                "anchors": anchors, "manual": manual, "log": []}
            enqueue(job_id)
            return self.send(200, {"job": job_id})

        return self.fail(404, "no such endpoint")


def main():
    global LOCAL, LOCAL_DIRS, PORT
    if "--port" in sys.argv:
        PORT = int(sys.argv[sys.argv.index("--port") + 1])
    if "--local" in sys.argv:
        LOCAL = True
        LOCAL_DIRS = [d for d in (
            os.path.join(HERE, "videos"),     # the assay recordings, listed first
            os.path.join(HERE, "clips"),
            os.path.expanduser("~/Downloads"),
            UPLOADS,
        ) if os.path.isdir(d)]
    os.makedirs(UPLOADS, exist_ok=True)
    os.makedirs(REPLAYS, exist_ok=True)
    os.makedirs(RESULTS, exist_ok=True)
    # One worker by default: the tracker already uses every core, so a second
    # job in parallel finishes both later. More is worth it only locally, when
    # several dishes are being worked through at once and each is mostly idle
    # waiting on the operator.
    n_workers = 1
    if "--workers" in sys.argv:
        n_workers = max(1, min(8, int(sys.argv[sys.argv.index("--workers") + 1])))
    for _ in range(n_workers):
        threading.Thread(target=worker, daemon=True).start()
    print("%d worker(s)" % n_workers)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("larvatrack  ->  http://localhost:%d   (one larva per dish)" % PORT)
    if LOCAL:
        print("local files on, no upload needed, from:")
        for d in LOCAL_DIRS:
            print("   ", d)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")


if __name__ == "__main__":
    main()
