# Copyright 2019-2020 by J. Christopher Wagner (jwag). All rights reserved.

"""
Use dynamoDB for our at cache.
"""

from datetime import datetime
from dateutil import tz
import logging
import json

import boto3
from boto3.dynamodb.conditions import Key

TN_LOOKUP = {"cache": "cache"}

TABLES = [
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
                self._logger.error(f"Received multiple results for ckey {ckey}")
            return None
        return json.loads(rv["Items"][0]["cvalue"])

    def put(self, ckey, cvalue, only_if_changed=True):
        table = self._conn.Table(TN_LOOKUP["cache"])
        new_value = json.dumps(cvalue)
        if only_if_changed:
            rv = table.query(KeyConditionExpression=Key("ckey").eq(ckey))
            if len(rv["Items"]) == 1 and (rv["Items"][0]["cvalue"] == new_value):
                self._logger.info(f"Cache key {ckey} value unchanged")
                return

        item = {
            "ckey": ckey,
            "cvalue": new_value,
            "update_datetime": datetime.now(tz.tzutc()).isoformat(),
        }
        self._logger.info(
            "Setting cache key {} to table {} value {}".format(
                ckey, TN_LOOKUP["cache"], new_value
            )
        )
        table.put_item(Item=item)

    def delete(self, ckey):
        self._logger.info(f"Deleting ckey {ckey} from cache")
        table = self._conn.Table(TN_LOOKUP["cache"])
        table.delete_item(Key={"ckey": ckey})
