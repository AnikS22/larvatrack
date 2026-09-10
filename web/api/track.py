"""Measure how far larvae crawled in an uploaded clip.

The video is uploaded straight to Blob storage by the browser and only its URL
reaches this function - a clip is far larger than a function body may be.
"""
import json, math, os, tempfile, urllib.request
from http.server import BaseHTTPRequestHandler

import _larvatrack as lt

MAX_BYTES = 300 * 1024 * 1024
MAX_SECONDS = 6 * 60
DISH_PX = 640                    # ~1 GB peak; below ~550 a larva merges with the rim
PASSWORD = os.environ.get("LARVATRACK_PASSWORD", "")


def measure(url, dish_mm, larvae, hz):
    import cv2
    with urllib.request.urlopen(url, timeout=120) as r:
        if int(r.headers.get("Content-Length") or 0) > MAX_BYTES:
            raise lt.TrackingError("video is larger than 300 MB")
        fd, path = tempfile.mkstemp(suffix=".mp4", dir="/tmp")
        with os.fdopen(fd, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    try:
        cap = cv2.VideoCapture(path)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        secs = (cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0) / max(fps, 1e-6)
        cap.release()
        if secs > MAX_SECONDS:
            raise lt.TrackingError(
                f"clip is {secs / 60:.1f} min; the limit is {MAX_SECONDS // 60} min")

        S, cir = lt.analyse_video(path, dish_mm, hz=hz, expect=larvae or None,
                                  max_dish_px=DISH_PX, log=lambda *a: None)
        unit = "mm" if S["cfg"]["mm_per_px"] != 1.0 else "px"
        out = []
        for L in S["larvae"].values():
            c = lt.larva_cfg(S, L)
            total, _cum, gap, bridged = lt.path_length(L["pts"], c, L.get("offplane"))
            dur = L["pts"][-1][0] - L["pts"][0][0]
            seen = max(dur - gap, 1e-9)
            p0 = L["pts"][0]
            spread = max(math.hypot(p[1] - p0[1], p[2] - p0[2])
                         for p in L["pts"]) * c["mm_per_px"]
            out.append({
                "name": L["name"],
                "observed": round(total, 1),
                "gapChords": round(bridged, 1),
                "lowerBound": round(total + bridged, 1),
                "speed": round(total / seen, 2),
                "estimate5min": round(total / seen * 300.0, 1),
                "spread": round(spread, 1),
                "trackedSeconds": round(seen),
                "spanSeconds": round(dur),
                "offAgarSeconds": round(L.get("off_s", 0.0)),
                "samples": len(L["pts"]),
            })
        out.sort(key=lambda x: -x["observed"])
        return {"unit": unit, "clipSeconds": round(secs),
                "dishRadiusPx": round(cir[2]), "mmPerPx": round(S["cfg"]["mm_per_px"], 5),
                "larvae": out}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:
            return self._send(400, {"error": "could not read the request"})

        if PASSWORD and req.get("password") != PASSWORD:
            return self._send(401, {"error": "wrong password"})

        url = req.get("url") or ""
        if not url.startswith("https://") or "blob.vercel-storage.com" not in url:
            return self._send(400, {"error": "expected a Blob storage URL"})
        try:
            dish_mm = float(req.get("dishMm") or 0)
            if not 20.0 <= dish_mm <= 200.0:
                raise ValueError
        except ValueError:
            return self._send(400, {"error": "dish diameter must be 20-200 mm"})
        larvae = int(req.get("larvae") or 0)
        hz = float(req.get("hz") or 2.0)

        try:
            return self._send(200, measure(url, dish_mm, larvae, hz))
        except lt.TrackingError as e:
            return self._send(422, {"error": str(e)})
        except Exception as e:                       # never leak a stack to a stranger
            print("track failed:", repr(e))
            return self._send(500, {"error": "could not process that video"})
