# Copyright 2019-2020 by J. Christopher Wagner (jwag). All rights reserved.

"""
Handle new 'Home' tab.
For now - this is a static view.
"""
import logging

import asyncev
from constants import TYPE_TRAIL, TYPE_DISTURBANCE
from slack_api import post
from utils import buttons_block, divider_block, text_block


logger = logging.getLogger("home")


def handle_home(event):
    """ When user opens home tab we get this event """
    app = asyncev.wapp
    with app.app_context():
        b = []
        b.append(text_block("Welcome"))
        b.append(divider_block())
        if app.config["ENABLE_TRAIL_REPORT"]:
            b.append(
                buttons_block("HOMETRAILREP:0", [("Create Trail Report", TYPE_TRAIL)])
            )
        b.append(
            buttons_block(
                "HOMEDISTREP:0", [("Create Disturbance Report", TYPE_DISTURBANCE)]
            )
        )
        b.append(divider_block())
        b.append(text_block("Who's at the reserve:"))
        b.append(
            buttons_block("HOMEAT", [("Today", "Today"), ("Tomorrow", "Tomorrow")])
        )
        view = {"type": "home", "blocks": b}
        post("views.publish", payload={"user_id": event["user"], "view": view})
    return {}
