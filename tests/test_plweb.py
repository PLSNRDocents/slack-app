# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import os

import plweb


def test_today():
    with open(os.path.join(os.path.dirname(__file__), "data/info.html")) as fp:
        page = fp.read()
        ans = plweb.at_station(page, "20191022")
        assert len(ans) == 4
        assert ans[3] == {"time": "3-5", "who": ["R Henry"]}


def test_anyday():
    with open(os.path.join(os.path.dirname(__file__), "data/info.html")) as fp:
        page = fp.read()
        ans = plweb.at_station(page, "20191002")
        assert len(ans) == 4
        assert ans[3] == {"time": "3-5", "who": ["D Turner"]}


def test_today_tz():
    with open(
        os.path.join(os.path.dirname(__file__), "data/whalers-tz-error.html")
    ) as fp:
        page = fp.read()
        ans = plweb.at_station(page, "20191022")
        assert len(ans) == 4
        assert ans[3] == {"time": "3-5", "who": ["K Armstrong"]}


def test_tomorrow():
    with open(os.path.join(os.path.dirname(__file__), "data/info.html")) as fp:
        page = fp.read()
        ans = plweb.at_station(page, "20191023")
        assert len(ans) == 4
        assert ans[3] == {"time": "3-5", "who": ["C Mattos"]}


def test_pw():
    with open(os.path.join(os.path.dirname(__file__), "data/public_walks.html")) as fp:
        page = fp.read()
        ans = plweb.at_pw(page, "20190927")
        assert len(ans) == 1


def test_interp():
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

    with open(
        os.path.join(os.path.dirname(__file__), "data/activity_detail.html")
    ) as fp:
        requests_mock.get("{}/node/111772".format(plweb.URL), text=fp.read())
    with open(
        os.path.join(os.path.dirname(__file__), "data/node111803_detail.html")
    ) as fp:
        requests_mock.get("{}/node/111803".format(plweb.URL), text=fp.read())

    with open(os.path.join(os.path.dirname(__file__), "data/mint.html")) as fp:
        page = fp.read()
        ans = plweb.at_activities(page, "20190928")
        assert len(ans) == 2
        assert ans[0]["who"] == ["Chris Wagner"]
        assert ans[1]["time"] == "4:00pm"
