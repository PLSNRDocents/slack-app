# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Scheduled tasks invoke via zappa

Locally - python -c "import tasks; tasks.xxx"

"""

import datetime
import importlib
import logging
import os

from constants import LOG_FORMAT, DATE_FMT
import dynamo
import plweb


logging.basicConfig(format=LOG_FORMAT, datefmt=DATE_FMT, level=logging.INFO)
logger = logging.getLogger(__name__)


def _setup():
    # grab config
    config = {}
    mode = os.environ["PLSNRENV"]
    logger.info("create_app: mode {}".format(mode))

    settings = getattr(importlib.import_module("settings"), mode + "Settings")
    for key in dir(settings):
        if key.isupper():
            config[key] = getattr(settings, key)

    # let environ overwrite settings
    for rc in config:
        if rc in os.environ and (os.environ[rc] != config[rc]):
            logger.warning("Config variable {} overwritten by environment".format(rc))
            config[rc] = os.environ[rc]
    return config


def prime_cache():
    config = _setup()
    logger.info("prime_cache: init db")
    ddb = dynamo.DDB(config)
    ddb_cache = dynamo.DDBCache(config, ddb)

    # plweb actually can only handle current month.
    today = datetime.date.today()
    which_days = [today.strftime("%Y%m%d")]
    tomorrow = today + datetime.timedelta(days=1)
    if tomorrow.month == today.month:
        which_days.append(tomorrow.strftime("%Y%m%d"))

    where = "all"
    for day in which_days:
        ckey = "{}:{}".format(day, where)
        atinfo = plweb.whoat(day, where)
        ddb_cache.put(ckey, atinfo)


def backup():
    config = _setup()
    logger.info("backup: init db")
    ddb = dynamo.DDB(config, need_client=True)

    dt = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    for table in dynamo.TN_LOOKUP.values():
        rv = ddb.client.create_backup(TableName=table, BackupName=table + dt)
        logger.info("Backup response for table {}: {}".format(table, rv))
