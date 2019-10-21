# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging
import os


from bs4 import BeautifulSoup
from cachetools import cached, keys, TTLCache
import requests

from exc import ParseError

URL = "https://docents.plsnr.org"
VERBOSE = 0
SESSION = requests.session()

logger = logging.getLogger(__name__)

whoat_cache = TTLCache(maxsize=128, ttl=60 * 60)


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


def _gettime(d):
    """ Parse time div
    Public-Walks time is: <div><strong>9:30am</strong></div>
    Interp time is: <div><strong><time datetime="00Z">9:15am</time>
                     - <time datetime="00Z">11:15am</time>
    Docent Activitiy: <div><time datetime="00Z">9:30am</time></div>
    """
    times = d.find_all("time")
    if len(times) == 2:
        t = "{} - {}".format(times[0].text, times[1].text)
    elif len(times) == 1:
        t = times[0].text
    else:
        t = d.text
    return t


def today_pw(page):
    """ Public Walks and Interp (gate greet) Calendar.
    Returns a list:
    [{
        "time": <time>,
        "title": <title>,
        "who": [<list of who>]
     }, ...
    ]
    """
    hc = BeautifulSoup(page, features="html.parser")
    todays = hc.find_all("td", class_="today")
    walks = []
    # There will be 2 todays - one is the title...
    for td in todays:
        info = td.find_all("div", class_="contents")
        if info:
            walks.extend(info)
    if not walks:
        return []
    ans = []
    # There seem to be 3 divs: time, title, who
    for w in walks:
        a = {}
        info = w.find_all("div")
        a["time"] = _gettime(info[0])
        a["title"] = info[1].text
        # <div>led by <a href="/users/f-brown" hreflang="en">Fred Brown</a> </div>
        a["who"] = [info[2].contents[1].text]
        ans.append(a)
    return ans


def today_activities(page):
    """ Docent Activities Calendar.
    Returns a list:
    [{
        "time": <time>,
        "title": <title>,
        "who": [<list of who>]
     }, ...
    ]
    """
    hc = BeautifulSoup(page, features="html.parser")
    todays = hc.find_all("td", class_="today")
    walks = []
    # There will be 2 todays - one is the title...
    for td in todays:
        info = td.find_all("div", class_="contents")
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
        a["time"] = _gettime(info[1])
        link = info[0].contents[0]
        a["title"] = link.text
        rv = get_session().get("{url}{ep}".format(url=URL, ep=link.get("href")))
        rv.raise_for_status()
        a["who"] = [_get_presenter(rv.text)]
        ans.append(a)
    return ans


def _get_presenter(page):
    hc = BeautifulSoup(page, features="html.parser")
    pdiv = hc.find_all("div", class_="field--name-field-presented-by")
    presenter = ""
    if pdiv:
        presenter = pdiv[0].find("div", class_="field--item").text
    return presenter


@cached(whoat_cache)
def whoat(when, where=None):
    """
    Get info on who is where by querying calendars.
    If 'where' is None - try to find everything going on.
    Works for 'today' only.
    The 'when' argument is needed for proper caching - and should be
    unique for the day - e.g. 20191001
    """

    locations = {
        "info": {
            "title": "Info-Station",
            "cal_url": "schedule/info-station",
            "parser": today,
        },
        "whalers": {
            "title": "Whaler's Cabin",
            "cal_url": "schedule/whalers-cabin",
            "parser": today,
        },
        "public": {
            "title": "Public Walks",
            "cal_url": "schedule/public-walks/month",
            "parser": today_pw,
        },
        "gate": {
            "title": "Gate Greet/Scoping/Pup",
            "cal_url": "schedule/interpretive-duty/month",
            "parser": today_pw,
        },
        "other": {
            "title": "Other Activities",
            "cal_url": "community/activities/month",
            "parser": today_activities,
        },
    }
    if not where:
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
        logger.info("Fetching {} calendar".format(info["cal_url"]))
        rv = get_session().get("{url}/{ep}".format(url=URL, ep=info["cal_url"]))
        if rv.status_code == 403:
            # need to log in.
            logger.info("Logging in to PLSNR web site")
            login(os.environ["PLSNR_USERNAME"], os.environ["PLSNR_PASSWORD"])
            rv = get_session().get("{url}/{ep}".format(url=URL, ep=info["cal_url"]))
        rv.raise_for_status()
        ans[info["title"]] = info["parser"](rv.text)
    return ans


def cached_whoat(when, where=None):
    return keys.hashkey(when, where) in whoat_cache
