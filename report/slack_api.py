# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging
import os

import cachetools.func
import requests

from exc import SlackApiError

SLACK_URL = "https://www.slack.com/api/"
BOT_USER_ID = ""

logger = logging.getLogger(__name__)


def _chk_error(rv, endpoint):
    try:
        jresponse = rv.json()
    except Exception:
        jresponse = None
    logger.info("Slack POST to {} status {}".format(endpoint, rv.status_code))
    if rv.status_code != 200 or (jresponse and "error" in jresponse):
        raise SlackApiError("Endpoint {} error {}".format(endpoint, jresponse["error"]))
    return jresponse


def post(endpoint, payload, auth=None):
    if not auth:
        auth = os.environ["BOT_TOKEN"]
    headers = {
        "Authorization": "Bearer {}".format(auth),
        "Content-Type": "application/json;charset=utf-8",
        "Accept": "application/json",
    }
    try:
        rv = requests.post(SLACK_URL + "/" + endpoint, headers=headers, json=payload)
    except Exception as exc:
        logger.error("POST failed", exc)
        return None
    return _chk_error(rv, endpoint)


def get(endpoint, params=None):
    headers = {
        "Authorization": "Bearer {}".format(os.environ["BOT_TOKEN"]),
        "Content-Type": "application/json;charset=utf-8",
        "Accept": "application/json",
    }
    rv = requests.get(SLACK_URL + "/" + endpoint, headers=headers, params=params)
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


def post_ephemeral_message(channel, user, payload):
    if isinstance(payload, list):
        content = {"text": "Here ya go!", "blocks": payload}
    else:
        content = {"text": payload}
    content.update(channel=channel, user=user, as_user=True)
    jresponse = post("chat.postEphemeral", content)
    return jresponse["message_ts"]


def post_message(channel, payload):
    """ PostMessage - 'channel' can be user ID. """
    if isinstance(payload, list):
        content = {"text": "Here ya go!", "blocks": payload}
    else:
        content = {"text": payload}
    content.update(channel=channel, as_user=True)
    jresponse = post("chat.postMessage", content)
    return jresponse["ts"]


def delete_message(channel, ts):
    # This seems to fail for users other than me :-)
    payload = {"channel": channel, "ts": ts, "as_user": True}
    try:
        post("chat.delete", payload, auth=os.environ["APP_TOKEN"])
    except SlackApiError as exc:
        logger.warning(
            "Delete message {} channel {} failed: {}".format(ts, channel, exc)
        )


@cachetools.func.ttl_cache(600, ttl=60 * 60 * 24)
def user_to_name(slack_user_id):
    try:
        j = get("users.info", params={"user": slack_user_id})
        return j["user"]["real_name"]
    except Exception:
        return ""


def get_bot_info():
    j = get("auth.test")
    global BOT_USER_ID
    BOT_USER_ID = j["user_id"]
    logger.info("BOT USER ID {}".format(BOT_USER_ID))


def get_bot_user_id():
    return BOT_USER_ID
