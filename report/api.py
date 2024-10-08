# Copyright 2019-2022 by J. Christopher Wagner (jwag). All rights reserved.

from dateutil import tz
import datetime
import logging
import json

from flask import Blueprint, abort, current_app, jsonify, request

import asyncev
from asyncev import run_async
import exc
from home import handle_home
from otterbot import talk_to_me
from report import (
    open_disturbance_report_modal,
    open_trail_report_modal,
    handle_report_cancel_modal,
    handle_report_submit_modal,
    handle_report_submit_validation,
)
from slack_api import get_file_info, get_bot_user_id, post
import utils

api = Blueprint("api", __name__, url_prefix="/")
logger = logging.getLogger("api")


@api.route("/report", methods=["GET", "POST"])
def top():
    # This handles the /report command
    if not current_app.slack_verifier.is_valid_request(
        request.get_data().decode("utf-8"), request.headers
    ):
        abort(403)

    # remove all extraneous white space and put into list.
    # rrequest = " ".join(request.form["text"].split()).split()
    return (
        jsonify({"response_type": "ephemeral", "text": "Slash commands not supported"}),
        200,
    )


@api.route("/interact", methods=["GET", "POST"])
def submit():
    """Called from slack for all interactions (dialogs, button, etc)."""
    if not current_app.slack_verifier.is_valid_request(
        request.get_data().decode("utf-8"), request.headers
    ):
        abort(403)

    rjson = json.loads(request.form["payload"])
    if rjson["type"] == "view_submission":
        verrors = handle_report_submit_validation(rjson)
        if verrors:
            return jsonify(verrors), 200
        run_async(current_app.config["EV_MODE"], handle_report_submit_modal, rjson)
        return "", 200
    elif rjson["type"] == "view_closed":
        run_async(current_app.config["EV_MODE"], handle_report_cancel_modal, rjson)
        return "", 200

    elif rjson["type"] == "block_actions":
        # ts = rjson["container"]["message_ts"]
        block_id = rjson["actions"][0]["block_id"]
        block_type = block_id.split(":")[0]
        """
        if "container" in rjson and rjson["container"].get("type", None) == "message":
            initiating_channel = rjson["container"]["channel_id"]
            initiating_message = rjson["container"]["message_ts"]
        """

        if block_type in ["NEWREP", "HOMETRAILREP", "HOMEDISTREP"]:
            rid = block_id.split(":")[1]
            value = rjson["actions"][0]["value"]
            state = json.dumps({"rid": rid})

            run_async(
                current_app.config["EV_MODE"],
                start_report,
                value,
                rjson["trigger_id"],
                state,
            )
        elif block_type == "HOMEAT":
            value = rjson["actions"][0]["value"]
            run_async(current_app.config["EV_MODE"], handle_at, value, rjson)
        else:
            logger.error(f"Unknown block actions block id {block_id}")
        return "", 200

    logger.error("Unhandled type {}: {}".format(rjson["type"], rjson))
    return "", 200


@api.route("/events", methods=["GET", "POST"])
def events():
    if not current_app.slack_verifier.is_valid_request(
        request.get_data().decode("utf-8"), request.headers
    ):
        abort(403)

    payload = request.json
    event_id = payload.get("event_id", "")

    # Check for retry. These are really annoying so we simple ignore them!
    retry_num = request.headers.get("X-Slack-Retry-Num", 0)
    retry_why = request.headers.get("X-Slack-Retry-Reason", "")
    if retry_num:
        logger.warning(
            "Ignoring retry event Id {} try {} reason {}".format(
                event_id, retry_num, retry_why
            )
        )
        return "", 200

    if payload["type"] == "url_verification":
        return dict(challenge=payload["challenge"])
    elif payload["type"] == "event_callback":
        event = payload["event"]
        logger.info(f"Event id {event_id} {event}")

        if event["type"] == "app_mention":
            # let's chat
            run_async(current_app.config["EV_MODE"], talk_to_me, event_id, event)
        elif event["type"] == "file_created" or event["type"] == "file_shared":
            run_async(current_app.config["EV_MODE"], handle_file, event)
        elif event["type"] == "app_home_opened":
            # Alas mobile app doesn't work yet
            if event.get("tab", None) == "home":
                run_async(current_app.config["EV_MODE"], handle_home, event)
        elif event["type"] == "message":
            subtype = event.get("subtype", "")
            if subtype and subtype != "file_share":
                # ignore
                logger.info(f"Ignoring message subtype {subtype}")
            elif event["user"] == get_bot_user_id():
                logger.info("Ignoring message - its from me!")
            else:
                # Treat like a mention - seems like this can only be DMs.
                # hack - make it look same as a @mention.
                event["text"] = "DM " + event["text"]
                run_async(current_app.config["EV_MODE"], talk_to_me, event_id, event)
        else:
            logger.info("Ignored Event type: {}".format(event["type"]))

        # Always respond
        return "", 200
    logger.error("Unknown event {}".format(payload["type"]))
    return "", 200


def handle_file(event):
    # This runs async w/o an app context.
    finfo = get_file_info(event["file_id"])
    finfo = finfo["file"]
    logger.info(
        "IGNORING: File info image link {} channels {}".format(
            finfo["url_private"], finfo["channels"]
        )
    )
    return {}


def start_report(ttype, trigger, state):
    try:
        logger.info(f"Opening modal type {ttype} trigger_id {trigger} state {state}")
        if ttype == "trail":
            open_trail_report_modal(trigger, state)
        else:
            open_disturbance_report_modal(trigger, state)
    except Exception:
        logger.exception("Start report failed")


def handle_at(when, rjson):
    """Handle Home buttons for 'at'."""
    app = asyncev.wapp
    with app.app_context():
        # userid = rjson["user"]["id"]
        where = "all"
        today = datetime.datetime.now(tz.tzutc())
        which_day = today
        if when == "Tomorrow":
            which_day = today + datetime.timedelta(days=1)

        lday, ckey = utils.at_cache_helper(which_day, where)
        logger.info(f"APP: handle_at Pacific TZ: {lday.isoformat()} Key: {ckey}")
        atinfo = app.ddb_cache.get(ckey)
        if not atinfo:
            logger.warning(f"No atinfo for ckey: {ckey}")
            view = {
                "type": "modal",
                "title": {"type": "plain_text", "text": "Hmm don't know that one"},
                "notify_on_close": False,
                "blocks": [],
            }
        else:
            blocks = utils.atinfo_to_blocks(atinfo, lday)
            logger.debug(f"APP:blocks: {blocks}")
            # Example of something that doesn't display correctly on iphone
            bblocks = [  # noqa: F841
                {"type": "divider"},
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "Thu Jul 11 2024"},
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Info Station:*\n_9:00AM-11:00AM_: L Turrini-Smith\n"
                        "_11:00AM-1:00PM_: S DuCoeur\n"
                        "_1:00PM-3:00PM_: V Cormack\n_3:00PM-5:00PM_: E Lichy",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*Whaling Station:*\n_9:00AM-11:00AM_: J Alexander\n"
                        "_11:00AM-1:00PM_: E Fukunaga\n"
                        "_1:00PM-3:00PM_: C Schaefer\n_3:00PM-5:00PM_: E Young",
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "*The Women Who Shaped and Saved Point"
                        " Lobos Public Walk:*\n_10:30AM_: M Alancraig"
                        " at Whalers Cabin",
                    },
                },
            ]
            view = {
                "type": "modal",
                "title": {"type": "plain_text", "text": "Who's at the Reserve"},
                "notify_on_close": False,
                "blocks": blocks,
            }

        try:
            post("views.open", dict(trigger_id=rjson["trigger_id"], view=view))
        except exc.SlackApiError as ex:
            if "expired_trigger_id" in repr(ex):
                logger.warning("Received trigger expired - ignoring")
            else:
                raise

    return {}
