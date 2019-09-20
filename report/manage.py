# Copyright 2015-2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Migrate db using Alembic and flask-migrate
activate venv
PLSNRENV=Dev FLASK_APP=manage flask db history

PLSNRENV=Dev FLASK_APP=manage flask db migrate -m 'reason'

Edit migration version file then:

...  flask db upgrade

"""
import os

from flask import Flask
from flask_migrate import Migrate

app = Flask(__name__)
mode = os.environ["PLSNRENV"]
app.config.from_object("settings." + mode + "Settings")

from dbmodel import db  # noqa E402

migrate = Migrate(app, db)
