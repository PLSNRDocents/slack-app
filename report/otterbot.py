# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Handle our chat-bot.
"""

import datetime
import logging
import json
from random import randint
import re
import traceback

import asyncev
from constants import (
    STATUS_PLACEHOLDER,
    STATUS_CLOSED,
    TRAIL_VALUE_2_DESC,
    TYPE_DISTURBANCE,
    TYPE_TRAIL,
    xlate_issues,
)

import plweb
from quotes import QUOTES
from slack_api import get_file_info, delete_message, post_message, user_to_name


logger = logging.getLogger(__name__)

# U4DUR80RG - jwag
ADMIN_USER_IDS = ["U4DUR80RG"]


def talk_to_me(event_id, event):
    """
    We were @app_mention'd or DM'd.
    NOT IN APP context.
    TODO: NLP

    Commands:
    "rep(orts)"
    "<report_id> del(ete) | photo | close
    "new r(eport)"
    "at <where>"

    """

    try:
        app = asyncev.wapp
        with app.app_context():
            # remove all extraneous white space.
            whatsup = " ".join(event["text"].split()).split()
            # First word is the @mention
            logger.info(
                "Event id {} event_ts {} user {} text {}".format(
                    event_id, event["event_ts"], user_to_name(event["user"]), whatsup
                )
            )

            if len(whatsup) < 2:
                # This can happen if on iphone one 'attaches' an existing file
                # rather than use the 'images' icon.
                # We get 3 messages - a file_shared, and 2 'messages' - one of
                # which has an empty text but file info the other with the message
                # but no file (sigh).
                if "files" in event:
                    finfo = get_file_info(event["files"][0]["id"])
                    logger.warning("Empty text but file! {}".format(json.dumps(finfo)))
                    pme(
                        event,
                        "Sorry can't handle attachments via iphone,"
                        " use the 'images' button instead to send pictures.",
                    )
                    return {}

            if re.match(r"rep", whatsup[1], re.IGNORECASE):
                # Help people who type: report new or attach files
                if "files" in event or (
                    len(whatsup) > 2 and whatsup[2].startswith("new")
                ):
                    pme(
                        event,
                        "It appears you are trying to create a report -"
                        " use *@{}* new".format(app.config["BOT_NAME"]),
                    )
                # Options:
                # Whether to return reports with any status
                active_only = True
                if len(whatsup) > 2 and whatsup[2].startswith("any"):
                    active_only = False
                blocks = []
                blocks.append(divider_block())
                blocks.append(text_block("*Current Reports:*"))

                reports = app.report.fetch_all(active=active_only)
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
                        url = None
                        if len(r.photos) > 0:
                            url = (
                                "https://slack-files.com/TODJUU16J-FN7GS9OD8-c5fe8ef934"
                            )
                            url = (
                                "https://files.slack.com/files-pri/"
                                "T0DJUU16J-FNM7VV9FF/image_from_ios__2_.jpg"
                            )
                            url = "https://s3.us-east-1.amazonaws.com/{}/{}".format(
                                app.config["S3_BUCKET"], r.photos[0].s3_url
                            )
                        text = (
                            "[{}] {date} _{who}_ {status} {type}:"
                            "\n*{issue}* {verb} _{location}_ {gps}"
                            " {photo_link}".format(
                                app.report.id_to_name(r),
                                date=dt,
                                who=r.reporter
                                if r.reporter
                                else r.reporter_slack_handle,
                                status=r.status,
                                type="trail issue"
                                if r.type == TYPE_TRAIL
                                else "disturbance",
                                issue=xlate_issues(r.issues),
                                verb="on" if r.location.startswith("t") else "at",
                                location=TRAIL_VALUE_2_DESC.get(r.location, "??"),
                                gps=gps,
                                photo_link="(<{}|Big Picture>)".format(url)
                                if url
                                else "",
                            )
                        )
                        if url:
                            blocks.append(text_image(text, url))
                            logger.debug(
                                "Image block {}".format(
                                    json.dumps(text_image(text, url))
                                )
                            )
                        else:
                            blocks.append(text_block(text))
                post_message(event["channel"], event["user"], blocks)
                delete_message(event["channel"], event["ts"])
            elif re.match(r"new", whatsup[1], re.IGNORECASE):
                try:
                    what = whatsup[2]
                    if not what.startswith("r"):
                        raise ValueError()
                except (ValueError, IndexError):
                    pme(
                        event,
                        "Use: *@{}* new r(eport) to start a new report "
                        "(with attached photos).".format(app.config["BOT_NAME"]),
                    )
                    return
                # create new report to store photos
                nr = app.report.start_new()
                logger.info(
                    "User {}({}) starting new report {}".format(
                        event["user"], user_to_name(event["user"]), nr.id
                    )
                )

                # start an interactive message.
                # Seems safe enough to do this now - it takes a while to save files
                # and that confuses users.
                b = select_block(
                    nr.id,
                    "What type of report",
                    "Select an item",
                    [("Trail", TYPE_TRAIL), ("Disturbance", TYPE_DISTURBANCE)],
                )
                pme(event, [b])

                # grab photos
                if "files" in event:
                    for finfo in event["files"]:
                        logger.info(
                            "Adding file {} to {}".format(json.dumps(finfo), nr.id)
                        )
                        app.report.add_photo(app.s3, finfo, nr)

            elif re.match(r"(TR|DR|[12][0-9])", whatsup[1], re.IGNORECASE):
                # <report_id> del [photo]
                # <report_id> photo
                # <report_id> close
                rname = whatsup[1]

                usage = (
                    "Use: _report_id_ del(ete) - Delete report entirely\n"
                    "_report_id_ del(ete) photo(s) -"
                    " Delete all photos from report\n"
                    "_report_id_ photo - Add (attached) photos to report\n"
                    "_report_id_ close - close a trail report"
                )
                try:
                    action = whatsup[2]
                    rid = app.report.name_to_id(rname)
                    rm = app.report.get(rid)
                    if not rm:
                        pme(
                            event,
                            "Could not find report named {}\n{}".format(rname, usage),
                        )
                        return

                    if action.startswith("del"):
                        if event["user"] not in ADMIN_USER_IDS:
                            post_message(
                                event["channel"],
                                event["user"],
                                "You aren't authorized to delete reports",
                            )
                            return
                        if len(whatsup) == 3:
                            # delete entire report
                            just_photos = False
                        elif len(whatsup) == 4 and whatsup[3].startswith("photo"):
                            just_photos = True
                        else:
                            post_message(event["channel"], event["user"], usage)
                            return
                        logger.info(
                            "User {}({}) requesting to delete {} {}".format(
                                event["user"],
                                user_to_name(event["user"]),
                                "photos" if just_photos else "report",
                                rname,
                            )
                        )
                        if just_photos:
                            app.report.delete_photos(rm, app.s3)
                        else:
                            app.report.delete(rm, app.s3)
                        pme(
                            event,
                            "Deleted {} report {}".format(
                                "photos from" if just_photos else "", rname
                            ),
                        )
                    elif action.startswith("photo"):
                        if "files" not in event:
                            pme(
                                event, "No photos attached? for report {}".format(rname)
                            )
                            return
                        for finfo in event["files"]:
                            logger.info(
                                "Adding file to report {}: {}".format(
                                    rname, json.dumps(finfo)
                                )
                            )
                            app.report.add_photo(app.s3, finfo, rm)
                        pme(
                            event,
                            "Added {} photos to report {}".format(
                                len(event["files"]), rname
                            ),
                        )
                    elif action.startswith("close"):
                        # Can only close trail reports
                        if rm.type != TYPE_TRAIL:
                            pme(event, "Only Trail reports can be closed")
                        else:
                            if rm.status != STATUS_PLACEHOLDER:
                                rm.status = STATUS_CLOSED
                                app.report.update(rm)
                                pme(event, "Closed report {}".format(rname))
                    else:
                        pme(event, usage)
                except (ValueError, IndexError) as exc:
                    logger.warning(
                        "Error working on report {}: {}: {}".format(
                            rname, exc, traceback.format_exc()
                        )
                    )
                    pme(event, usage)
            elif re.match(r"at", whatsup[1], re.IGNORECASE):
                # default to all locations for 'today'.
                where = "all"
                today = datetime.date.today()
                which_day = today

                tomorrow = today + datetime.timedelta(days=1)
                want_tomorrow = False
                if len(whatsup) > 2:
                    # at <where> e.g. at info
                    # at <where> tom(orrow)
                    # at tom(orrow) - same as: at all tomorrow
                    # at delete <key>
                    if re.match(r"delete", whatsup[2], re.IGNORECASE):
                        if len(whatsup) != 4:
                            pme(event, "Usage: at delete key")
                            return
                        app.ddb_cache.delete(whatsup[3])
                        return

                    if re.match(r"tom", whatsup[2], re.IGNORECASE):
                        # handles shortcut at tom(orrow)
                        want_tomorrow = True
                    else:
                        where = whatsup[2]
                        if len(whatsup) > 3 and re.match(
                            r"tom", whatsup[3], re.IGNORECASE
                        ):
                            # tomorrow
                            want_tomorrow = True
                if want_tomorrow:
                    if today.month != tomorrow.month:
                        pme(event, "Tomorrow is looking hazy")
                        return
                    which_day = tomorrow

                ckey = "{}:{}".format(which_day.strftime("%Y%m%d"), where)
                atinfo = app.ddb_cache.get(ckey)
                if not atinfo:
                    pme(
                        event,
                        [
                            text_block(
                                "I am going to need to dive deep to find that"
                                " out for you."
                            )
                        ],
                    )
                    atinfo = plweb.whoat(which_day.strftime("%Y%m%d"), where)
                    app.ddb_cache.put(ckey, atinfo)
                blocks = []
                blocks.append(divider_block())
                blocks.append(text_block(which_day.strftime("%b %d %Y")))
                for loc, what in atinfo.items():
                    if what:
                        t = "*{}:*".format(loc)
                        for i in what:
                            t += "\n_{}_: {}".format(i["time"], ", ".join(i["who"]))
                            if "title" in i:
                                t += " - {}".format(i["title"])
                        blocks.append(text_block(t))

                delete_message(event["channel"], event["ts"])
                pme(event, blocks)
            else:
                blocks = [
                    text_block(
                        "Sorry didn't hear you - I was sleeping.\nYou can ask for:\n"
                        "*reports* - Show most recent trail/disturbance reports.\n"
                        "*new* - Create a report with optional photos.\n"
                        "_report_id_ - Modify/Delete/Add photos"
                        " to an existing report.\n"
                        "*at* - who's doing what at the Reserve today.\n"
                    )
                ]

                blocks.append(
                    text_image(
                        QUOTES[randint(0, len(QUOTES) - 1)].strip(),
                        "https://media.giphy.com/media/drxyCDMT7kkvu1FWNZ/giphy.gif",
                    )
                )
                delete_message(event["channel"], event["ts"])
                pme(event, blocks)
    except Exception as exc:
        logger.error(
            "Exception in talk_to_me text: {} {}:{}".format(
                event["text"], exc, traceback.format_exc()
            )
        )
    # from zappa docs.
    return {}


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


def pme(event, text):
    post_message(event["channel"], event["user"], text)
