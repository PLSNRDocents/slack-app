# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging
import os


from bs4 import BeautifulSoup
import requests

from exc import ParseError

URL = "https://docents.plsnr.org"
VERBOSE = 0
SESSION = requests.session()

logger = logging.getLogger(__name__)


IDX_TO_TIME = ["label", "9-11", "11-1", "1-3", "3-5"]


def get_session():
    return SESSION


def login(username, password):
    rv = get_session().get("{url}".format(url=URL, name=username))
    hc = BeautifulSoup(rv.text, features="html.parser")
    form_info = parse_form_data(hc, ["form_build_id", "form_id"])
    form_data = {
        "name": username,
        "pass": password,
        "op": "Log in",
        "form_build_id": form_info["form_build_id"],
        "form_id": form_info["form_id"],
    }
    # this should fill cookie jar
    rv = get_session().post(
        "{url}".format(url=URL),
        data=form_data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "*/*"},
        allow_redirects=False,
    )
    rv.raise_for_status()


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


def today(page):
    """ Returns a list:
    [{
        "time": <time>,
        "who": [<list of who>]
     }, ...
    ]
    """
    hc = BeautifulSoup(page, features="html.parser")
    shift_days = hc.find_all("td", class_="shift-day")
    for shift in shift_days:
        # look for one 'day-today'
        dt = shift.find_all("table", class_="day-today")
        if dt:
            # there should be 5 rows - first is label
            ans = []
            rows = dt[0].find_all("tr")
            if len(rows) != 5:
                raise ParseError("{} rows in today table".format(len(rows)))
            for idx, row_data in enumerate(rows):
                if idx > 0:
                    # Each row has one or more <span>
                    who = [s.text for s in row_data.find_all("span")]
                    ans.append({"time": IDX_TO_TIME[idx], "who": who})
            return ans


def whoat(where=None):
    """
    Get info on who is where by querying calendars.
    If 'where' is None - try to find everything going on.
    Works for 'today' only.
    """
    if not where:
        where = ["info", "whalers"]
    elif not isinstance(where, list):
        where = [where]

    ans = {}
    for w in where:
        if w.startswith("info"):
            loc = "Info-Station"
            ep = "schedule/info-station"
        elif w.startswith("whaler"):
            loc = "Whaler's Cabin"
            ep = "schedule/whalers-cabin"
        else:
            raise ParseError("Unknown where: {}", format(w))

        rv = get_session().get("{url}/{ep}".format(url=URL, ep=ep))
        if rv.status_code == 403:
            # need to log in.
            logger.info("Logging in to PLSNR web site")
            login(os.environ["PLSNR_USERNAME"], os.environ["PLSNR_PASSWORD"])
            rv = get_session().get("{url}/{ep}".format(url=URL, ep=ep))
        rv.raise_for_status()
        ans[loc] = today(rv.text)
    return ans
