# Copyright 2019-2024 by J. Christopher Wagner (jwag). All rights reserved.

"""
Scheduled tasks invoked via zappa

Locally - python -c "import tasks; tasks.xxx"

"""

import argparse
import datetime
from dateutil import parser, tz
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
import report_drupal
from scheduled_activity import ScheduledActivity
import utils


logging.basicConfig(format=LOG_FORMAT, datefmt=DATE_FMT, level=logging.INFO)
logger = logging.getLogger(__name__)


def _setup():
    # grab config
    config = {}
    mode = os.environ["PLSNRENV"]
    logger.info(f"task setup: mode {mode}")

    settings = getattr(importlib.import_module("settings"), mode + "Settings")
    for key in dir(settings):
        if key.isupper():
            config[key] = getattr(settings, key)

    # let environ overwrite settings
    for rc in config:
        if rc in os.environ and (os.environ[rc] != config[rc]):
            logger.warning(f"Config variable {rc} overwritten by environment")
            config[rc] = os.environ[rc]
    return config


def prime_cache_internal(config, ddb_cache, which_days):
    site = DrupalApi(
        config["PLSNR_USERNAME"],
        config["PLSNR_PASSWORD"],
        "{}/plsnr1933api".format(config["PLSNR_HOST"]),
        config["SSL_VERIFY"],
    )
    report = report_drupal.Report(config, site)
    sa = ScheduledActivity(config, site)

    where = "all"
    for day in which_days:
        lday, ckey = utils.at_cache_helper(day, where)
        atinfo = sa.whoat(lday.strftime("%Y%m%d"), where)
        ddb_cache.put(ckey, atinfo)

    logger.info("prime_cache: reports")
    ddb_cache.put(CKEY_PLACES, report.get_places_list())
    ddb_cache.put(CKEY_WILDLIFE_ISSUES, report.get_wildlife_issue_list())
    ddb_cache.put(CKEY_OTHER_ISSUES, report.get_other_issue_list())


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
        ddb = dynamo.DDB(config)
        ddb_cache = dynamo.DDBCache(config, ddb)
        today = datetime.datetime.now(tz.tzutc())
        which_days = [
            today,
            today + datetime.timedelta(days=1),
        ]
        prime_cache_internal(config, ddb_cache, which_days)
    except Exception as exc:
        logger.error(f"Task failed: {exc}", exc_info=True)


def backup():
    config = _setup()
    logger.info("backup: init db")
    ddb = dynamo.DDB(config, need_client=True)

    dt = datetime.datetime.now(tz.tzutc()).strftime("%Y%m%d%H%M%S")
    for table in dynamo.TN_LOOKUP.values():
        rv = ddb.client.create_backup(TableName=table, BackupName=table + dt)
        logger.info(f"Backup response for table {table}: {rv}")


def parseargs():
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--date", help="example: 01/23/2019.")
    return arg_parser.parse_args()


if __name__ == "__main__":
    _args = parseargs()
    config = _setup()
    gddb = dynamo.DDB(config)
    gddb.create_all()
    gddb_cache = dynamo.DDBCache(config, gddb)

    if _args.date:
        fday = parser.parse(_args.date)
    else:
        fday = datetime.datetime.now(tz.tzutc())

    which_days = [
        fday,
        fday + datetime.timedelta(days=1),
    ]
    prime_cache_internal(config, gddb_cache, which_days)

    for day in which_days:
        lday, ckey = utils.at_cache_helper(day, "all")
        atinfo = gddb_cache.get(ckey)
        blocks = utils.atinfo_to_blocks(atinfo, lday)
        print(blocks)
