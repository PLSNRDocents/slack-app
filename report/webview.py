# Copyright 2019 by J. Christopher Wagner (jwag). All rights reserved.

import logging

from flask import request, redirect, url_for
from flask_admin.model import BaseModelView
from flask_admin.model.filters import BaseFilter
from flask_login import current_user
from wtforms import Form, StringField

from dynamo import Report, ReportModel, attr_to_display


logger = logging.getLogger("webview")

"""
class DDBBaseFilter(BaseFilter):
    def __init__(self, name, options=None, data_type=None):
        super().__init__(name, options, data_type)


class DDBTextContainsFilter(DDBBaseFilter):
    def apply(self, fexp, value):
        # Add onto filter expression
        if fexp:
            return fexp & Attr(self.name).contains(value)
        return Attr(self.name).contains(value)

    def operation(self):
        return "contains"
"""


class InMemoryBaseFilter(BaseFilter):
    def __init__(self, name, options=None, data_type=None):
        super().__init__(name, options, data_type)


class InMemoryTextContainsFilter(InMemoryBaseFilter):
    def apply(self, record, value):
        # This isn't quite what flask-admin had in mind - we are
        # doing in-place filtering after all results have been returned.
        # So we get the record and return True if it matches filter.
        av = attr_to_display(record, self.name)
        return value.casefold() in av.casefold()

    def operation(self):
        return "contains"


class DDBModelView(BaseModelView):
    def __init__(self, report: Report, *args, **kwargs):
        super().__init__(ReportModel, *args, **kwargs)
        self._report = report

    def get_pk_value(self, model: ReportModel):
        return model.id

    def scaffold_list_columns(self):
        columns = ReportModel.field_list()
        return columns

    def scaffold_sortable_columns(self):
        return dict(
            location="location",
            issues="issues",
            kiosk_called="kiosk_called",
            id="id",
            update_datetime="update_datetime",
        )

    def scaffold_form(self):
        class ReportForm(Form):
            id = StringField(label="Report id")

        return ReportForm

    def scaffold_list_form(self, widget=None, validators=None):
        return None

    def scaffold_filters(self, name):
        if name in ["location", "issues", "reporter", "kiosk_called"]:
            return [InMemoryTextContainsFilter(name)]

    def init_search(self):
        return False

    def get_list(self, page, sort_field, sort_desc, search, filters, page_size=None):
        # In memory filters.
        raw_reports = self._report.fetch(
            limit=page_size, filters=self._report.REAL_REPORT_FILTER
        )
        reports = []
        for r in raw_reports:
            if filters:
                filter_rv = []
                for idx, flt, value in filters:
                    # Only support AND
                    filter_rv.append(self._filters[idx].apply(r, value))
                if all(filter_rv):
                    reports.append(r)
            else:
                reports.append(r)
        # now sort
        if sort_field:
            reports = sorted(
                reports,
                key=lambda rec: attr_to_display(rec, sort_field),
                reverse=sort_desc,
            )
        logging.info(
            "Retrieved {} records filtered to {}".format(len(raw_reports), len(reports))
        )
        return len(reports), reports

    def get_one(self, rid):
        return self._report.get(rid)


def _fmtdate(view, context, model, name):
    return getattr(model, name).strftime("%b %-d %Y at %-H:%M")


class ReportModelView(DDBModelView):
    can_create = False
    can_edit = False
    can_delete = False
    can_export = True
    can_set_page_size = True

    column_list = (
        "id",
        "type",
        "issues",
        "location",
        "cross_trail",
        "create_datetime",
        "update_datetime",
        "status",
        "reporter",
        "gps",
        "kiosk_called",
        "kiosk_resolution",
        "details",
        "photos",
    )
    column_exclude_list = {
        "create_ts",
        "update_ts",
        "reporter_slack_id",
        "reporter_slack_handle",
        "allreports",
        "channel",
    }

    column_formatters = dict(
        create_datetime=_fmtdate,
        update_datetime=_fmtdate,
        location=lambda v, c, m, p: attr_to_display(m, "location"),
        cross_trail=lambda v, c, m, p: attr_to_display(m, "cross_trail"),
        issues=lambda v, c, m, p: attr_to_display(m, "issues"),
        photos=lambda v, c, m, p: "{} photo(s)".format(len(m.photos))
        if m.photos
        else None,
    )
    column_filters = ["location", "issues", "reporter", "kiosk_called"]

    def __init__(self, report, *args, **kwargs):
        super().__init__(report, *args, **kwargs)

    def is_accessible(self):
        return current_user.is_authenticated

    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("admin.login_view", next=request.url))
