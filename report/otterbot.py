# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Handle our chat-bot.
"""

import datetime
import logging

from flask import current_app

from dbmodel import (
    TRAIL_VALUE_2_DESC,
    TYPE_TRAIL,
    TYPE_DISTURBANCE,
    ISSUES_2_DESC,
    PhotoModel,
    xlate_issues,
)

from slack_api import get_file_info, post_message, post, send_update


logger = logging.getLogger(__name__)


def talk_to_me(event):
    """
    We were @app_mention'd.
    TODO: NLP

    Commands:
    "reports"
    "photo <report id>"  TBD

    """

    whatsup = event["text"].strip()

    tl = "Current Trail Reports"

    reports = current_app.report.fetch_all()
    if reports:
        for r in reports:
            gps = ""
            if r.gps:
                gps = "GPS {}".format(r.gps)
            dt = "<!date^{}^{{date_short_pretty}} {{time}}|{}>".format(
                int(
                    (
                            r.create_datetime - datetime.datetime(1970, 1, 1)
                    ).total_seconds()
                ),
                r.create_datetime,
            )
            tl += "\n{} {} {} reported {}: {} on {} {}".format(
                current_app.report.report_name(r),
                dt,
                r.reporter_slack_handle,
                "trail issue" if r.type == TYPE_TRAIL else "disturbance",
                xlate_issues(r.issues),
                TRAIL_VALUE_2_DESC[r.location],
                gps,
            )
    post_message(event["channel"], event["user"], tl)
