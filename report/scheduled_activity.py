# Copyright 2020 by J. Christopher Wagner (jwag). All rights reserved.

import logging

from dateutil import parser as date_parser
from dateutil import relativedelta
from dateutil import tz

from drupal_api import DrupalApi


class ScheduledActivity:
    def __init__(self, config, site: DrupalApi):
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._site = site

    def whoat(self, when, which):
        """
        when has format: 20191001

        We need to convert that to the UTC times that would correspond to that day
        in our (PST/PDT) timezone.

        Returns a dict:
        {<header>:
            [{
                "time": <time>,
                "title": <title>,
                "who": [<list of who>]
             }, ...
            ],
        <header2>: []
        }
        """

        rawdt = date_parser.parse(when)
        dt = rawdt.replace(tzinfo=tz.gettz("America/Los Angeles")).astimezone(tz.UTC)
        self._logger.info(f"whoat which: {which} when: {dt.isoformat()}")

        filters = {
            "filter[from][condition][path]": "start_time",
            "filter[from][condition][operator]": ">=",
            "filter[from][condition][value]": dt.isoformat(),
            "filter[to][condition][path]": "start_time",
            "filter[to][condition][operator]": "<",
            "filter[to][condition][value]": (
                dt + relativedelta.relativedelta(days=1)
            ).isoformat(),
        }
        if which != "all":
            filters.update(
                {
                    "filter[at][condition][path]": "activity_type",
                    "filter[at][condition][operator]": "=",
                    "filter[at][condition][value]": which,
                }
            )
        filters.update({"sort": "start_time"})

        self._logger.info(f"params: {filters}")

        results = self._site.simple_get(
            "/scheduled_activity/scheduled_activity", params=filters
        )
        views = self._site.get_activity_views()
        types = self._site.get_activity_types()

        atinfo = {}
        for r in results:
            rels = r["relationships"]
            st = date_parser.parse(r["attributes"]["start_time"]).strftime("%-I:%M%p")
            et = date_parser.parse(r["attributes"]["end_time"]).strftime("%-I:%M%p")
            presenter = self._site.get_user(rels["presenter"]["data"]["id"])
            me = presenter["attributes"]["name"]

            title = self.find_what(
                r, views, types.get(r["attributes"]["activity_type"], None)
            )
            if title not in atinfo:
                atinfo[title] = []
            atinfo[title].append(dict(who=[me], time=f"{st}-{et}"))
        if not atinfo:
            atinfo["Oh no!"] = [dict(who=["No one"], time="all day")]
        return atinfo

    def find_what(self, sa, views, atype):
        # look at activity view to figure out what field is 'what'
        # Simplification - assume different views don't have same activity type
        # with different 'what' fields.
        what_value = "unk"
        for view in views.values():
            sa_atype = sa["attributes"]["activity_type"]
            if sa_atype in view["activity_types"]:
                what = view["activity_types"][sa_atype].get("what", None)
                if what:
                    if what["week_entry"]["enabled"]:
                        field = what["week_entry"]["sa_field_name"]
                    elif what["month_entry"]["enabled"]:
                        field = what["month_entry"]["sa_field_name"]
                    else:
                        field = None
                    what_value = self.find_what_value(
                        field, sa["attributes"][field], atype,
                    )
                    return what_value
        return what_value

    def find_what_value(self, field_name, field_value, atype):
        # self._logger.info(f"find what value {field_name} {field_value} {atype}")
        if not atype:
            return "unk"
        if field_name == "title":
            return field_value
        elif field_name == "custom1":
            options = atype["custom_fields"][0]["options"]
            for option in options:
                if option["key"] == field_value:
                    return option["name"]
        elif field_name == "custom2":
            options = atype["custom_fields"][1]["options"]
            for option in options:
                if option["key"] == field_value:
                    return option["name"]
        return "unk"
