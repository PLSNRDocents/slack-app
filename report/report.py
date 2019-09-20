# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

from contextlib import contextmanager
import logging
from typing import List

from flask import Flask
import sqlalchemy
from sqlalchemy.orm import joinedload

from dbmodel import TYPE_DISTURBANCE, TYPE_TRAIL, PhotoModel, ReportModel
import slack_api


# Used so we can easily mock out in unit tests.
def sort_by_date():
    return sqlalchemy.desc(ReportModel.create_datetime)


class Report:
    def __init__(self, db, app: Flask):
        self._db = db
        self._app = app
        self._logger = logging.getLogger(__name__)

    def create(self, rtype, who, channel, dinfo):
        # This is run in an eventloop - so need to push app context.
        with self._app.app_context():
            nr = ReportModel(type=rtype)
            nr.channel = channel["id"]
            nr.details = dinfo["details"]
            nr.location = dinfo["location"]
            nr.issues = dinfo["issues"]
            nr.gps = dinfo["gps"]
            nr.cross_trail = dinfo["cross"]
            nr.reporter_slack_handle = who["name"]
            nr.reporter_slack_id = who["id"]

            self._db.session.add(nr)
            self._db.session.commit()

            # Inform user
            slack_api.post_message(
                channel["id"],
                who["id"],
                "Report {} saved. Consider adding photos.".format(
                    Report.report_name(nr)
                ),
            )

    def fetch_all(self, limit=10) -> List[ReportModel]:
        query = ReportModel.query

        query = query.options(joinedload("photos"))

        query = query.order_by(sort_by_date())
        if limit:
            query = query.limit(limit)
        return query.all()

    def get(self, rid) -> ReportModel:
        r = ReportModel.query.get(rid)
        return r

    def delete(self, rid):
        r = self.get(rid)
        if not r:
            raise ValueError()
        self._db.session.delete(r)
        self._db.session.commit()

    @contextmanager
    def acquire_for_update(self, rm, photo: PhotoModel = None):
        """ Re-lookup row and lock for update.
        This is critical when running in multi-process (uwsgi) mode.
        """

        try:
            # flush current info so we queue waiting for any other pending updates.
            self._db.session.expire(rm)
            nrm = ReportModel.query.with_for_update().get(rm.id)
            if not nrm:
                self._logger.warning("Report disappeared %s", rm.id)
                raise Exception('Invalid report id: {}'.format(rm.id))
            if photo:
                self._db.session.add(photo)
            yield nrm
            self._db.session.commit()
        except Exception:
            self._db.session.rollback()
            raise

    @staticmethod
    def report_name(rm):
        if rm.type == TYPE_TRAIL:
            rid = "[TR-{}]".format(rm.id)
        elif rm.type == TYPE_DISTURBANCE:
            rid = "[DR-{}]".format(rm.id)
        else:
            rid = rm.id
        return rid
