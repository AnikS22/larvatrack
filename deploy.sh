#!/usr/bin/env bash
# Publish the page to Vercel, pointed at this laptop's current tunnel.
#
# Vercel serves the page; the measuring runs here, because the tracker needs
# OpenCV, trackpy and minutes of CPU per clip - none of which fits a serverless
# function. The tunnel is how the page reaches this machine.
#
# Run it again whenever the tunnel URL changes (a free ngrok URL changes every
# restart). Nothing else needs touching.
set -euo pipefail
cd "$(dirname "$0")"

command -v ngrok  >/dev/null || { echo "ngrok is not installed"; exit 1; }
command -v vercel >/dev/null || { echo "vercel CLI is not installed"; exit 1; }

curl -sf http://localhost:8020/health >/dev/null \
  || { echo "app.py is not running - start it with: .venv-track/bin/python app.py"; exit 1; }

if ! curl -sf http://127.0.0.1:4040/api/tunnels >/dev/null 2>&1; then
  echo "starting ngrok..."
  nohup ngrok http 8020 --log=stdout >/tmp/ngrok.log 2>&1 &
  sleep 6
fi

TUNNEL=$(curl -s http://127.0.0.1:4040/api/tunnels | python3 -c "
import json,sys
t=json.load(sys.stdin)['tunnels']
print(next(x['public_url'] for x in t if x['public_url'].startswith('https')))")
[ -n "$TUNNEL" ] || { echo "could not read the ngrok tunnel URL"; exit 1; }
echo "tunnel: $TUNNEL"

mkdir -p site
# Pin the tunnel into the published copy. app.html stays origin-relative so it
# still works when opened straight off this machine.
python3 - "$TUNNEL" <<'PY'
import sys
url = sys.argv[1]
html = open("app.html").read()
tag = '<script>window.BACKEND_URL=%r;</script>\n' % url
open("site/index.html", "w").write(tag + html)
PY

# framework:null and an empty build stop Vercel reaching for the Python builder
# it remembers from this project's earlier life as a serverless tracker.
cat > site/vercel.json <<'JSON'
{
  "version": 2,
  "framework": null,
  "buildCommand": null,
  "installCommand": null,
  "outputDirectory": ".",
  "cleanUrls": true
}
JSON

vercel deploy site --prod --yes --name larvatrack
