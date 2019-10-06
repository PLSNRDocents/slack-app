# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging
import os

import cachetools.func
import requests

from exc import SlackApiError

SLACK_URL = "https://www.slack.com/api/"

logger = logging.getLogger(__name__)


def _chk_error(rv, endpoint):
    try:
        jresponse = rv.json()
    except Exception:
        jresponse = None
    logger.info(
        "Slack POST to {} status {}: {}".format(endpoint, rv.status_code, jresponse)
    )
    if rv.status_code != 200 or (jresponse and "error" in jresponse):
        raise SlackApiError("Endpoint {} error {}".format(endpoint, jresponse["error"]))
    return jresponse


def post(endpoint, payload):
    headers = {
        "Authorization": "Bearer {}".format(os.environ["BOT_TOKEN"]),
        "Content-Type": "application/json;charset=utf-8",
        "Accept": "application/json",
    }
    try:
        rv = requests.post(SLACK_URL + "/" + endpoint, headers=headers, json=payload)
    except Exception as exc:
        logger.error("POST failed", exc)
        return None
    return _chk_error(rv, endpoint)


def get(endpoint, slack_id):
    headers = {
        "Authorization": "Bearer {}".format(os.environ["BOT_TOKEN"]),
        "Content-Type": "application/json;charset=utf-8",
        "Accept": "application/json",
    }
    rv = requests.get(
        SLACK_URL + "/" + endpoint, headers=headers, params={"user": slack_id}
    )
    rv.raise_for_status()
    return rv.json()


def get_file_info(fid):
    headers = {"Authorization": "Bearer {}".format(os.environ["BOT_TOKEN"])}
    rv = requests.get(SLACK_URL + "/files.info", headers=headers, params={"file": fid})
    rv.raise_for_status()
    return rv.json()


def send_update(response_url, text, replace_original=False, delete_original=False):
    payload = {
        "text": text,
        "response_type": "ephemeral",
        "replace_original": replace_original,
        "delete_original": delete_original,
    }
    rv = requests.post(response_url, json=payload)
    _chk_error(rv, response_url)


def post_message(channel, user, payload):
    if isinstance(payload, list):
        content = {"text": "a report", "blocks": payload}
    else:
        content = {"text": payload}
    content.update(channel=channel, user=user, as_user=True)
    jresponse = post("chat.postEphemeral", content)
    return jresponse["message_ts"]


@cachetools.func.ttl_cache(600, ttl=60 * 60 * 24)
def user_to_name(slack_user_id):
    try:
        j = get("users.info", slack_user_id)
        return j["user"]["real_name"]
    except Exception:
        return ""
