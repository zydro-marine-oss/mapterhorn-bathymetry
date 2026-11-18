# Rebuild file_list.txt from the official CHS NONNA index shapefile.
# Download NONNA10.zip from the Open Government record, unzip it beside this script, then run.
import os
import sys
from osgeo import ogr

COVERAGE = "nonna__NONNA%2010%20Coverage"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "file_list.txt")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: create_file_list.py path/to/NONNA10.shp")
    source = ogr.Open(sys.argv[1])
    layer = source.GetLayer(0)
    lines = []
    for feature in layer:
        west, east, south, north = feature.GetGeometryRef().GetEnvelope()
        name = (feature.GetField("OBJNAM") or "cell") + ".tif"
        url = (
            "https://nonna-geoserver.data.chs-shc.ca/geoserver/wcs?service=WCS&version=2.0.1"
            "&request=GetCoverage&coverageId=" + COVERAGE + "&format=image/tiff"
            "&subsettingCrs=http://www.opengis.net/def/crs/EPSG/0/4326"
            "&subset=Long({:.5f},{:.5f})&subset=Lat({:.5f},{:.5f})"
        ).format(west, east, south, north)
        lines.append(url + "\t" + name)
    with open(OUT, "w") as handle:
        handle.write("\n".join(lines) + "\n")
    print("wrote {}".format(len(lines)))


if __name__ == "__main__":
    main()
