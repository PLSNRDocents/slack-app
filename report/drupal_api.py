# Copyright 2020 by J. Christopher Wagner (jwag). All rights reserved.
"""
Interact with the Drupal JSON:API module to fetch and create entities.
https://www.drupal.org/docs/8/core/modules/jsonapi-module

"""

import cachetools.func
from datetime import datetime
import dateutil
import logging

import requests

from constants import TYPE_DISTURBANCE

logger = logging.getLogger(__name__)


class DrupalApi:
    def __init__(self, username, password, server_url, ssl_verify):
        if not username or not password:
            raise ValueError("username and/or password not specified")
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

    def simple_get(self, path, params, fetchall=True):
        next_batch = f"{self.server_url}{path}"
        rdata = []
        while next_batch:
            rv = self.session.get(next_batch, params=params)
            rv.raise_for_status()
            jbody = rv.json()
            rdata.extend(jbody["data"])
            if fetchall:
                next_batch = jbody["links"].get("next", None)
            else:
                next_batch = None
            if next_batch:
                next_batch = next_batch["href"]
                params = {}
        return rdata

    def get_activity_views(self):
        """
        Get activity views.
        Returns dict of name: attributes. where 'name' is the machine name
        (look at "name" for display name)
        """
        raw_views = self.simple_get("/activity_view/activity_view", None)
        views = {
            item["attributes"]["drupal_internal__id"]: item["attributes"]
            for item in raw_views
        }
        return views

    def get_activity_types(self):
        """
        Get activity types.
        Returns dict of name: attributes. where 'name' is the machine name
        """
        raw_types = self.simple_get("/activity_type/activity_type", None)
        views = {
            item["attributes"]["drupal_internal__id"]: item["attributes"]
            for item in raw_types
        }
        return views

    @cachetools.func.ttl_cache(60, ttl=(60 * 5))
    def get_taxonomy(self, which):
        """

        The 'name' in Drupal as returned in relationships looks like:
        taxonomy_term--xxxx (e.g. taxonomy_term--wildlife_disturbance)
        We accept 'which' either the entire name or 'xxx'.

        N.B. while this is cached - that is mostly for testing - it doesn't
        really help in production when this is a lambda. That's why higher level code
        actually writes this to a DB cache (so we can respond to slack fast enough).

        Return a list of dict

        [ {
            "name": <name>,
            "id": <uuid>
          },...
        ]
        """
        tterm = which.split("--", 1)
        if len(tterm) == 2:
            tterm = tterm[1]
        else:
            tterm = which

        rv = self.session.get(f"{self.server_url}/taxonomy_term/{tterm}")
        rv.raise_for_status()
        jbody = rv.json()

        terms = list()
        for d in jbody["data"]:
            terms.append({"name": d["attributes"]["name"], "id": d["id"]})
        if not terms:
            # that isn't right - don't cache
            raise ValueError(f"No taxonomy terms returned for {which}")
        return terms

    def get_reports(self):
        rv = self.session.get(
            f"{self.server_url}/node/disturbance_report",
            params={"sort": "-field_interaction_time", "page[limit]": "10"},
        )
        rv.raise_for_status()
        jbody = rv.json()

        reports = list()
        for d in jbody["data"]:
            r = {
                "id": d["id"],
                "type": TYPE_DISTURBANCE,
                "details": d["attributes"]["field_details"],
                "create_datetime": dateutil.parser.parse(
                    d["attributes"]["field_interaction_time"]
                ),
            }
            # All the rest are relationships - we return the UUID and let caller xlate
            rels = d["relationships"]
            if "field_reporter" in rels and "data" in rels["field_reporter"]:
                r["reporter"] = rels["field_reporter"]["data"]["id"]
            if "field_place" in rels and rels["field_place"].get("data", None):
                r["location"] = rels["field_place"]["data"]["id"]
            if "field_wildlife_disturbance" in rels and rels[
                "field_wildlife_disturbance"
            ].get("data", None):
                r["wildlife_issues"] = [
                    f["id"] for f in rels["field_wildlife_disturbance"]["data"]
                ]
            if "field_other_disturbance" in rels and rels[
                "field_other_disturbance"
            ].get("data", None):
                r["other_issues"] = [
                    f["id"] for f in rels["field_other_disturbance"]["data"]
                ]
            reports.append(r)
        return reports

    def create_disturbance_report(
        self,
        when: datetime,
        details,
        wildlife_tax_ids,
        other_tax_ids,
        reporter_id,
        location_tax_id,
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
                "field_via": "slack",
            },
            "relationships": dict(),
        }

        if wildlife_tax_ids:
            data = list()
            for tax_id in wildlife_tax_ids:
                data.append(
                    {"type": "taxonomy_term--wildlife_disturbance", "id": tax_id}
                )
            body["relationships"]["field_wildlife_disturbance"] = {"data": data}

        if other_tax_ids:
            data = list()
            for tax_id in other_tax_ids:
                data.append({"type": "taxonomy_term--other_disturbance", "id": tax_id})
            body["relationships"]["field_other_disturbance"] = {"data": data}

        if reporter_id:
            body["relationships"]["field_reporter"] = {
                "data": {"type": "user--user", "id": reporter_id}
            }
        body["relationships"]["field_place"] = {
            "data": {"type": "taxonomy_term--places", "id": location_tax_id}
        }

        rv = self.session.post(
            f"{self.server_url}/node/disturbance_report", json=dict(data=body)
        )
        if rv.status_code >= 400:
            # Alas we seem to sometimes get a 500 with the error:
            #   The controller result claims to be providing relevant cache metadata,
            #   but leaked metadata was detected.
            # However the content was created just fine.
            logger.warning(f"API failed code:{rv.status_code} Text:{rv.text}")
            if rv.status_code == 500 and "leaked metadata" in rv.text:
                return None, "API returned error but report likely created"
            return None, "API failed"

        # return id which is what is need when POSTing.
        jbody = rv.json()
        return jbody["data"]["id"], None

    @cachetools.func.ttl_cache(60, ttl=(60 * 60 * 8))
    def get_all_users(self):
        """Return a dict

        { "id": {
            <user attributes>
                },...
        }
        """

        users = {}
        next_batch = f"{self.server_url}/user/user"
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

    @cachetools.func.ttl_cache(60, ttl=(60 * 5))
    def get_user(self, user_uuid):
        rv = self.session.get(f"{self.server_url}/user/user/{user_uuid}")
        rv.raise_for_status()
        jbody = rv.json()
        return jbody["data"]
