# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import os

import requests

SLACK_URL = "https://www.slack.com/api/"


def post(endpoint, payload):
    headers = {
        "Authorization": "Bearer {}".format(os.environ["BOT_TOKEN"]),
        "Content-Type": "application/json;charset=utf-8",
    }
    rv = requests.post(SLACK_URL + "/" + endpoint, headers=headers, json=payload)
    rv.raise_for_status()


def get_file_info(fid):
    headers = {"Authorization": "Bearer {}".format(os.environ["BOT_TOKEN"])}
    rv = requests.get(SLACK_URL + "/files.info", headers=headers, params={"file": fid})
    rv.raise_for_status()
    return rv.json()
