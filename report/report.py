# Copyright 2019-2020 by J. Christopher Wagner (jwag). All rights reserved.

import json
import logging

import asyncev
from constants import (
    KIOSK_RESOLVED_UNKNOWN,
    STATUS_PLACEHOLDER,
    TRAIL_VALUE_2_DESC,
    TYPE_TRAIL,
    TYPE_DISTURBANCE,
    ISSUES_2_DESC,
)
import exc
from slack_api import post, post_message, user_to_name
from utils import input_block, pt_input_element, select_element


logger = logging.getLogger("report")


def open_trail_report_modal(trigger, state):
    trail_options = []
    for n, d in TRAIL_VALUE_2_DESC.items():
        trail_options.append((d, n))
    valid_trail_issues = ["po", "sign", "cable", "tree", "step", "trash", "ot"]
    trail_issues = []
    for n in valid_trail_issues:
        trail_issues.append((ISSUES_2_DESC[n], n))

    blocks = []
    blocks.append(
        input_block(
            "issues", "Issue", select_element("value", "Select one", trail_issues)
        )
    )
    blocks.append(
        input_block(
            "location",
            "Trail/Location",
            select_element("value", "Select one", trail_options),
        )
    )
    blocks.append(
        input_block(
            "cross_trail",
            "Nearest Cross Trail",
            select_element("value", "Select one", trail_options),
            optional=True,
        )
    )
    blocks.append(
        input_block(
            "gps",
            "GPS",
            pt_input_element(
                "value", "Use Compass app (ios) to grab current coordinates"
            ),
            optional=True,
        )
    )
    blocks.append(
        input_block(
            "details",
            "Additional Details",
            pt_input_element("value", "Any additional details", multiline=True),
            optional=True,
        )
    )
    view = {
        "type": "modal",
        "callback_id": TYPE_TRAIL,
        "title": {"type": "plain_text", "text": "Trail Report"},
        "notify_on_close": True,
        "private_metadata": state,
        "submit": {"type": "plain_text", "text": "Create"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }

    try:
        post("views.open", dict(trigger_id=trigger, view=view))
    except exc.SlackApiError as ex:
        if "trigger_expired" in repr(ex):
            logger.warning("Received trigger expired - ignoring")
        else:
            raise


def open_disturbance_report_modal(trigger, state):
    trail_options = []
    for n, d in TRAIL_VALUE_2_DESC.items():
        trail_options.append((d, n))
    valid_dist_issues = [
        "off",
        "eat",
        "pet",
        "take",
        "tide",
        "climb",
        "evil",
        "pin",
        "ott",
        "bird",
        "jump",
        "bike",
        "drone",
        "air",
        "fish",
        "ot",
    ]
    disturbance_issues = []
    for n in valid_dist_issues:
        disturbance_issues.append((ISSUES_2_DESC[n], n))

    blocks = []
    blocks.append(
        input_block(
            "issues",
            "Disturbance",
            select_element("value", "Select one", disturbance_issues),
        )
    )
    blocks.append(
        input_block(
            "location",
            "Trail/Location",
            select_element("value", "Select one", trail_options),
        )
    )
    blocks.append(
        input_block(
            "cross_trail",
            "Nearest Cross Trail",
            select_element("value", "Select one", trail_options),
            optional=True,
        )
    )
    blocks.append(
        input_block(
            "kiosk_called",
            "Was Kiosk Called?",
            select_element(
                "value",
                "Select Yes or No",
                [("Yes", "yes"), ("No", "no")],
                initial_option=("No", "no"),
            ),
        )
    )
    blocks.append(
        input_block(
            "kiosk_resolution",
            "Did kiosk/SP personnel resolve issue?",
            select_element(
                "value",
                "Select One",
                [("Yes", "yes"), ("No", "no"), ("Unsure", KIOSK_RESOLVED_UNKNOWN)],
            ),
            optional=True,
        )
    )
    blocks.append(
        input_block(
            "details",
            "Additional Details",
            pt_input_element("value", "Any additional details", multiline=True),
            optional=True,
        )
    )
    view = {
        "type": "modal",
        "callback_id": TYPE_DISTURBANCE,
        "title": {"type": "plain_text", "text": "Disturbance Report"},
        "notify_on_close": True,
        "private_metadata": state,
        "submit": {"type": "plain_text", "text": "Create"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": blocks,
    }

    try:
        post("views.open", dict(trigger_id=trigger, view=view))
    except exc.SlackApiError as ex:
        if "expired" in repr(ex):
            logger.warning("Received trigger expired - ignoring")
        else:
            raise


def handle_report_submit_modal(rjson):
    app = asyncev.wapp
    with app.app_context():
        userid = rjson["user"]["id"]
        state = json.loads(rjson["view"]["private_metadata"])
        logger.info(
            "Report submit by {}({}) type {} rid {}".format(
                user_to_name(userid), userid, rjson["view"]["callback_id"], state["rid"]
            )
        )
        if state["rid"] != "0":
            # From @ new report - where we create a 'placeholder' report (maybe with
            # pictures)
            nr = app.report.get(state["rid"])
            if not nr:
                # hmm - what happened to the report
                post_message(userid, "Couldn't find report {}".format(state["rid"]))
                return {}
            if nr.status != STATUS_PLACEHOLDER:
                # Hmm - report ID already completed. This can happen when starting with
                # 'new rep' which produces the 'trail' versus 'disturbance' buttons
                # and those buttons are used more than once.
                post_message(userid, "Report {} already completed?".format(nr.id))
                return {}

        values = rjson["view"]["state"]["values"]
        dinfo = {}
        for field in app.report.user_field_list():
            # desktop app always returns something - iphone app doesn't.
            if field in values:
                rv = values[field]["value"]
                if rv["type"] == "static_select":
                    if "selected_option" in rv:
                        dinfo[field] = rv["selected_option"]["value"]
                elif "value" in rv:
                    dinfo[field] = rv["value"]
        if state["rid"] != "0":
            nr = app.report.complete(
                nr, rjson["view"]["callback_id"], rjson["user"], None, dinfo
            )
        else:
            # This is from Home button - no report started yet
            nr = app.report.create(
                rjson["view"]["callback_id"], rjson["user"], None, dinfo
            )

        # inform user
        post_message(
            userid,
            "Report [{}] saved. To add photos, you can send me a message"
            " (with photos attached): *{} photo*".format(
                app.report.id_to_name(nr), app.report.id_to_name(nr)
            ),
        )
    return {}


def handle_report_cancel_modal(rjson):
    # Called on modal cancel.
    app = asyncev.wapp
    with app.app_context():
        state = json.loads(rjson["view"]["private_metadata"])
        if state["rid"] != "0":
            rm = app.report.get(state["rid"])
            # Bug in IOS app - calls us on modal submit (sigh)
            if rm and rm.status == STATUS_PLACEHOLDER:
                logger.info("Cancelled - deleting report {}".format(state["rid"]))
                app.report.delete(rm, app.s3)
    return {}
