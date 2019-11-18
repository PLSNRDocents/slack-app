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
