# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

from dateutil import tz
import datetime


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


def buttons_block(block_id, options: list):
    # Create a actions button block.
    # options should be a list of tuples (text, value)
    elements = []
    for o in options:
        elements.append(
            {
                "type": "button",
                "value": o[1],
                "text": {"type": "plain_text", "text": o[0]},
            }
        )
    b = {"type": "actions", "block_id": str(block_id), "elements": elements}
    return b


def action_block(block_id, elements: list):
    b = {"type": "actions", "block_id": str(block_id), "elements": elements}
    return b


def divider_block():
    return {"type": "divider"}


def input_block(block_id, label, element, optional=False):
    """ This is for modals. element can be plain-text, select """
    b = {
        "type": "input",
        "block_id": str(block_id),
        "label": {"type": "plain_text", "text": label},
        "element": element,
        "optional": optional,
    }
    return b


def pt_input_element(action_id, place_text, multiline=False):
    e = {
        "type": "plain_text_input",
        "action_id": action_id,
        "placeholder": {"type": "plain_text", "text": place_text},
        "multiline": multiline,
    }
    return e


def select_element(action_id, place_text, options):
    ops = []
    for o in options:
        ops.append({"text": {"type": "plain_text", "text": o[0]}, "value": o[1]})
    e = {
        "type": "static_select",
        "action_id": action_id,
        "placeholder": {"type": "plain_text", "text": place_text},
        "options": ops,
    }
    return e


def atinfo_to_blocks(atinfo, lday: datetime.datetime):
    """ Convert/format atinfo into nice presentation. """
    blocks = []
    blocks.append(divider_block())
    blocks.append(text_block(lday.strftime("%a %b %d %Y")))
    for loc, what in atinfo.items():
        if what:
            t = "*{}:*".format(loc)
            for i in what:
                t += "\n_{}_: {}".format(i["time"], ", ".join(i["who"]))
                if "title" in i:
                    t += " - {}".format(i["title"])
            blocks.append(text_block(t))
    return blocks


def at_cache_helper(which_day: datetime.datetime, where):
    # Look for day based on our location (America/Los_Angeles)
    lday = which_day.astimezone(tz=tz.gettz("America/Los_Angeles"))
    ckey = "{}:{}".format(lday.strftime("%Y%m%d"), where)
    return lday, ckey
