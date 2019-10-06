# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

from app import create_app
import asyncev

app = create_app()

asyncev.wapp = app
