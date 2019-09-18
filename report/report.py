# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

from typing import List

from flask import Flask

from dbmodel import ReportModel


class Report:
    def __init__(self, db, app: Flask):
        self._db = db
        self._app = app

    def create(self, who, channel, dinfo):
        with self._app.app_context():
            nr = ReportModel()
            nr.channel = channel["id"]
            nr.details = dinfo["details"]
            nr.location = dinfo["location"]
            nr.issue = dinfo["issue"]
            nr.gps = dinfo["gps"]
            nr.reporter_slack_handle = who["name"]
            nr.reporter_slack_id = who["id"]

            self._db.session.add(nr)
            self._db.session.commit()

    def fetch_all(self) -> List[ReportModel]:
        query = ReportModel.query

        r = query.all()
        return r
