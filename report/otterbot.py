# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

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
from slack_api import (
    get,
    get_file_info,
    delete_message,
    post_ephemeral_message,
    user_to_name,
)
import utils
from utils import text_block, divider_block, text_image, buttons_block


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
                        " use new report",
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
                            dlat, dlng = convert_gps(r.gps)
                            if dlat and dlng:
                                gps = (
                                    "<https://www.google.com/maps/search/?"
                                    "api=1&query={},{}|GPS {}>".format(
                                        dlat, dlng, r.gps
                                    )
                                )
                            else:
                                gps = "GPS {}".format(r.gps)
                        dt = "<!date^{}^{{date_short_pretty}} {{time}}|{}>".format(
                            int(r.create_datetime.timestamp()), r.create_datetime
                        )
                        kiosk = ""
                        if r.kiosk_called != "no":
                            kiosk = "\nKiosk called - resolved: _{}_".format(
                                r.kiosk_resolution
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
                            "  {photo_link}{kiosk}".format(
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
                                kiosk=kiosk,
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
                post_ephemeral_message(event["channel"], event["user"], blocks)
                delete_message(event["channel"], event["ts"])
            elif re.match(r"new", whatsup[1], re.IGNORECASE):
                try:
                    what = whatsup[2]
                    if not what.startswith("rep"):
                        raise ValueError()
                except (ValueError, IndexError):
                    pme(
                        event,
                        "Use: new rep(ort) to start a new report "
                        "(with optional attached photos).",
                    )
                    return
                # create new report to store photos
                nr = app.report.start_new()
                logger.info(
                    "User {}({}) starting new report {}".format(
                        user_to_name(event["user"]), event["user"], nr.id
                    )
                )

                # start an interactive message.
                # Seems safe enough to do this now - it takes a while to save files
                # and that confuses users.
                b = []
                b.append(text_block("*Please select report type*"))
                b.append(divider_block())
                b.append(
                    buttons_block(
                        "NEWREP:" + nr.id,
                        [("Trail", TYPE_TRAIL), ("Disturbance", TYPE_DISTURBANCE)],
                    )
                )
                # debugging why I cant delete other messages.
                convos = get(
                    "conversations.list",
                    params={"types": "public_channel," " private_channel, mpim, im"},
                )
                for c in convos["channels"]:
                    if c["id"] == event["channel"]:
                        logger.info("Channel info: {}".format(json.dumps(c, indent=4)))
                delete_message(event["channel"], event["ts"])

                pme(event, b)

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
                            post_ephemeral_message(
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
                            post_ephemeral_message(
                                event["channel"], event["user"], usage
                            )
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
                    atinfo = plweb.whoat(lday.strftime("%Y%m%d"), where)
                    app.ddb_cache.put(ckey, atinfo)
                blocks = utils.atinfo_to_blocks(atinfo, lday)

                delete_message(event["channel"], event["ts"])
                pme(event, blocks)
            else:
                blocks = [
                    text_block(
                        "*Sorry didn't hear you - I was sleeping.*\nYou can ask for:\n"
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


def pme(event, text):
    post_ephemeral_message(event["channel"], event["user"], text)


def convert_gps(gps):
    """ Parse iphone compass app GPS coordinates: '36°33′0″ N  121°55′28″ W'
    """
    # 2 spaces between lat/lng
    try:
        lat, lng = gps.split("  ")
        dlat = dms_to_dd(lat)
        dlng = dms_to_dd(lng)
        return dlat, dlng
    except Exception:
        return None, None


def dms_to_dd(coords):
    """ iphone uses some funky punctuation """
    coords = " ".join(coords.split())
    deg, minutes, seconds, direction = re.split(
        "[°'\"\N{PRIME}\N{DOUBLE PRIME}]", coords
    )
    return (float(deg) + float(minutes) / 60 + float(seconds) / (60 * 60)) * (
        -1 if direction.strip() in ["W", "S"] else 1
    )
