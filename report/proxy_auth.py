# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.


"""
Use Flask-Login to provide auth via logging in to plweb site.
"""
import logging
import requests

from flask import url_for, redirect, request
import flask_admin
from flask_admin import helpers, expose
import flask_login
from flask_wtf import FlaskForm
from wtforms import fields, validators

from plweb import login as plweb_login

logger = logging.getLogger("proxy-auth")

proxy_session = requests.session()


class User(flask_login.UserMixin):
    id = 0
    pass


class LoginForm(FlaskForm):
    login = fields.StringField(validators=[validators.required()])
    password = fields.PasswordField(validators=[validators.required()])

    def validate(self):
        if not super(LoginForm, self).validate():
            return False

        # verify with plweb
        try:
            if not plweb_login(proxy_session, self.login.data, self.password.data):
                self.login.errors = ["Incorrect Credentials"]
                return False
        except Exception as exc:
            logger.info("Failed to authenticate {}: {}".format(self.login, exc))
            return False
        return True


def init_login(app):
    login_manager = flask_login.login_manager.LoginManager()
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        user = User()
        user.id = user_id
        return user


# Create customized index view class that handles login
class PLAdminIndexView(flask_admin.AdminIndexView):
    @expose("/")
    def index(self):
        if not flask_login.current_user.is_authenticated:
            return redirect(url_for(".login_view"))
        return super(PLAdminIndexView, self).index()

    @expose("/login/", methods=("GET", "POST"))
    def login_view(self):
        # handle user login
        form = LoginForm(request.form)
        if helpers.validate_form_on_submit(form):
            user = User()
            user.id = form.login
            flask_login.login_user(user)

        if flask_login.current_user.is_authenticated:
            return redirect(url_for(".index"))
        self._template_args["form"] = form
        return super(PLAdminIndexView, self).index()

    @expose("/logout/")
    def logout_view(self):
        flask_login.logout_user()
        return redirect(url_for(".index"))
