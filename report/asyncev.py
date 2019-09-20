# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import asyncio

event_loop = asyncio.new_event_loop()


def run_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()
