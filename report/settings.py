# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.


class Settings:
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_RECORD_QUERIES = True


class DevSettings(Settings):
    SQLALCHEMY_DATABASE_URI = "postgresql://jwag@localhost/plsnr"

    S3_BUCKET = "plsnr-slack-test"
