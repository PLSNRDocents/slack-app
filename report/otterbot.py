# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Handle our chat-bot.
"""

import datetime
import logging
from random import randint

from flask import Flask

from dbmodel import (
    TRAIL_VALUE_2_DESC,
    TYPE_TRAIL,
    TYPE_DISTURBANCE,
    ISSUES_2_DESC,
    xlate_issues,
)

import plweb
from quotes import QUOTES
import report
from slack_api import post_message


logger = logging.getLogger(__name__)


def talk_to_me(event, app: Flask):
    """
    We were @app_mention'd.
    NOT IN APP context.
    TODO: NLP

    Commands:
    "reports"
    "photo <report id>"
    "at info"

    """

    with app.app_context():
        # remove all extraneous white space.
        whatsup = " ".join(event["text"].split()).split()
        # First word is the @mention

        if whatsup[1].startswith("report"):
            blocks = []
            blocks.append(text_block("*Current Trail Reports*"))

            reports = app.report.fetch_all()
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
                    text = "[{}] {} {} reported {}:\n{} on {} {}".format(
                        app.report.id_to_name(r),
                        dt,
                        r.reporter_slack_handle,
                        "trail issue" if r.type == TYPE_TRAIL else "disturbance",
                        xlate_issues(r.issues),
                        TRAIL_VALUE_2_DESC[r.location],
                        gps,
                    )
                    if len(r.photos) > 0:
                        # blocks.append(text_block(text))
                        url = "https://photos.smugmug.com/Public/Point-Lobos/i-66GZC52/0/c07785d6/X2/DSC_2691-X2.jpg"
                        url = r.photos[0].s3_url
                        url = "https://slack-files.com/TODJUU16J-FN7GS9OD8-c5fe8ef934"
                        url = "https://pldocents.slack.com/files/U4DUR80RG/FNL492VJQ/image_from_ios__2_.jpg"
                        blocks.append(text_image(text, url))

                    else:
                        blocks.append(text_block(text))
            post_message(event["channel"], event["user"], blocks)
        elif whatsup[1].startswith("photo"):
            try:
                rname = whatsup[2]
                rid = app.report.name_to_id(rname)
                rm = app.report.get(rid)
                if not rm:
                    post_message(
                        event["channel"],
                        event["user"],
                        "Could not find report named {}".format(rname),
                    )
                    return
                if "files" not in event:
                    post_message(
                        event["channel"],
                        event["user"],
                        "No photos attached?".format(rname),
                    )
                    return
                for finfo in event["files"]:
                    logger.info("Adding file {}".format(finfo))
                    report.add_photo(app, finfo, rm)
                post_message(
                    event["channel"],
                    event["user"],
                    "Added {} photos to report {}".format(len(event["files"]), rname),
                )
            except (ValueError, IndexError):
                post_message(
                    event["channel"],
                    event["user"],
                    "Use 'photo report_id' to add a photo to an existing report",
                )
        elif whatsup[1] == "at":
            where = None
            if len(whatsup) > 2:
                where = whatsup[2]
            post_message(
                event["channel"],
                event["user"],
                [text_block("Give me a sec to look this up.")],
            )
            atinfo = plweb.whoat(where)
            blocks = []
            for loc, what in atinfo.items():
                t = "*{}:*".format(loc)
                for i in what:
                    t += "\n_{}_: {}".format(i["time"], ", ".join(i["who"]))
                blocks.append(text_block(t))
            post_message(event["channel"], event["user"], blocks)
        else:
            blocks = [
                text_block(
                    "Hmm I don't understand. You can ask for"
                    " 'reports' or 'photo' or 'at'."
                )
            ]

            blocks.append(
                text_image(
                    QUOTES[randint(0, len(QUOTES) - 1)].strip(),
                    "https://media.giphy.com/media/drxyCDMT7kkvu1FWNZ/giphy.gif",
                )
            )
            post_message(event["channel"], event["user"], blocks)


def text_block(text):
    b = {"type": "section", "text": {"type": "mrkdwn", "text": text}}
    return b


def text_image(text, url):
    b = {
        "type": "section",
        "text": {"type": "mrkdwn", "text": text},
        "accessory": {"type": "image", "image_url": url, "alt_text": "image"},
    }
    return b
