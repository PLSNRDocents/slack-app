# Copyright 2019-2024 by J. Christopher Wagner (jwag). All rights reserved.

"""
Use dynamoDB for our at cache.
"""

from datetime import datetime
from dateutil import tz
import logging
import json

import boto3

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
        tables_name_list = self.client.list_tables()["TableNames"]
        for table in TABLES:
            if table["TableName"] not in tables_name_list:
                self._logger.info(
                    f" APP: create_all: Creating table {table['TableName']}"
                )
                self.client.create_table(**table)

    def destroy_all(self):
        for t in TABLES:
            self._logger.info(f"APP: destroy_all: Deleting table {t['TableName']}")
            self.client.delete_table(t["TableName"])


class DDBCache:
    """
    Cache things.
    The record is simple - just ckey, cvalue
    Value should be a json serializable value
    """

    def __init__(self, config, ddb: DDB):
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._client = ddb.client

    def get(self, ckey):
        cn = TN_LOOKUP["cache"]
        rv = self._client.query(
            TableName=cn,
            KeyConditionExpression="ckey = :ckey",
            ExpressionAttributeValues={":ckey": {"S": ckey}},
        )
        if len(rv["Items"]) != 1:
            if len(rv["Items"]) > 1:
                self._logger.error(
                    f"APP: get: Received multiple results for ckey {ckey}"
                )
            return None
        cvalue = json.loads(rv["Items"][0]["cvalue"]["S"])
        if isinstance(cvalue, dict):
            self._logger.debug(f"APP: get: {cvalue.items()}")
            entries_per_title = {t: len(v) for t, v in cvalue.items()}
            self._logger.info(f"APP: get: atinfo counts:{entries_per_title}")
        return cvalue

    def put(self, ckey, cvalue, only_if_changed=True):
        cn = TN_LOOKUP["cache"]
        new_value = json.dumps(cvalue)
        if only_if_changed:
            rv = self._client.query(
                TableName=cn,
                KeyConditionExpression="ckey = :ckey",
                ExpressionAttributeValues={":ckey": {"S": ckey}},
            )
            if len(rv["Items"]) == 1 and (rv["Items"][0]["cvalue"]["S"] == new_value):
                self._logger.info(f"APP: put: Cache key {ckey} value unchanged")
                return

        item = {
            "ckey": {"S": ckey},
            "cvalue": {"S": new_value},
            "update_datetime": {"S": datetime.now(tz.tzutc()).isoformat()},
        }
        self._logger.debug(
            "APP: put: Setting cache key {} to table {} value {}".format(
                ckey, cn, new_value
            )
        )
        if isinstance(cvalue, dict):
            entries_per_title = {t: len(v) for t, v in cvalue.items()}
            self._logger.info(f"APP: put: counts:{entries_per_title}")
        self._client.put_item(TableName=cn, Item=item)

    def delete(self, ckey):
        self._logger.info(f"APP: delete: Deleting ckey {ckey} from cache")
        self._client.delete_item(
            TableName=TN_LOOKUP["cache"], Key={"ckey": {"S": ckey}}
        )
