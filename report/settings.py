# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.


class Settings:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True
    # SQLALCHEMY_ECHO = True


class DevSettings(Settings):
    EV_MODE = "ev"
    SQLALCHEMY_DATABASE_URI = "postgresql://jwag@localhost/plsnr"

    S3_BUCKET = "plsnr-slack-test"
    AWS_PROFILE = "plsnr"
    BOT_NAME = "otter-bot-test"


class AWSDevSettings(Settings):
    EV_MODE = "zappa"
    SQLALCHEMY_DATABASE_URI = (
        "postgresql://plsnr:plsnr6262@"
        "plsnr-slack-dev.cluster-cex79jl1h28t.us-east-1."
        "rds.amazonaws.com:5432/plsnr"
    )

    S3_BUCKET = "plsnr-slack-test"
    BOT_NAME = "otter-bot"


class AWSRDSSettings(DevSettings):
    # local/IDE running against Amazon RDS using ssh tunnel
    # Used mostly for migrate etc.
    SQLALCHEMY_DATABASE_URI = "postgresql://postgres:plsnr6262@localhost:12000/plsnr"
