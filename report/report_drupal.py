# Copyright 2020 by J. Christopher Wagner (jwag). All rights reserved.

"""
This is the interface from slack to/from backend of drupal.
"""

from dataclasses import dataclass, fields
from datetime import datetime
from dateutil import tz
import logging

from drupal_api import DrupalApi
import slack_api

from constants import (
    TYPE_TRAIL,
    TYPE_DISTURBANCE,
)


@dataclass
class ReportModel:
    id: str  # readable unique id (primary key)

    create_datetime: datetime
    type: str  # Trail or Disturbance
    location: str  # e.g. trail name
    wildlife_issues: str = None  # e.g. otters - comma separated
    other_issues: str = None  # e.g. otters - comma separated

    # Full name from website
    reporter: str = None

    # website uuid
    reporter_id: str = None

    cross_trail: str = None
    details: str = None

    @classmethod
    def field_list(cls) -> set:
        """ Return set of all field names """
        return {f.name for f in fields(cls)}

    @classmethod
    def user_field_list(cls) -> set:
        """ Return set of all field names that are user/form settable """
        internal = {
            "id",
            "create_datetime",
            "photos",
            "type",
            "reporter",
        }
        return cls.field_list() - internal


class Report:
    def __init__(self, config):
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._site = DrupalApi(
            config["PLSNR_JSON_USERNAME"],
            config["PLSNR_PASSWORD"],
            "{}/plsnr1933api".format(config["PLSNR_HOST"]),
            config["SSL_VERIFY"],
        )

    def _initrm(self):
        dt = datetime.now(tz.tzutc())
        nr = ReportModel(id="", type="Unknown", location="", create_datetime=dt,)
        return nr

    def _fillin(self, nr, rtype, who, dinfo):
        nr.type = rtype
        for f in nr.user_field_list():
            if f in dinfo:
                setattr(nr, f, dinfo[f])
        nr.reporter_id, nr.reporter, _ = self.slack2plsnr(who["id"])

    def create(self, rtype, who, dinfo):
        nr = self._initrm()
        self._fillin(nr, rtype, who, dinfo)
        if not nr.reporter_id:
            return (
                None,
                "Cannot map slack user {} to PLSNR website user".format(who["name"]),
            )

        nr.id = self._site.create_disturbance_report(
            nr.create_datetime,
            nr.details,
            nr.wildlife_issues,
            nr.other_issues,
            nr.reporter_id,
        )
        self._logger.info("Created report {}".format(nr.id))
        return nr, None

    def get_wildlife_issue_list(self):
        # Return a list of tuple (<display_name>, <id>) of possible wildlife issues
        wissues = self._site.get_taxonomy("wildlife")
        return [(d["name"], d["id"]) for d in wissues]

    def get_other_issue_list(self):
        # Return a list of tuple (<display_name>, <id>) of possible other issues
        wissues = self._site.get_taxonomy("other")
        return [(d["name"], d["id"]) for d in wissues]

    def slack2plsnr(self, slack_user_id):
        # Attempt to map the slack_id to a registered plsnr web site user
        # Returns a tuple - (<drupal uuid for user>, <name>, <drupal uid e.g. 358))
        all_users = self._site.get_all_users()

        slack_user = slack_api.get("users.info", params={"user": slack_user_id})
        for uuid, attributes in all_users.items():
            slack_profile = slack_user["user"].get("profile", None)
            if slack_profile and "email" in slack_profile:
                if (attributes.get("mail", "1") == slack_profile.get("email", "2")) or (
                    attributes.get("name", "3").lower()
                    == slack_profile.get("real_name_normalized", "4").lower()
                ):
                    return uuid, attributes["name"], attributes["drupal_internal__uid"]
        return None, None, None

    def whoswho(self):
        """ Return a dict:
        { "slack_id": {
            "slack_name": <name>,
            "web_name": <matched name>,
            "web_id": <matched uid>
            },
        }
        and a list of slack users that didn't match
        """
        whoswho = {}
        unmatched = []
        all_slack_users = slack_api.get_all_users()
        all_users = self._site.get_all_users()

        for su in all_slack_users:
            slack_profile = su.get("profile", None)
            if slack_profile:
                info = {"slack_name": slack_profile["real_name"]}
                # Match email - since we are a small org - matching name also works
                # sometimes.
                for uuid, attributes in all_users.items():
                    if (
                        attributes.get("mail", "1") == slack_profile.get("email", "2")
                    ) or (
                        attributes.get("name", "3").lower()
                        == slack_profile.get("real_name_normalized", "4").lower()
                    ):
                        info["web_name"] = attributes["name"]
                        info["email"] = attributes["mail"]
                        info["web_id"] = attributes["drupal_internal__uid"]
                        break
                if "web_name" not in info:
                    # Didn't find them.
                    unmatched.append((su["id"], slack_profile["real_name"]))
                whoswho[su["id"]] = info
        return whoswho, unmatched

    @staticmethod
    def id_to_name(rm):
        if rm.type == TYPE_TRAIL:
            rid = "TR-{}".format(rm.id)
        elif rm.type == TYPE_DISTURBANCE:
            rid = "DR-{}".format(rm.id)
        else:
            rid = rm.id
        return rid

    @classmethod
    def user_field_list(cls):
        return ReportModel.user_field_list()
