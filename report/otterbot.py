# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Handle our chat-bot.
"""

import datetime
import logging
import json
from random import randint

from flask import Flask

from dbmodel import TRAIL_VALUE_2_DESC, TYPE_DISTURBANCE, TYPE_TRAIL, xlate_issues

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
    "report(s)"
    "photo <report id>"
    "new r(eport)"
    "at info"

    """

    with app.app_context():
        # remove all extraneous white space.
        whatsup = " ".join(event["text"].split()).split()
        # First word is the @mention

        if whatsup[1].startswith("rep"):
            blocks = []
            blocks.append(text_block("*Current Trail Reports:*"))

            reports = app.report.fetch_all()
            if reports:
                for r in reports:
                    blocks.append(divider_block())
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
                    text = "[{}] {} _{}_ reported {}:\n*{}* on _{}_ {}".format(
                        app.report.id_to_name(r),
                        dt,
                        r.reporter if r.reporter else r.reporter_slack_handle,
                        "trail issue" if r.type == TYPE_TRAIL else "disturbance",
                        xlate_issues(r.issues),
                        TRAIL_VALUE_2_DESC[r.location],
                        gps,
                    )
                    if len(r.photos) > 0:
                        # blocks.append(text_block(text))
                        url = "https://slack-files.com/TODJUU16J-FN7GS9OD8-c5fe8ef934"
                        url = (
                            "https://files.slack.com/files-pri/"
                            "T0DJUU16J-FNM7VV9FF/image_from_ios__2_.jpg"
                        )
                        url = "https://s3.us-east-1.amazonaws.com/{}/{}".format(
                            app.config["S3_BUCKET"], r.photos[0].s3_url
                        )
                        blocks.append(text_image(text, url))
                        logger.debug(
                            "Image block {}".format(json.dumps(text_image(text, url)))
                        )
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
                    logger.info("Adding file {}".format(json.dumps(finfo)))
                    report.add_photo(app, finfo, rm)
                post_message(
                    event["channel"],
                    event["user"],
                    "Added {} photos to report {}".format(len(event["files"]), rname),
                )
            except (ValueError, IndexError) as exc:
                logging.error(
                    "Error handling photo for report {}: {}".format(rm.id, exc)
                )
                post_message(
                    event["channel"],
                    event["user"],
                    "Use: *@{}* photo _report-id_ to add attached photo"
                    " to an existing report".format(app.config["BOT_NAME"]),
                )
        elif whatsup[1] == "new":
            try:
                what = whatsup[2]
                if not what.startswith("r"):
                    raise ValueError()
            except (ValueError, IndexError):
                post_message(
                    event["channel"],
                    event["user"],
                    "Use: *@{}* new r(eport) to start a"
                    " new report (with photos).".format(app.config["BOT_NAME"]),
                )
                return
            # create new report to store photos
            nr = app.report.start_new()
            logger.info("Starting new report {}".format(nr.id))

            # start an interactive message.
            # Seems safe enough to do this now - it takes a while to save files
            # and that confuses users.
            b = select_block(
                nr.id,
                "What type of report",
                "Select an item",
                [("Trail", TYPE_TRAIL), ("Disturbance", TYPE_DISTURBANCE)],
            )
            post_message(event["channel"], event["user"], [b])

            # grab photos
            if "files" in event:
                for finfo in event["files"]:
                    logger.info("Adding file {} to {}".format(json.dumps(finfo), nr.id))
                    report.add_photo(app, finfo, nr)

        elif whatsup[1].startswith("del"):
            # TODO authz
            # We handle delete report_id
            # and delete report_id photos
            if len(whatsup) == 3:
                # delete entire report
                just_photos = False
            elif len(whatsup) == 4 and whatsup[3].startswith("photo"):
                just_photos = True
            else:
                post_message(
                    event["channel"],
                    event["user"],
                    "Use: *@{}* delete _report_id_ OR"
                    " {} delete _report_id_ photos".format(
                        app.config["BOT_NAME"], app.config["BOT_NAME"]
                    ),
                )
                return

            rname = whatsup[2]
            logger.info(
                "User {} requesting to delete {} {}".format(
                    event["user"], "photos" if just_photos else "report", rname
                )
            )
            try:
                rid = app.report.name_to_id(rname)
                if just_photos:
                    app.report.delete_photos(rid)
                else:
                    app.report.delete(rid)
                post_message(
                    event["channel"],
                    event["user"],
                    "Deleted {} report {}".format(
                        "photos from" if just_photos else "", rname
                    ),
                )
            except ValueError:
                post_message(
                    event["channel"],
                    event["user"],
                    "Use: *@{}* delete _report_id_ OR"
                    " {} delete _report_id_ photos".format(
                        app.config["BOT_NAME"], app.config["BOT_NAME"]
                    ),
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
            atinfo = plweb.whoat(datetime.date.today().strftime("%Y%m%d"), where)
            blocks = []
            for loc, what in atinfo.items():
                if what:
                    t = "*{}:*".format(loc)
                    for i in what:
                        t += "\n_{}_: {}".format(i["time"], ", ".join(i["who"]))
                        if "title" in i:
                            t += " - {}".format(i["title"])
                    blocks.append(text_block(t))
            post_message(event["channel"], event["user"], blocks)
        else:
            blocks = [
                text_block(
                    "Sorry didn't hear you - I was sleeping.\nYou can ask for:\n"
                    "*reports* - Show most recent trail/disturbance reports.\n"
                    "*new* - Create a report with photos.\n"
                    "*photo* - Add photos to an existing report.\n"
                    "*at* - who's doing what at the Reserve today.\n"
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


def select_block(block_id, text, place_text, options: list):
    # Create a select block.
    # options should be a list of tuples (text, value)
    ops = []
    for o in options:
        ops.append({"text": {"type": "plain_text", "text": o[0]}, "value": o[1]})
    b = {
        "type": "section",
        "block_id": str(block_id),
        "text": {"type": "mrkdwn", "text": text},
        "accessory": {
            "action_id": "123",
            "type": "static_select",
            "placeholder": {"type": "plain_text", "text": place_text},
            "options": ops,
        },
    }
    return b


def action_block(block_id, place_text, options: list):
    # Create a actions select block.
    # options should be a list of tuples (text, value)
    ops = []
    for o in options:
        ops.append({"text": {"type": "plain_text", "text": o[0]}, "value": o[1]})
    b = {
        "type": "actions",
        "block_id": str(block_id),
        "elements": [
            {
                "action_id": "456",
                "type": "static_select",
                "placeholder": {"type": "plain_text", "text": place_text},
                "options": ops,
            }
        ],
    }
    return b


def divider_block():
    return {"type": "divider"}
