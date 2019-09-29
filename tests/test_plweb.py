# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import os

import plweb


def test_today_pw():
    with open(os.path.join(os.path.dirname(__file__), "data/public_walks.html")) as fp:
        page = fp.read()
        ans = plweb.today_pw(page)
        assert len(ans) == 1


def test_today_interp():
    with open(os.path.join(os.path.dirname(__file__), "data/interp.html")) as fp:
        page = fp.read()
        ans = plweb.today_pw(page)
        assert len(ans) == 2


def test_today_mint(requests_mock):

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
        ans = plweb.today_activities(page)
        assert len(ans) == 2
        assert ans[0]["who"] == ["Chris Wagner"]
        assert ans[1]["time"] == "4:00pm"
