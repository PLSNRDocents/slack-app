# Copyright 2015-2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Migrate db using Alembic and flask-migrate
activate venv
PLSNRENV=Dev FLASK_APP=manage flask db history

PLSNRENV=Dev FLASK_APP=manage flask db migrate -m 'reason'

Edit migration version file then:

...  flask db upgrade

For AWS setup ssh tunnel first:
ssh -i ~/.ssh/plsnr_aws_iam_user.pem ec2-user@54.81.108.17
 -L 12000:plsnr-slack-dev.cluster-cex79jl1h28t.us-east-1.rds.amazonaws.com:5432 -N

Then PLSNRENV=AWSRDS FLASK_APP=manage

"""
import os

from flask import Flask
from flask_migrate import Migrate

app = Flask(__name__)
mode = os.environ["PLSNRENV"]
app.config.from_object("settings." + mode + "Settings")

from dbmodel import db  # noqa E402

migrate = Migrate(app, db)
