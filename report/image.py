# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import os
import shutil
from tempfile import mkstemp


from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS
import requests


def add_photo(finfo, rid):
    fd, local_file = mkstemp(suffix="." + finfo["filetype"])
    try:
        # fetch and store locally
        fetch_image(finfo["url_private"], local_file)

        with Image.open(local_file) as im:
            # find GPS coordinates - note that IOS actually strips this
            # so likely we won't find any.
            exif_data = get_exif_data(im)
            lat, lon = get_lat_lon(exif_data)

        # TODO - upload to report?
        return
    finally:
        os.close(fd)
        os.remove(local_file)


def fetch_image(url, local_file):
    headers = {"Authorization": "Bearer {}".format(os.environ["BOT_TOKEN"])}
    with requests.get(url, stream=True, headers=headers) as r:
        r.raise_for_status()
        with open(local_file, "w+b") as f:
            shutil.copyfileobj(r.raw, f)


def get_exif_data(image: Image):
    """Returns a dictionary from the exif data of an PIL Image item.
    Also converts the GPS Tags
    """
    exif_data = {}
    info = image._getexif()
    if info:
        for tag, value in info.items():
            decoded = TAGS.get(tag, tag)
            if decoded == "GPSInfo":
                gps_data = {}
                for t in value:
                    sub_decoded = GPSTAGS.get(t, t)
                    gps_data[sub_decoded] = value[t]

                exif_data[decoded] = gps_data
            else:
                exif_data[decoded] = value

    return exif_data


def _get_if_exist(data, key):
    if key in data:
        return data[key]

    return None


def _convert_to_degress(value):
    """
    Helper function to convert the GPS coordinates stored in the EXIF
    to degrees in float format
    """
    d0 = value[0][0]
    d1 = value[0][1]
    d = float(d0) / float(d1)

    m0 = value[1][0]
    m1 = value[1][1]
    m = float(m0) / float(m1)

    s0 = value[2][0]
    s1 = value[2][1]
    s = float(s0) / float(s1)

    return d + (m / 60.0) + (s / 3600.0)


def get_lat_lon(exif_data):
    """Returns the latitude and longitude, if available,
    from the provided exif_data (obtained through get_exif_data above)
    """
    lat = None
    lon = None

    if "GPSInfo" in exif_data:
        gps_info = exif_data["GPSInfo"]

        gps_latitude = _get_if_exist(gps_info, "GPSLatitude")
        gps_latitude_ref = _get_if_exist(gps_info, "GPSLatitudeRef")
        gps_longitude = _get_if_exist(gps_info, "GPSLongitude")
        gps_longitude_ref = _get_if_exist(gps_info, "GPSLongitudeRef")

        if gps_latitude and gps_latitude_ref and gps_longitude and gps_longitude_ref:
            lat = _convert_to_degress(gps_latitude)
            if gps_latitude_ref != "N":
                lat = 0 - lat

            lon = _convert_to_degress(gps_longitude)
            if gps_longitude_ref != "E":
                lon = 0 - lon

    return lat, lon
