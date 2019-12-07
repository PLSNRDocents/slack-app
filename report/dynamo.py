# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Use dynamoDB for our report store.

This has the advantage of:
1) at our usage it will be in the free tier
2) DDB has a VPC endpoint so our lambda can access it while running in the AWS
   lambda VPC - so we don't need a NAT gateway which is costing $$$

"""

from dataclasses import asdict, dataclass, field, fields
from datetime import datetime
from dateutil import tz
import decimal
import logging
import json
import re
from typing import List

import boto3
from boto3.dynamodb.conditions import Attr, Key
from dateutil import parser as date_parser

import image
import slack_api

from constants import (
    KIOSK_RESOLVED_UNKNOWN,
    STATUS_PLACEHOLDER,
    STATUS_REPORTED,
    STATUS_CONFIRMED,
    TRAIL_VALUE_2_DESC,
    TYPE_TRAIL,
    TYPE_DISTURBANCE,
    xlate_issues,
)

TN_LOOKUP = {"reports": "reports", "idgen": "idgen", "cache": "cache"}

TABLES = [
    {
        "TableName": "reports",
        "AttributeDefinitions": [
            dict(AttributeName="allreports", AttributeType="S"),
            dict(AttributeName="update_ts", AttributeType="N"),
            dict(AttributeName="id", AttributeType="S"),
        ],
        "KeySchema": [dict(AttributeName="id", KeyType="HASH")],
        "GlobalSecondaryIndexes": [
            dict(
                IndexName="byupdate",
                KeySchema=[
                    dict(AttributeName="allreports", KeyType="HASH"),
                    dict(AttributeName="update_ts", KeyType="RANGE"),
                ],
                Projection=dict(ProjectionType="ALL"),
                ProvisionedThroughput={"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
            )
        ],
        "ProvisionedThroughput": {"ReadCapacityUnits": 5, "WriteCapacityUnits": 5},
    },
    {
        "TableName": "idgen",
        "AttributeDefinitions": [dict(AttributeName="year", AttributeType="S")],  # YYYY
        "KeySchema": [dict(AttributeName="year", KeyType="HASH")],
        "ProvisionedThroughput": {"ReadCapacityUnits": 3, "WriteCapacityUnits": 3},
    },
    {
        "TableName": "cache",
        # PK for 'at': YYYYMMDD:where
        "AttributeDefinitions": [dict(AttributeName="ckey", AttributeType="S")],
        "KeySchema": [dict(AttributeName="ckey", KeyType="HASH")],
        "ProvisionedThroughput": {"ReadCapacityUnits": 3, "WriteCapacityUnits": 3},
    },
]


class DDB:
    def __init__(self, config, need_client=False):
        self._config = config
        self._logger = logging.getLogger(__name__)
        if config.get("AWS_PROFILE", None):
            self.session = boto3.Session(
                profile_name=config["AWS_PROFILE"], region_name="us-east-1"
            )
        else:
            self.session = boto3.Session()

        client_kwargs = {}
        local = True if config.get("DYNAMO_ENABLE_LOCAL", None) else False
        if local:
            client_kwargs["endpoint_url"] = "http://{}:{}".format(
                config["DYNAMO_LOCAL_HOST"], config["DYNAMO_LOCAL_PORT"]
            )

        self.conn = self.session.resource("dynamodb", **client_kwargs)
        if need_client:
            self.client = self.session.client("dynamodb", **client_kwargs)
        tsuffix = config.get("DYNAMO_TABLE_SUFFIX", None)
        if tsuffix:
            for table in TABLES:
                if not table["TableName"].endswith(tsuffix):
                    table["TableName"] = table["TableName"] + tsuffix
            for n, tn in TN_LOOKUP.items():
                if not TN_LOOKUP[n].endswith(tsuffix):
                    TN_LOOKUP[n] = tn + tsuffix

    def create_all(self):
        tables_name_list = [table.name for table in self.conn.tables.all()]
        for table in TABLES:
            if table["TableName"] not in tables_name_list:
                self._logger.info("Creating table {}".format(table["TableName"]))
                self.conn.create_table(**table)

    def destroy_all(self):
        for t in TABLES:
            table = self.conn.Table(t["TableName"])
            self._logger.info("Deleting table {}".format(t["TableName"]))
            table.delete()


ALL_REPORTS = "2xxx"


@dataclass
class PhotoModel:
    slack_file_id: str
    s3_url: str
    added_datetime: datetime


@dataclass
class ReportModel:
    allreports: str  # Constant for sorting
    create_ts: int  # Creation timestamp
    update_ts: int  # last update timestamp
    id: str  # readable unique id (primary key)

    create_datetime: datetime
    update_datetime: datetime
    status: str
    type: str  # Trail or Disturbance
    location: str  # e.g. trail name
    issues: str  # e.g. tree/obstruction - comma separated

    # ideally the real name
    reporter: str = None
    reporter_slack_handle: str = None
    reporter_slack_id: str = None

    cross_trail: str = None
    details: str = None

    # lat, lon - format ??
    gps: str = None

    # channel this report was filed on
    channel: str = None

    # kiosk
    kiosk_called: str = "no"
    kiosk_resolution: str = KIOSK_RESOLVED_UNKNOWN

    photos: List[PhotoModel] = field(default_factory=list)

    @classmethod
    def field_list(cls) -> set:
        """ Return set of all field names """
        return {f.name for f in fields(cls)}

    @classmethod
    def user_field_list(cls) -> set:
        """ Return set of all field names that are user/form settable """
        internal = {
            "id",
            "allreports",
            "create_datetime",
            "create_ts",
            "update_datetime",
            "update_ts",
            "photos",
            "type",
            "status",
            "reporter",
            "reporter_slack_handle",
            "reporter_slack_id",
        }
        return cls.field_list() - internal


def ddb2rm(item):
    """ Convert from item stored in dynamoDB to ReportModel """
    item["create_datetime"] = date_parser.parse(item["create_datetime"])
    item["update_datetime"] = date_parser.parse(item["update_datetime"])
    rm = ReportModel(**item)
    rm.photos = []
    for pitem in item["photos"]:
        pitem["added_datetime"] = date_parser.parse(pitem["added_datetime"])
        rm.photos.append(PhotoModel(**pitem))
    return rm


def rm2ddb(rm: ReportModel):
    """ Convert ReportModel to what dynamo wants """
    item = asdict(rm)
    item["create_datetime"] = item["create_datetime"].isoformat()
    item["update_datetime"] = item["update_datetime"].isoformat()
    item["photos"] = []
    for p in rm.photos:
        pitem = asdict(p)
        pitem["added_datetime"] = pitem["added_datetime"].isoformat()
        item["photos"].append(pitem)
    return item


def attr_to_display(r: ReportModel, attr):
    # Some model attributes are abbreviations
    # Always return a string to sorting can work.
    av = getattr(r, attr, None)
    if not av:
        return ""
    if attr == "location":
        av = TRAIL_VALUE_2_DESC.get(av)
    elif attr == "cross_trail":
        av = TRAIL_VALUE_2_DESC.get(av)
    elif attr == "issues":
        av = xlate_issues(av)
    return av


class Report:

    ACTIVE_FILTER = Attr("status").is_in([STATUS_REPORTED, STATUS_CONFIRMED])
    REAL_REPORT_FILTER = Attr("status").ne(STATUS_PLACEHOLDER)

    def __init__(self, config, ddb: DDB):
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._conn = ddb.conn

    def start_new(self):
        """ When creating a report using interactive messages and photos
        were uploaded at the beginning.
        """
        nr = self._initrm()
        table = self._conn.Table(TN_LOOKUP["reports"])
        rv = table.put_item(Item=rm2ddb(nr))
        self._logger.info("New report: rv {}".format(rv))
        return nr

    def _initrm(self):
        dt = datetime.now(tz.tzutc())
        dts = int(dt.timestamp() * 1000000)
        nr = ReportModel(
            allreports=ALL_REPORTS,
            id="{}-{}".format(str(dt.year)[2:], self._get_next_id(dt.year)),
            type="Unknown",
            status=STATUS_PLACEHOLDER,
            location="Unk",
            issues="Unk",
            create_datetime=dt,
            update_datetime=dt,
            create_ts=dts,
            update_ts=dts,
        )
        return nr

    @staticmethod
    def _fillin(nr, rtype, who, channel, dinfo):
        nr.type = rtype
        if channel:
            nr.channel = channel["id"]
        for f in nr.user_field_list():
            if f in dinfo:
                setattr(nr, f, dinfo[f])
        nr.reporter_slack_handle = who["name"]
        nr.reporter_slack_id = who["id"]
        nr.reporter = slack_api.user_to_name(who["id"])

    @staticmethod
    def _upd_time():
        dt = datetime.now(tz.tzutc())
        dts = int(dt.timestamp() * 1000000)
        return dt, dts

    def create(self, rtype, who, channel, dinfo):
        nr = self._initrm()
        nr.status = STATUS_REPORTED
        self._fillin(nr, rtype, who, channel, dinfo)

        table = self._conn.Table(TN_LOOKUP["reports"])
        rv = table.put_item(Item=rm2ddb(nr))
        self._logger.info("Created report {}: rv {}".format(nr.id, rv))
        return nr

    def complete(self, nr: ReportModel, rtype, who, channel, dinfo):
        # Finish up a report created via start_new
        nr.status = STATUS_REPORTED
        Report._fillin(nr, rtype, who, channel, dinfo)

        table = self._conn.Table(TN_LOOKUP["reports"])
        rv = table.put_item(Item=rm2ddb(nr))
        self._logger.info("Finished report {}: rv {}".format(nr.id, rv))
        return nr

    def fetch(self, limit=10, filters=None) -> List[ReportModel]:
        table = self._conn.Table(TN_LOOKUP["reports"])
        qopts = dict(
            KeyConditionExpression=Key("allreports").eq(ALL_REPORTS),
            IndexName="byupdate",
            ScanIndexForward=False,
        )
        if limit:
            qopts["Limit"] = limit
        if filters:
            qopts["FilterExpression"] = filters
        rv = table.query(**qopts)
        rm = []
        for i in rv["Items"]:
            rm.append(ddb2rm(i))
        limit -= len(rv["Items"])
        while "LastEvaluatedKey" in rv and limit > 0:
            qopts["ExclusiveStartKey"] = rv["LastEvaluatedKey"]
            qopts["Limit"] = limit
            rv = table.query(**qopts)
            for i in rv["Items"]:
                rm.append(ddb2rm(i))
            limit -= len(rv["Items"])
        return rm

    def _get(self, rid):
        """ Fetch based on unique id. """
        table = self._conn.Table(TN_LOOKUP["reports"])
        rv = table.query(KeyConditionExpression=Key("id").eq(rid))
        if len(rv["Items"]) != 1:
            if len(rv["Items"]) > 1:
                self._logger.error("Received multiple results for rid {}".format(rid))
            return None
        return ddb2rm(rv["Items"][0])

    def get(self, rid) -> ReportModel:
        return self._get(rid)

    def delete(self, rm: ReportModel, s3):
        for p in rm.photos:
            # remove from S3.
            s3.delete(p.s3_url, rm.id)

        table = self._conn.Table(TN_LOOKUP["reports"])
        table.delete_item(Key=dict(id=rm.id))

    def delete_photos(self, rm: ReportModel, s3):
        # delete all photos but leave report alone
        for p in rm.photos:
            # remove from S3.
            s3.delete(p.s3_url, rm.id)
        rm.photos = []
        table = self._conn.Table(TN_LOOKUP["reports"])
        rm.update_datetime, rm.update_ts = Report._upd_time()
        table.put_item(Item=rm2ddb(rm))

    def update(self, rm: ReportModel):
        """ Update report.
        We just update the entire record because - that's easier.
        """
        rm.update_datetime, rm.update_ts = Report._upd_time()
        table = self._conn.Table(TN_LOOKUP["reports"])
        table.put_item(Item=rm2ddb(rm))

    def add_photo(self, s3, finfo, rm: ReportModel):
        """ Add photo.
        We do this one photo at a time - we don't expect more than one or 2.
        We just update the entire record because - that's easier.
        """
        s3_finfo, lat, lon = image.add_photo(s3, finfo, rm.id)
        pm = PhotoModel(finfo["id"], s3_finfo["path"], datetime.now(tz.tzutc()))
        rm.photos.append(pm)
        if not rm.gps and lat and lon:
            rm.gps = "{},{}".format(lat, lon)
        table = self._conn.Table(TN_LOOKUP["reports"])
        rm.update_datetime, rm.update_ts = Report._upd_time()
        table.put_item(Item=rm2ddb(rm))

    def _get_next_id(self, year):
        table = self._conn.Table(TN_LOOKUP["idgen"])
        rv = table.update_item(
            Key=dict(year=str(year)),
            UpdateExpression="add yearid :o",
            ExpressionAttributeValues={":o": decimal.Decimal(1)},
            ReturnValues="UPDATED_NEW",
        )
        return rv["Attributes"]["yearid"]

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
        if re.match(r"(TR-|DR-)", rname, re.IGNORECASE):
            rname = rname[3:]
        return rname

    @classmethod
    def user_field_list(cls):
        return ReportModel.user_field_list()


class DDBCache:
    """
    Cache things.
    The record is simple - just ckey, cvalue
    Value should be a json serializable value
    """

    def __init__(self, config, ddb: DDB):
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._conn = ddb.conn

    def get(self, ckey):
        table = self._conn.Table(TN_LOOKUP["cache"])
        rv = table.query(KeyConditionExpression=Key("ckey").eq(ckey))
        if len(rv["Items"]) != 1:
            if len(rv["Items"]) > 1:
                self._logger.error("Received multiple results for ckey {}".format(ckey))
            return None
        return json.loads(rv["Items"][0]["cvalue"])

    def put(self, ckey, cvalue):
        table = self._conn.Table(TN_LOOKUP["cache"])
        item = {
            "ckey": ckey,
            "cvalue": json.dumps(cvalue),
            "update_datetime": datetime.now(tz.tzutc()).isoformat(),
        }
        self._logger.info(
            "Setting cache key {} to table {}".format(ckey, TN_LOOKUP["cache"])
        )
        table.put_item(Item=item)

    def delete(self, ckey):
        self._logger.info("Deleting ckey {} from cache".format(ckey))
        table = self._conn.Table(TN_LOOKUP["cache"])
        table.delete_item(Key={"ckey": ckey})
