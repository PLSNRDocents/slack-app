# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import datetime

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.sql import func

db = SQLAlchemy()


class ReportModel(db.Model):
    """
    Information about any report - trail or disturbance.
    """

    id: int = db.Column(db.Integer, primary_key=True)
    create_datetime = db.Column(db.DateTime, nullable=False)
    # server_default is basically for upgrade DB
    update_datetime = db.Column(
        db.DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=datetime.datetime.utcnow,
    )
    type: str = db.Column(db.String(length=32), nullable=False)

    # e.g. trail name
    location: str = db.Column(db.String(length=16), nullable=False)

    cross_trail: str = db.Column(db.String(length=16), nullable=True)

    # e.g. tree/obstruction - comma separated
    issues: str = db.Column(db.String(length=256), nullable=False)

    # ideally the real name
    reporter: str = db.Column(db.String(length=128))
    reporter_slack_handle: str = db.Column(db.String(length=64))
    reporter_slack_id: str = db.Column(db.String(length=64))

    details: str = db.Column(db.UnicodeText, nullable=True)
    status: str = db.Column(db.String(length=32), nullable=False)

    # lat, lon - format ??
    gps: str = db.Column(db.String(length=128), nullable=True)

    # channel this report was filed on
    channel: str = db.Column(db.String(length=64), nullable=True)

    # if a report goes away, so should all pictures.
    photos = db.relationship(
        "PhotoModel",
        backref="report",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    def __init__(self, status, **kwargs):
        """ Init a dbmodel
        Of course - this is just for creating new - normally all these fields are
        filled in by a DB fetch.
        The super __init__ will use kwargs to init fields - we only fill fields that
        either aren't fillable or need special default
        """

        self.create_datetime = datetime.datetime.utcnow()
        self.update_datetime = datetime.datetime.utcnow()
        self.status = status

        # overwrite with passed kwargs
        super().__init__(**kwargs)


class PhotoModel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(
        db.Integer, db.ForeignKey("report_model.id", ondelete="CASCADE"), nullable=False
    )
    slack_file_id: str = db.Column(db.String(length=32), nullable=False)
    s3_url = db.Column(db.String(length=256), nullable=False)

    def __init__(self, report: ReportModel, **kwargs):
        """
        :param kwargs: other init keys: text, attrs

        Need to pass in s3_url
        """
        self.report = report
        self.create_datetime = datetime.datetime.utcnow()
        self.update_datetime = datetime.datetime.utcnow()
        # overwrite with passed kwargs
        super().__init__(**kwargs)
