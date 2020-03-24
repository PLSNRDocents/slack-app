# Copyright 2019-2020 by J. Christopher Wagner (jwag). All rights reserved.

"""
Handle our chat-bot.
"""

import datetime
from dateutil import tz
import logging
import json
from random import randint
import re
import traceback

import asyncev
from constants import TYPE_TRAIL

from quotes import QUOTES
from slack_api import (
    get_file_info,
    delete_message,
    post_ephemeral_message,
    user_to_name,
)
import utils
from utils import text_block, divider_block, text_image


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
    "<report_id> photo
    "at <where>"

    """

    try:
        app = asyncev.wapp
        with app.app_context():
            # remove all extraneous white space.
            whatsup = " ".join(event["text"].split()).split()
            # First word is the @mention
            logger.info(
                "Event id {} event_ts {} channel {} user {}({}) text {}".format(
                    event_id,
                    event["event_ts"],
                    event.get("channel", "??"),
                    user_to_name(event["user"]),
                    event["user"],
                    whatsup,
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
                        " use home tab to create reports",
                    )

                blocks = []
                blocks.append(divider_block())
                blocks.append(text_block("*Current Reports:*"))

                reports = app.report.fetch()
                if reports:
                    for r in reports:
                        blocks.append(divider_block())
                        dt = "<!date^{}^{{date_short_pretty}} {{time}}|{}>".format(
                            int(r.create_datetime.timestamp()), r.create_datetime
                        )
                        issues = ""
                        if r.wildlife_issues:
                            issues += "*{}*".format(r.wildlife_issues)
                        if r.other_issues:
                            if issues:
                                issues += " and "
                            issues += "*{}*".format(r.other_issues)
                        text = (
                            "{date} _{who}_ reported:"
                            "\n{issues} {verb} _{location}_".format(
                                date=dt,
                                who=r.reporter,
                                issues=issues,
                                verb="on" if "Trail" in r.location else "at",
                                location=r.location,
                            )
                        )
                        blocks.append(text_block(text))
                post_ephemeral_message(event["channel"], event["user"], blocks)
                delete_message(event["channel"], event["ts"])

            elif re.match(r"(TR|DR|[12][0-9])", whatsup[1], re.IGNORECASE):
                # <report_id> photo
                pme(event, "Not supported yet")
                return
                """
                rname = whatsup[1]
                usage = "Use: _report_id_ photo - Add (attached) photos to report\n"
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

                    if action.startswith("photo"):
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
                            app.report.add_photo(finfo, rm)
                        pme(
                            event,
                            "Added {} photos to report {}".format(
                                len(event["files"]), rname
                            ),
                        )
                    else:
                        pme(event, usage)
                except (ValueError, IndexError) as exc:
                    logger.warning(
                        "Error working on report {}: {}: {}".format(
                            rname, exc, traceback.format_exc()
                        )
                    )
                    pme(event, usage)
                """
            elif re.match(r"at", whatsup[1], re.IGNORECASE):
                # default to all locations for 'today'.
                where = "all"

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

                today = datetime.datetime.now(tz.tzutc())
                which_day = today
                if want_tomorrow:
                    which_day = today + datetime.timedelta(days=1)

                lday, ckey = utils.at_cache_helper(which_day, where)
                logger.info(
                    "Looking for at info for Pacific TZ: {} Key: {}".format(
                        lday.isoformat(), ckey
                    )
                )
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
                    atinfo = app.plweb.whoat(lday.strftime("%Y%m%d"), where)
                    app.ddb_cache.put(ckey, atinfo)
                blocks = utils.atinfo_to_blocks(atinfo, lday)

                delete_message(event["channel"], event["ts"])
                pme(event, blocks)
            elif re.match(r"whoswho", whatsup[1], re.IGNORECASE):
                whoswho, unmatched = app.report.whoswho()
            else:
                blocks = [
                    text_block(
                        "*Sorry didn't hear you - I was sleeping.*\nYou can ask for:\n"
                        "*reports* - Show most recent trail/disturbance reports.\n"
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


def pme(event, text):
    post_ephemeral_message(event["channel"], event["user"], text)
