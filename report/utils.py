# Copyright 2019-2024 by J. Christopher Wagner (jwag). All rights reserved.

from dateutil import tz
import datetime
import re


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
    """This is for modals. element can be plain-text, select"""
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


def select_element(action_id, place_text, options, initial_option=None):
    ops = []
    for o in options:
        ops.append({"text": {"type": "plain_text", "text": o[0]}, "value": o[1]})
    e = {
        "type": "static_select",
        "action_id": action_id,
        "placeholder": {"type": "plain_text", "text": place_text},
        "options": ops,
    }
    if initial_option:
        e["initial_option"] = {
            "text": {"type": "plain_text", "text": initial_option[0]},
            "value": initial_option[1],
        }
    return e


def multi_select_element(action_id, place_text, options, initial_option=None):
    ops = []
    for o in options:
        ops.append({"text": {"type": "plain_text", "text": o[0]}, "value": o[1]})
    e = {
        "type": "multi_static_select",
        "action_id": action_id,
        "placeholder": {"type": "plain_text", "text": place_text},
        "options": ops,
    }
    if initial_option:
        e["initial_option"] = {
            "text": {"type": "plain_text", "text": initial_option[0]},
            "value": initial_option[1],
        }
    return e


def atinfo_to_blocks(atinfo, lday: datetime.datetime):
    """Convert/format atinfo into nice presentation."""
    blocks = []
    blocks.append(divider_block())
    blocks.append(text_block(lday.strftime("%a %b %d %Y")))

    # Use rich_text rather than mrkdwn since a) Slack recommends it and
    # b) iphones don't render mrkdwn correctly (especially ':')
    for atype, info in atinfo.items():
        if info:
            b = dict(type="rich_text", elements=[])
            b["elements"].append(
                dict(
                    type="rich_text_section",
                    elements=[dict(type="text", text=atype, style=dict(bold=True))],
                )
            )

            for i in info:
                info_section = dict(type="rich_text_section", elements=[])
                info_section["elements"].append(
                    dict(type="text", style=dict(italic=True), text=f"{i['time']}: ")
                )
                line = ", ".join(i["who"])
                if "title" in i:
                    line += " - {}".format(i["title"])
                if i.get("where", "unk") != "unk":
                    line += f" at {i['where']}"
                info_section["elements"].append(dict(type="text", text=line))
                b["elements"].append(info_section)
            blocks.append(b)
    return blocks


def at_cache_helper(which_day: datetime.datetime, where):
    # Look for day based on our location (America/Los_Angeles)
    lday = which_day.astimezone(tz=tz.gettz("America/Los_Angeles"))
    ckey = "{}:{}".format(lday.strftime("%Y%m%d"), where)
    return lday, ckey


def convert_gps(gps):
    """Parse iphone compass app GPS coordinates: '36°33′0″ N  121°55′28″ W'"""
    # 2 spaces between lat/lng
    try:
        lat, lng = gps.split("  ")
        dlat = _dms_to_dd(lat)
        dlng = _dms_to_dd(lng)
        return dlat, dlng
    except Exception:
        return None, None


def _dms_to_dd(coords):
    """iphone uses some funky punctuation"""
    coords = " ".join(coords.split())
    deg, minutes, seconds, direction = re.split(
        "[°'\"\N{PRIME}\N{DOUBLE PRIME}]", coords
    )
    return (float(deg) + float(minutes) / 60 + float(seconds) / (60 * 60)) * (
        -1 if direction.strip() in ["W", "S"] else 1
    )
