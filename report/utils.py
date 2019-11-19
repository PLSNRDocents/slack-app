# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.


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
