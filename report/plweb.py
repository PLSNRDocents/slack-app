# Copyright 2019-2020 by J. Christopher Wagner (jwag). All rights reserved.

import logging

from bs4 import BeautifulSoup
from dateutil import parser as date_parser
import requests

from exc import ParseError

VERBOSE = 0

IDX_TO_TIME = ["label", "9-11", "11-1", "1-3", "3-5"]


class Plweb:
    def __init__(self, config):
        self._logger = logging.getLogger(__name__)
        self.username = config["PLSNR_USERNAME"]
        self.password = config["PLSNR_PASSWORD"]
        self.server_url = config["PLSNR_HOST"]
        self.session = requests.session()
        self.session.verify = config["SSL_VERIFY"]

    def login(self):
        rv = self.session.get("{url}".format(url=self.server_url))
        hc = BeautifulSoup(rv.text, features="html.parser")
        form_info = self.parse_form_data(hc, ["form_build_id", "form_id"])
        form_data = {
            "name": self.username,
            "pass": self.password,
            "op": "Log in",
            "form_build_id": form_info["form_build_id"],
            "form_id": form_info["form_id"],
        }
        # this should fill cookie jar
        self._logger.info("Logging into plweb site as user {}".format(self.username))
        rv = self.session.post(
            "{url}".format(url=self.server_url),
            data=form_data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "*/*",
            },
            allow_redirects=False,
        )
        rv.raise_for_status()
        return False

    @staticmethod
    def parse_form_data(hc: BeautifulSoup, needed=None):
        if not needed:
            needed = ["form_build_id", "form_token", "form_id"]
        _form_info = hc.find_all("input")
        _special_info = {}
        for fi in _form_info:
            if fi.get("name", "") in needed:
                if VERBOSE:
                    print(
                        "Found form info {} value {}".format(
                            fi.get("name"), fi.get("value")
                        )
                    )
                _special_info[fi.get("name")] = fi.get("value")
        if len(_special_info) != len(needed):
            raise ValueError("Need 3 pieces of form data")
        return _special_info

    def at_station(self, page, when):
        """ Returns a list:
        [{
            "time": <time>,
            "who": [<list of who>]
         }, ...
        ]
        """
        # This assumes date of form YYYYMMDD
        dom = str(int(when[6:]))
        hc = BeautifulSoup(page, features="html.parser")

        # start by looking for correct month (this is an issue due to current web
        # not handling timezones correctly.
        rmonth = date_parser.parse(when).strftime("%B")
        cmonths = hc.find_all("table", class_="calendar-month")
        for month in cmonths:
            # Look for title.
            title = month.find_all("span", class_="cal-section")
            if rmonth in title[0].text:
                # This is the correct one

                shift_days = month.find_all("td", class_="shift-day")
                for shift in shift_days:
                    cd = shift.find_all("table", class_="calendar-day")
                    rows = cd[0].find_all("tr")
                    date_labels = rows[0].find_all("div", class_="label-date")
                    # mostly text is just 'dd' - but for 'at_station' it is '*dd*'
                    rdom = date_labels[0].text.strip("*")
                    if dom == rdom:
                        # This is us.
                        ans = []
                        if len(rows) != 5:
                            raise ParseError(
                                "{} rows in at_station table".format(len(rows))
                            )
                        for idx, row_data in enumerate(rows):
                            if idx > 0:
                                # Each row has one or more <span>
                                who = [s.text for s in row_data.find_all("span")]
                                ans.append({"time": IDX_TO_TIME[idx], "who": who})
                        return ans

    @staticmethod
    def _gettime(d):
        """ Parse time div
        Public-Walks time is: <div><strong>9:30am</strong></div>
        Interp time is: <div><strong><time datetime="00Z">9:15am</time>
                         - <time datetime="00Z">11:15am</time>
        Docent Activity: <div><time datetime="00Z">9:30am</time></div>
        """
        times = d.find_all("time")
        if len(times) == 2:
            t = "{} - {}".format(times[0].text, times[1].text)
        elif len(times) == 1:
            t = times[0].text
        else:
            t = d.text
        return t

    def at_pw(self, page, when):
        """ Public Walks and Interp (gate greet) Calendar.
        Returns a list:
        [{
            "time": <time>,
            "title": <title>,
            "who": [<list of who>]
         }, ...
        ]
        """
        dom = str(int(when[6:]))
        hc = BeautifulSoup(page, features="html.parser")
        days = hc.find_all("td", class_="single-day")
        walks = []
        for day in days:
            if day["data-day-of-month"] == dom:
                info = day.find_all("div", class_="contents")
                if info:
                    walks.extend(info)
        if not walks:
            return []
        ans = []
        # There seem to be 3 divs: time, title, who
        for w in walks:
            a = {}
            info = w.find_all("div")
            a["time"] = Plweb._gettime(info[0])
            a["title"] = info[1].text
            # <div>led by <a href="/users/f-brown" hreflang="en">Fred Brown</a> </div>
            a["who"] = [info[2].contents[1].text]
            ans.append(a)
        return ans

    def at_activities(self, page, when):
        """ Docent Activities Calendar.
        Returns a list:
        [{
            "time": <time>,
            "title": <title>,
            "who": [<list of who>]
         }, ...
        ]
        """
        dom = str(int(when[6:]))
        hc = BeautifulSoup(page, features="html.parser")
        days = hc.find_all("td", class_="single-day")
        walks = []
        for day in days:
            if day["data-day-of-month"] == dom:
                info = day.find_all("div", class_="contents")
                if info:
                    walks.extend(info)
        if not walks:
            return []
        ans = []
        # There seem to be 4 divs: title/link, time
        # We need to look up the link to find out who
        for w in walks:
            a = {}
            info = w.find_all("div")
            link = info[0].contents[0]
            rv = self.session.get(
                "{url}{ep}".format(url=self.server_url, ep=link.get("href"))
            )
            rv.raise_for_status()
            signups = Plweb._get_whoall(rv.text)
            if signups:
                a["time"] = Plweb._gettime(info[1])
                a["title"] = link.text
                a["who"] = signups
                ans.append(a)
        return ans

    @staticmethod
    def _get_whoall(page):
        hc = BeautifulSoup(page, features="html.parser")
        whoall = []

        # look for presenters
        pdiv = hc.find_all("div", class_="field--name-field-presented-by")
        if pdiv:
            whoall.append(pdiv[0].find("div", class_="field--item").text)

        # look for signups
        tables = hc.find_all("table")
        for table in tables:
            try:
                title = table.thead.tr.th.text
                if "Signups" in title:
                    for row in table.find_all("td", class_="views-field-uid"):
                        whoall.append(row.a.text)

            except Exception:
                pass

        return whoall

    def whoat(self, when, where="all"):
        """
        Get info on who is where by querying calendars.
        If 'where' is None - try to find everything going on.
        Works for 'at_station' only.
        The 'when' argument is needed for proper caching - and should be
        unique for the day - e.g. 20191001
        """

        locations = {
            "info": {
                "title": "Info-Station",
                "cal_url": "schedule/info-station",
                "has_month": False,
                "parser": "at_station",
            },
            "whalers": {
                "title": "Whaler's Cabin",
                "cal_url": "schedule/whalers-cabin",
                "has_month": False,
                "parser": "at_station",
            },
            "public": {
                "title": "Public Walks",
                "cal_url": "schedule/public-walks/month",
                "has_month": True,
                "parser": "at_pw",
            },
            "gate": {
                "title": "Gate Greet/Scoping/Pup",
                "cal_url": "schedule/interpretive-duty/month",
                "has_month": True,
                "parser": "at_pw",
            },
            "other": {
                "title": "Other Activities",
                "cal_url": "community/activities/month",
                "has_month": True,
                "parser": "at_activities",
            },
        }
        if where == "all":
            where = ["info", "whalers", "public", "gate", "other"]
        elif not isinstance(where, list):
            if where.startswith("info"):
                where = ["info"]
            elif where.startswith("whaler"):
                where = ["whalers"]
            elif where.startswith("pub"):
                where = ["public"]
            elif (
                where.startswith("gate")
                or where.startswith("scope")
                or where.startswith("pup")
            ):
                where = ["gate"]
            elif (
                where.startswith("mint")
                or where.startswith("school")
                or where.startswith("other")
            ):
                where = ["other"]
            else:
                raise ParseError("Unknown where: {}", format(where))

        ans = {}
        for w in where:
            info = locations[w]
            cal_url = info["cal_url"]
            if info["has_month"]:
                cal_url += "/{}".format(when[0:6])
            self._logger.info("Fetching {} calendar".format(cal_url))
            rv = self.session.get("{url}/{ep}".format(url=self.server_url, ep=cal_url))
            if rv.status_code == 403:
                # need to log in.
                self._logger.info(
                    "Logging in to PLSNR web site {}".format(self.server_url)
                )
                self.login()
                rv = self.session.get(
                    "{url}/{ep}".format(url=self.server_url, ep=cal_url)
                )
            rv.raise_for_status()
            ans[info["title"]] = getattr(self, info["parser"])(rv.text, when)
        return ans
