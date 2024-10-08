# Copyright 2019-2023 by J. Christopher Wagner (jwag). All rights reserved.


class Settings:
    USE_DYNAMO = True
    ENABLE_TRAIL_REPORT = False

    PLSNR_USERNAME = None
    PLSNR_PASSWORD = None

    SSL_VERIFY = True


class DevSettings(Settings):
    EV_MODE = "ev"

    AWS_PROFILE = "plsnr"

    DYNAMO_ENABLE_LOCAL = True
    DYNAMO_LOCAL_HOST = "localhost"
    DYNAMO_LOCAL_PORT = 8000

    PLSNR_HOST = "http://plsnrd10:12001"  # local indigo

    SSL_VERIFY = False


class AWSDevSettings(Settings):
    EV_MODE = "zappa"

    DYNAMO_TABLE_SUFFIX = "-test"

    PLSNR_HOST = "https://devd10-2g4wgvy-mhab7wjgx42wa.us-3.platformsh.site"


class AWSProdSettings(Settings):
    EV_MODE = "zappa"

    DYNAMO_TABLE_SUFFIX = "-live"

    PLSNR_HOST = "https://docents.plsnr.org"
