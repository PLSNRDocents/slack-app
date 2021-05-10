# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import os

from plweb import Plweb

CONFIG = dict(
    PLSNR_USERNAME="me",
    PLSNR_PASSWORD="pass",
    PLSNR_HOST="http://localhost",
    SSL_VERIFY=True,
)


def test_today():
    plweb = Plweb(CONFIG)
    with open(os.path.join(os.path.dirname(__file__), "data/info.html")) as fp:
        page = fp.read()
        ans = plweb.at_station(page, "20191022")
        assert len(ans) == 4
        assert ans[3] == {"time": "3-5", "who": ["R Henry"]}


def test_today_bom():
    """Current website doesn't handle timezones and there end of month
    well - so early on the First - it still shows last month first.
    Also - this makes 'tomorrow' work across months."""
    plweb = Plweb(CONFIG)
    with open(os.path.join(os.path.dirname(__file__), "data/info-dec1.html")) as fp:
        page = fp.read()
        ans = plweb.at_station(page, "20191201")
        assert len(ans) == 4
        assert ans[3] == {"time": "3-5", "who": ["B Boles", "KA Ryan"]}


def test_anyday():
    plweb = Plweb(CONFIG)
    with open(os.path.join(os.path.dirname(__file__), "data/info.html")) as fp:
        page = fp.read()
        ans = plweb.at_station(page, "20191002")
        assert len(ans) == 4
        assert ans[3] == {"time": "3-5", "who": ["D Turner"]}


def test_today_tz():
    plweb = Plweb(CONFIG)
    with open(
        os.path.join(os.path.dirname(__file__), "data/whalers-tz-error.html")
    ) as fp:
        page = fp.read()
        ans = plweb.at_station(page, "20191022")
        assert len(ans) == 4
        assert ans[3] == {"time": "3-5", "who": ["K Armstrong"]}


def test_tomorrow():
    plweb = Plweb(CONFIG)
    with open(os.path.join(os.path.dirname(__file__), "data/info.html")) as fp:
        page = fp.read()
        ans = plweb.at_station(page, "20191023")
        assert len(ans) == 4
        assert ans[3] == {"time": "3-5", "who": ["C Mattos"]}


def test_pw():
    plweb = Plweb(CONFIG)
    with open(os.path.join(os.path.dirname(__file__), "data/public_walks.html")) as fp:
        page = fp.read()
        ans = plweb.at_pw(page, "20190927")
        assert len(ans) == 1


def test_interp():
    plweb = Plweb(CONFIG)
    with open(os.path.join(os.path.dirname(__file__), "data/interp.html")) as fp:
        page = fp.read()
        ans = plweb.at_pw(page, "20190913")
        assert len(ans) == 2
        assert ans[1] == {
            "time": "1:00pm - 3:00pm",
            "title": "Scoping at Sea Lion Point Trail",
            "who": ["Geoffrey Bromfield"],
        }


def test_mint(requests_mock):
    plweb = Plweb(CONFIG)
    with open(
        os.path.join(os.path.dirname(__file__), "data/activity_detail.html")
    ) as fp:
        requests_mock.get("{}/node/111772".format("http://localhost"), text=fp.read())
    with open(
        os.path.join(os.path.dirname(__file__), "data/node111803_detail.html")
    ) as fp:
        requests_mock.get("{}/node/111803".format("http://localhost"), text=fp.read())

    with open(os.path.join(os.path.dirname(__file__), "data/mint.html")) as fp:
        page = fp.read()
        ans = plweb.at_activities(page, "20190928")
        assert len(ans) == 2
        assert ans[0]["who"] == ["Chris Wagner"]
        assert ans[1]["time"] == "4:00pm"
        assert len(ans[1]["who"]) == 8
