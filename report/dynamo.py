# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Use dynamoDB for our report store.

This has the advantage of:
1) at our usage it will be in the free tier
2) DDB has a VPC endpoint so our lambda can access it while running in the AWS
   lambda VPC - so we don't need a NAT gateway which is costing $$$

However - we are going to follow some worst-practices:

1) Use a constant PK/Hash Key - we will never have alot of records and we want to
   easily query for all recent reports (with particular status)
2) We want a user-friendly unique id - e.g. TR-19-1 (2019, first report). We create a
   secondary index to we can 'get_item' based on it.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
import decimal
import logging
from typing import List

import boto3
from boto3.dynamodb.conditions import Attr, Key
from dateutil import parser as date_parser

import image
import slack_api

from constants import (
    STATUS_PLACEHOLDER,
    STATUS_REPORTED,
    STATUS_CONFIRMED,
    TYPE_TRAIL,
    TYPE_DISTURBANCE,
)

TABLES = [
    {
        "TableName": "reports",
        "AttributeDefinitions": [
            dict(AttributeName="pk", AttributeType="S"),
            dict(AttributeName="update_ts", AttributeType="N"),
            dict(AttributeName="id", AttributeType="S"),
        ],
        "KeySchema": [
            dict(AttributeName="pk", KeyType="HASH"),
            dict(AttributeName="update_ts", KeyType="RANGE"),
        ],
        "GlobalSecondaryIndexes": [
            dict(
                IndexName="reportid",
                KeySchema=[dict(AttributeName="id", KeyType="HASH")],
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
]

PARTITION_HASH = "2xxx"


@dataclass
class PhotoModel:
    slack_file_id: str
    s3_url: str
    added_datetime: datetime


@dataclass
class ReportModel:
    pk: str  # Partition Key
    create_ts: int  # Creation timestamp
    update_ts: int  # last update timestamp
    id: str  # readable unique id...

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

    photos: List[PhotoModel] = field(default_factory=list)


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


class Report:
    def __init__(self, config):
        self._config = config
        self._logger = logging.getLogger(__name__)
        if config.get("AWS_PROFILE", None):
            self._session = boto3.Session(
                profile_name=config["AWS_PROFILE"], region_name="us-east-1"
            )
        else:
            self._session = boto3.Session()

        client_kwargs = {}
        local = True if config["DYNAMO_ENABLE_LOCAL"] else False
        if local:
            client_kwargs["endpoint_url"] = "http://{}:{}".format(
                config["DYNAMO_LOCAL_HOST"], config["DYNAMO_LOCAL_PORT"]
            )

        self._conn = self._session.resource("dynamodb", **client_kwargs)

    def start_new(self):
        """ When creating a report using interactive messages and photos
        were uploaded at the beginning.
        """
        dt = datetime.utcnow()
        dts = int(dt.timestamp() * 1000000)
        nr = ReportModel(
            pk=PARTITION_HASH,
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
        table = self._conn.Table("reports")
        rv = table.put_item(Item=rm2ddb(nr))
        self._logger.info("New report: rv {}".format(rv))
        return nr

    @staticmethod
    def _fillin(nr, rtype, who, channel, dinfo):
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

    """
    def create(self, rtype, who, channel, dinfo):
        nr = ReportModel(type=rtype, status=STATUS_REPORTED)
        self._fillin(nr, rtype, who, channel, dinfo)
        return self.get(nr.id)"""

    def complete(self, nr: ReportModel, rtype, who, channel, dinfo):
        # Finish up a report created via start_new
        nr.status = STATUS_REPORTED
        Report._fillin(nr, rtype, who, channel, dinfo)

        table = self._conn.Table("reports")
        rv = table.put_item(Item=rm2ddb(nr))
        self._logger.info("Finished report: rv {}".format(rv))
        return nr

    def fetch_all(self, limit=10, active=True) -> List[ReportModel]:
        table = self._conn.Table("reports")
        qopts = dict(
            KeyConditionExpression=Key("pk").eq("2xxx"), ScanIndexForward=False
        )
        if limit:
            qopts["Limit"] = limit
        if active:
            qopts["FilterExpression"] = Attr("status").is_in(
                [STATUS_REPORTED, STATUS_CONFIRMED]
            )
        rv = table.query(**qopts)
        rm = []
        for i in rv["Items"]:
            rm.append(ddb2rm(i))
        return rm

    def _get(self, rid):
        """ Fetch based on unique id. """
        table = self._conn.Table("reports")
        rv = table.query(KeyConditionExpression=Key("id").eq(rid), IndexName="reportid")
        if len(rv["Items"]) != 1:
            raise ValueError
        return ddb2rm(rv["Items"][0])

    def get(self, rid) -> ReportModel:
        return self._get(rid)

    def delete(self, rid, s3):
        rm = self._get(rid)
        for p in rm.photos:
            # remove from S3.
            s3.delete(p.s3_url, rid)

        table = self._conn.Table("reports")
        table.delete_item(Key=dict(pk=rm.pk, update_ts=rm.update_ts))

    def delete_photos(self, rid, s3):
        # delete all photos but leave report alone
        rm = self._get(rid)
        for p in rm.photos:
            # remove from S3.
            s3.delete(p.s3_url, rid)
        rm.photos = []
        table = self._conn.Table("reports")
        table.put_item(Item=rm2ddb(rm))

    def add_photo(self, s3, finfo, rm: ReportModel):
        """ Add photo.
        We do this one photo at a time - we don't expect more than one or 2.
        We just update the entire record because - that's easier.
        """
        s3_finfo, lat, lon = image.add_photo(s3, finfo, rm.id)
        pm = PhotoModel(finfo["id"], s3_finfo["path"], datetime.utcnow())
        rm.photos.append(pm)
        if not rm.gps and lat and lon:
            rm.gps = "{},{}".format(lat, lon)
        table = self._conn.Table("reports")
        table.put_item(Item=rm2ddb(rm))

    def create_all(self):
        tables_name_list = [table.name for table in self._conn.tables.all()]
        for table in TABLES:
            if table["TableName"] not in tables_name_list:
                self._logger.info("Creating table {}".format(table["TableName"]))
                self._conn.create_table(**table)

    def destroy_all(self):
        for t in TABLES:
            table = self._conn.Table(t["TableName"])
            self._logger.info("Deleting table {}".format(t["TableName"]))
            table.delete()

    def _get_next_id(self, year):
        table = self._conn.Table("idgen")
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
        if rname.startswith("TR-") or rname.startswith("DR-"):
            rname = rname[3:]
        return rname
