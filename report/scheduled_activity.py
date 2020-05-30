# Copyright 2020 by J. Christopher Wagner (jwag). All rights reserved.

import logging
from typing import List

from dateutil import parser as date_parser
from dateutil import relativedelta
from dateutil import tz

from drupal_api import DrupalApi


class ScheduledActivity:
    def __init__(self, config, site: DrupalApi):
        self._config = config
        self._logger = logging.getLogger(__name__)
        self._site = site

    def whoat(self, when, which: List):
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

        TODO: everything - which activity type, what title should be?
        Step 1 - taxon1 is title.

        """

        rawdt = date_parser.parse(when)
        dt = rawdt.replace(tzinfo=tz.gettz("America/Los Angeles")).astimezone(tz.UTC)

        filters = {
            "filter[from][condition][path]": "start_time",
            "filter[from][condition][operator]": ">=",
            "filter[from][condition][value]": dt.isoformat(),
            "filter[to][condition][path]": "start_time",
            "filter[to][condition][operator]": "<",
            "filter[to][condition][value]": (
                dt + relativedelta.relativedelta(days=1)
            ).isoformat(),
            "filter[at][condition][path]": "activity_type",
            "filter[at][condition][operator]": "=",
            "filter[at][condition][value]": which[0],
            "sort": "start_time",
        }

        results = self._site.simple_get(
            "/scheduled_activity/scheduled_activity", params=filters
        )

        atinfo = {}
        for r in results:
            rels = r["relationships"]
            st = date_parser.parse(r["attributes"]["start_time"]).strftime("%-I:%M%p")
            et = date_parser.parse(r["attributes"]["end_time"]).strftime("%-I:%M%p")
            presenter = self._site.get_user(rels["presenter"]["data"]["id"])
            me = presenter["attributes"]["name"]

            # For transitional - use taxon1 as a 'header'
            title = "unk"
            if rels["taxon1"]["data"]:
                taxon1 = self._site.get_taxonomy(rels["taxon1"]["data"]["type"])
                taxon1_names = [
                    t["name"] for t in taxon1 if t["id"] == rels["taxon1"]["data"]["id"]
                ]
                if taxon1_names:
                    title = taxon1_names[0]

            # For transitional - use taxon1 as a 'header'
            if title not in atinfo:
                atinfo[title] = []
            atinfo[title].append(dict(who=[me], time=f"{st}-{et}"))
        return atinfo
