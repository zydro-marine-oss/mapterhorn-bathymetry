# Rewrite file_list.txt from the public nz-coastal bucket.
# Keeps 1 m DEM GeoTIFFs. Anonymous listing, no credentials.
import fnmatch
import os
import re
import urllib.parse
import urllib.request

BUCKET = "https://nz-coastal.s3.ap-southeast-2.amazonaws.com/"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "file_list.txt")


def main():
    token = None
    lines = []
    while True:
        query = "list-type=2&max-keys=1000"
        if token:
            query += "&continuation-token=" + urllib.parse.quote(token, safe="")
        req = urllib.request.Request(BUCKET + "?" + query, headers={"User-Agent": "mapterhorn-bathymetry"})
        with urllib.request.urlopen(req, timeout=60) as response:
            xml = response.read().decode("utf-8")
        for key in re.findall(r"<Key>([^<]+)</Key>", xml):
            if not fnmatch.fnmatch(key, "*/dem_1m/*/*.tiff"):
                continue
            parts = key.split("/")
            local = "{}__{}__{}".format(parts[0], parts[1], parts[-1])
            if local.lower().endswith(".tiff"):
                local = local[:-5] + ".tif"
            url = BUCKET + urllib.parse.quote(key, safe="/")
            lines.append(url + "\t" + local)
        if "<IsTruncated>true</IsTruncated>" not in xml:
            break
        match = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", xml)
        if not match:
            break
        token = match.group(1)
    lines.sort()
    with open(OUT, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    print("wrote {} urls".format(len(lines)))


if __name__ == "__main__":
    main()
