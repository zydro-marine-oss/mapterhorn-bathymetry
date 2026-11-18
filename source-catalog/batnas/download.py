# Download BATNAS GeoTIFFs from Badan Informasi Geospasial.
# The sheet index is public. Each file needs a short-lived token from a
# logged-in browser session at https://tanahair.indonesia.go.id/
# (Unduh, BATNAS, copy the token query parameter).
#
#   BATNAS_TOKEN=... python3 download.py
#
# Run with the working directory set to pipelines/. Files land in
# source-store/batnas/.
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

INDEX = "https://tanahair.indonesia.go.id/portal-web/batnas.json"
DOWNLOAD = "https://tanahair.indonesia.go.id/api-inageo/unduh/batnas"
VERSIONS = ("1.6", "1.5", "1.1")


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mapterhorn-bathymetry"})
    with urllib.request.urlopen(req, timeout=300) as response:
        return response.read()


def main():
    token = os.environ.get("BATNAS_TOKEN", "").strip()
    if not token:
        raise SystemExit("Set BATNAS_TOKEN to the short-lived download token from tanahair.indonesia.go.id")
    out_dir = "source-store/batnas"
    os.makedirs(out_dir, exist_ok=True)
    payload = json.loads(get(INDEX))
    features = payload["features"] if isinstance(payload, dict) else payload
    saved = 0
    for feature in features:
        penamaan = feature["properties"]["Penamaan"]
        written = None
        for version in VERSIONS:
            filename = "BATNAS_{}_MSL_v{}.tif".format(penamaan, version)
            query = urllib.parse.urlencode({"token": token, "filename": filename})
            try:
                data = get(DOWNLOAD + "?" + query)
            except urllib.error.HTTPError as exc:
                if exc.code == 401:
                    raise SystemExit("BATNAS_TOKEN was rejected (401). It may have expired.")
                continue
            if data[:2] in (b"II", b"MM"):
                with open(os.path.join(out_dir, filename), "wb") as handle:
                    handle.write(data)
                written = filename
                break
        if written:
            saved += 1
            print(written)
        else:
            print("no sheet for {}".format(penamaan), file=sys.stderr)
    print("saved {}".format(saved))


if __name__ == "__main__":
    main()
