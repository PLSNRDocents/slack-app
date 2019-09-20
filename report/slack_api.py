# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging
import os

import requests

SLACK_URL = "https://www.slack.com/api/"

logger = logging.getLogger(__name__)


def post(endpoint, payload):
    headers = {
        "Authorization": "Bearer {}".format(os.environ["BOT_TOKEN"]),
        "Content-Type": "application/json;charset=utf-8",
    }
    rv = requests.post(SLACK_URL + "/" + endpoint, headers=headers, json=payload)
    logger.info("Slack POST to {} status {}".format(endpoint, rv.status_code))
    rv.raise_for_status()


def get_file_info(fid):
    headers = {"Authorization": "Bearer {}".format(os.environ["BOT_TOKEN"])}
    rv = requests.get(SLACK_URL + "/files.info", headers=headers, params={"file": fid})
    rv.raise_for_status()
    return rv.json()


def send_update(response_url, text):
    payload = {"text": text, "response_type": "ephemeral"}
    rv = requests.post(response_url, json=payload)
    rv.raise_for_status()


def post_message(channel, user, payload):
    post(
        "chat.postEphemeral",
        dict(channel=channel, user=user, text=payload, as_user=True),
    )
