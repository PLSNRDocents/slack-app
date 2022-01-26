# Copyright 2019-2022 by J. Christopher Wagner (jwag). All rights reserved.


class Settings:
    USE_DYNAMO = True
    ENABLE_TRAIL_REPORT = False

    PLSNR_USERNAME = None
    PLSNR_PASSWORD = None

    SSL_VERIFY = True

    # For 'at' - which calendars etc should we scrape.
    # WHICH_SCRAPE = ["info", "whalers", "public", "gate", "other"]
    # With new flexsched - we no longer do any scrapping!
    WHICH_SCRAPE = []


class DevSettings(Settings):
    EV_MODE = "ev"

    AWS_PROFILE = "plsnr"

    DYNAMO_ENABLE_LOCAL = True
    DYNAMO_LOCAL_HOST = "localhost"
    DYNAMO_LOCAL_PORT = 8000

    PLSNR_HOST = "http://platform-devd9:8888/"

    SSL_VERIFY = False


class AWSDevSettings(Settings):
    EV_MODE = "zappa"

    DYNAMO_TABLE_SUFFIX = "-test"

    PLSNR_HOST = "https://devd9-x4hjj4a-mhab7wjgx42wa.us-3.platformsh.site/"


class AWSProdSettings(Settings):
    EV_MODE = "zappa"

    DYNAMO_TABLE_SUFFIX = "-live"

    PLSNR_HOST = "https://docents.plsnr.org"
