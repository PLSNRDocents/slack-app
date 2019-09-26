# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

from contextlib import contextmanager
import logging
from tempfile import NamedTemporaryFile
from typing import List
import os

from flask import Flask
import sqlalchemy
from sqlalchemy.orm import joinedload

from dbmodel import (
    TYPE_DISTURBANCE,
    TYPE_TRAIL,
    PhotoModel,
    ReportModel,
    STATUS_CONFIRMED,
    STATUS_PLACEHOLDER,
    STATUS_REPORTED,
)
import image
import slack_api

logger = logging.getLogger(__name__)


# Used so we can easily mock out in unit tests.
def sort_by_date():
    return sqlalchemy.desc(ReportModel.create_datetime)


class Report:
    def __init__(self, db, app: Flask):
        self._db = db
        self._app = app
        self._logger = logging.getLogger(__name__)

    def _fillin(self, nr, rtype, who, channel, dinfo):
        nr.type = rtype
        nr.channel = channel["id"]
        nr.details = dinfo["details"]
        nr.location = dinfo["location"]
        nr.issues = dinfo["issues"]
        nr.gps = dinfo["gps"]
        nr.cross_trail = dinfo["cross"]
        nr.reporter_slack_handle = who["name"]
        nr.reporter_slack_id = who["id"]
        nr.reporter = slack_api.user_to_name(who["id"])

        self._db.session.add(nr)
        self._db.session.commit()

    def create(self, rtype, who, channel, dinfo):
        nr = ReportModel(type=rtype, status=STATUS_REPORTED)
        self._fillin(nr, rtype, who, channel, dinfo)
        return self.get(nr.id)

    def complete(self, nr, rtype, who, channel, dinfo):
        # Finish up a report created via start_new
        nr.status = STATUS_REPORTED
        self._fillin(nr, rtype, who, channel, dinfo)
        return self.get(nr.id)

    def start_new(self):
        """ When creating a report using interactive messages and photos
        were uploaded at the beginning.
        """
        nr = ReportModel(type="Unknown", status=STATUS_PLACEHOLDER)
        nr.location = "Unknown"
        nr.issues = "Unknown"
        self._db.session.add(nr)
        self._db.session.commit()
        return self.get(nr.id)

    def fetch_all(self, limit=10, active=True) -> List[ReportModel]:
        query = ReportModel.query

        query = query.options(joinedload("photos"))
        if active:
            query = query.filter(
                sqlalchemy.or_(
                    ReportModel.status == STATUS_REPORTED,
                    ReportModel.status == STATUS_CONFIRMED,
                )
            )

        query = query.order_by(sort_by_date())
        if limit:
            query = query.limit(limit)
        return query.all()

    def get(self, rid) -> ReportModel:
        r = ReportModel.query.options(joinedload("photos")).get(rid)
        return r

    def delete(self, rid):
        r = self.get(rid)
        if not r:
            raise ValueError()
        for p in r.photos:
            # remove from S3. PhotoModels will be automatically deleted.
            self._app.s3.delete(p.s3_url, Report.id_to_name(r))
        self._db.session.delete(r)
        self._db.session.commit()

    def delete_photos(self, rid):
        # delete all photos but leave report alone
        r = self.get(rid)
        if not r:
            raise ValueError()
        for p in r.photos:
            self._app.s3.delete(p.s3_url, Report.id_to_name(r))
            self._db.session.delete(p)
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
                raise Exception("Invalid report id: {}".format(rm.id))
            if photo:
                self._db.session.add(photo)
            yield nrm
            self._db.session.commit()
        except Exception:
            self._db.session.rollback()
            raise

    @staticmethod
    def id_to_name(rm):
        if rm.type == TYPE_TRAIL:
            rid = "TR-{}".format(rm.id)
        elif rm.type == TYPE_DISTURBANCE:
            rid = "DR-{}".format(rm.id)
        else:
            rid = rm.id
        return rid

    @staticmethod
    def name_to_id(rname):
        if rname.startswith("TR-") or rname.startswith("DR-"):
            rname = rname[3:]
        return rname


def add_photo(app, finfo, rm: ReportModel):
    # Assume called in app context.
    lat = None
    lon = None
    im = image.fetch_image(finfo["url_private"])
    if not rm.gps:
        # fetch image, find GPS coordinates - note that IOS actually strips this
        # so likely we won't find any.
        exif_data = image.get_exif_data(im)
        lat, lon = image.get_lat_lon(exif_data)
    # Save locally so can upload to S3
    local_file = NamedTemporaryFile(suffix="." + finfo["filetype"])
    im.save(local_file.name)

    s3_finfo = app.s3.save(
        local_file.name,
        finfo["filetype"],
        finfo["mimetype"],
        Report.id_to_name(rm),
        rm.id,
    )
    photo = PhotoModel(rm, slack_file_id=finfo["id"])
    photo.s3_url = s3_finfo["path"]

    with app.report.acquire_for_update(rm, photo):
        # report is locked, and photo has been added to session.
        if lat and lon:
            rm.gps = "{},{}".format(lat, lon)


def lax_remove(filename):
    try:
        os.remove(filename)
    except FileNotFoundError:
        pass
    except OSError as ex:
        logging.getLogger("lax_remove").warning(
            "Could not remove file: %s reason: %s", filename, ex
        )
