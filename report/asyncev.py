# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Async handler.

There are 2 models - event_loop (local) and zappa (AWS).
"""

import logging

import asyncio

from zappa.asynchronous import run

event_loop = asyncio.new_event_loop()

wapp = None

logger = logging.getLogger(__name__)


def run_loop(loop):
    """Just used in local development (not lambda)"""
    asyncio.set_event_loop(loop)
    loop.run_forever()


def run_async(mode, func, *args, **kwargs):
    if mode == "ev":
        event_loop.call_soon_threadsafe(func, *args)
    else:
        run(func, args, kwargs)
