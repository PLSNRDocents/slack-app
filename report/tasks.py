# Copyright 2019-2020 by J. Christopher Wagner (jwag). All rights reserved.

"""
Scheduled tasks invoke via zappa

Locally - python -c "import tasks; tasks.xxx"

"""

import datetime
from dateutil import tz
import importlib
import logging
import os

from constants import (
    LOG_FORMAT,
    CKEY_OTHER_ISSUES,
    CKEY_PLACES,
    CKEY_WILDLIFE_ISSUES,
    DATE_FMT,
)
from drupal_api import DrupalApi
import dynamo
import plweb
import report_drupal
from scheduled_activity import ScheduledActivity
import utils


logging.basicConfig(format=LOG_FORMAT, datefmt=DATE_FMT, level=logging.INFO)
logger = logging.getLogger(__name__)


def _setup():
    # grab config
    config = {}
    mode = os.environ["PLSNRENV"]
    logger.info("task setup: mode {}".format(mode))

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
    """
    This is run as a 'cron' task via zappa.
    Remember that lambdas are stateless - so we have to actually store this
    stuff in a DB (which is fast enough < 3 seconds) so we can respond to slack
    API calls before trigger_ids etc time out.
    """
    config = _setup()
    logger.info("prime_cache: init db")

    try:
        site = DrupalApi(
            config["PLSNR_USERNAME"],
            config["PLSNR_PASSWORD"],
            "{}/plsnr1933api".format(config["PLSNR_HOST"]),
            config["SSL_VERIFY"],
        )
        ddb = dynamo.DDB(config)
        ddb_cache = dynamo.DDBCache(config, ddb)
        plwebsite = plweb.Plweb(config)
        report = report_drupal.Report(config, site)
        sa = ScheduledActivity(config, site)

        today = datetime.datetime.now(tz.tzutc())
        which_days = [
            today,
            today + datetime.timedelta(days=1),
        ]

        where = "all"
        for day in which_days:
            lday, ckey = utils.at_cache_helper(day, where)
            atinfo = plwebsite.whoat(lday.strftime("%Y%m%d"), where)
            atinfo.update(sa.whoat(lday.strftime("%Y%m%d"), where))
            ddb_cache.put(ckey, atinfo)

        logger.info("prime_cache: reports")
        ddb_cache.put(CKEY_PLACES, report.get_places_list())
        ddb_cache.put(CKEY_WILDLIFE_ISSUES, report.get_wildlife_issue_list())
        ddb_cache.put(CKEY_OTHER_ISSUES, report.get_other_issue_list())
    except Exception as exc:
        logger.error("Task failed: {}".format(exc))


def backup():
    config = _setup()
    logger.info("backup: init db")
    ddb = dynamo.DDB(config, need_client=True)

    dt = datetime.datetime.now(tz.tzutc()).strftime("%Y%m%d%H%M%S")
    for table in dynamo.TN_LOOKUP.values():
        rv = ddb.client.create_backup(TableName=table, BackupName=table + dt)
        logger.info("Backup response for table {}: {}".format(table, rv))
