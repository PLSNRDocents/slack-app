# Copyright 2020 by J. Christopher Wagner (jwag). All rights reserved.
"""
Interact with the Drupal JSON:API module to fetch and create entities.
https://www.drupal.org/docs/8/core/modules/jsonapi-module

"""
import cachetools.func
from datetime import datetime
import logging

import requests

logger = logging.getLogger(__name__)

ISSUETYPE_TO_TAXONOMYTYPE = {
    "wildlife": "wildlife_disturbance",
    "other": "other_disturbance",
}


class DrupalApi:
    def __init__(self, username, password, server_url, ssl_verify):
        self.username = username
        self.password = password
        self.server_url = server_url
        self.session = requests.session()

        self.session.headers.update(
            {
                "Accept": "application/vnd.api+json",
                "Content-Type": "application/vnd.api+json",
            }
        )
        self.session.auth = (username, password)
        self.session.verify = ssl_verify

    def get_taxonomy(self, which):
        """ Return a list of dict

        [ {
            "name": <name>,
            "id": <uuid>
          },...
        ]
        """

        rv = self.session.get(
            "{}/taxonomy_term/{}".format(
                self.server_url, ISSUETYPE_TO_TAXONOMYTYPE[which]
            )
        )
        rv.raise_for_status()
        jbody = rv.json()

        terms = list()
        for d in jbody["data"]:
            terms.append({"name": d["attributes"]["name"], "id": d["id"]})
        return terms

    def create_disturbance_report(
        self, when: datetime, details, wildlife_tax_ids, other_tax_ids, reporter_id
    ):

        if wildlife_tax_ids and not isinstance(wildlife_tax_ids, list):
            wildlife_tax_ids = [wildlife_tax_ids]
        if other_tax_ids and not isinstance(other_tax_ids, list):
            other_tax_ids = [other_tax_ids]

        body = {
            "type": "node--disturbance_report",
            "attributes": {
                "field_interaction_time": when.isoformat(timespec="seconds"),
                "field_details": {"value": details, "format": "plain_text"},
            },
        }

        if wildlife_tax_ids:
            data = list()
            for tax_id in wildlife_tax_ids:
                data.append(
                    {"type": "taxonomy_term--wildlife_disturbance", "id": tax_id}
                )
            if "relationships" not in body:
                body["relationships"] = dict()
            body["relationships"]["field_wildlife_disturbance"] = {"data": data}

        if other_tax_ids:
            data = list()
            for tax_id in other_tax_ids:
                data.append({"type": "taxonomy_term--other_disturbance", "id": tax_id})
            if "relationships" not in body:
                body["relationships"] = dict()
            body["relationships"]["field_other_disturbance"] = {"data": data}

        if reporter_id:
            if "relationships" not in body:
                body["relationships"] = dict()
            body["relationships"]["field_reporter"] = {
                "data": {"type": "user--user", "id": reporter_id}
            }
        rv = self.session.post(
            "{}/node/disturbance_report".format(self.server_url), json=dict(data=body)
        )
        if rv.status_code >= 400:
            logger.warning("API failed code:{} Text:{}".format(rv.status_code, rv.text))
        rv.raise_for_status()

        # return id which is what is need when POSTing.
        jbody = rv.json()
        return jbody["data"]["id"]

    @cachetools.func.ttl_cache(60, ttl=(60 * 60 * 2))
    def get_all_users(self):
        """ Return a dict

        { "id": {
            <user attributes>
                },...
        }
        """

        users = {}
        next_batch = "{}/user/user".format(self.server_url)
        while next_batch:
            rv = self.session.get(next_batch)
            rv.raise_for_status()
            jbody = rv.json()

            for d in jbody["data"]:
                users[d["id"]] = d["attributes"]
            next_batch = jbody["links"].get("next", None)
            if next_batch:
                next_batch = next_batch["href"]

        return users
