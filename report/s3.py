# Copyright 2016-2019 by J. Christopher Wagner (jwag). All rights reserved.

"""
Storage handler for S3 storage
"""

import uuid

import boto3
import boto3.s3.transfer
from botocore.exceptions import ClientError
import botocore
import botocore.config
import flask
import logging

import exc


class S3Storage(object):
    def __init__(self, config):
        self._config = config
        self._logger = logging.getLogger(__name__)
        if config.get("AWS_PROFILE", None):
            self._session = boto3.Session(profile_name=config["AWS_PROFILE"])
        else:
            self._session = boto3.Session()
        # Default retries is 4 - and default timout is 60 seconds -
        # that seems way to long.
        self._botoconfig = botocore.config.Config(connect_timeout=10)

    def init(self):
        if self._config["S3_VERIFY_BUCKET"]:
            # Make sure bucket exists
            s3 = self._session.resource("s3", config=self._botoconfig)
            try:
                self._logger.info(
                    "Creating/verifying S3 bucket {}".format(self._config["S3_BUCKET"])
                )
                s3.create_bucket(Bucket=self._config["S3_BUCKET"])
            except Exception as ex:
                if isinstance(ex, ClientError):
                    # ignore if already present
                    if ex.response["ResponseMetadata"]["HTTPStatusCode"] == 409:
                        return
                self._logger.info(
                    "Failed to init/verify bucket: %s failed: %s",
                    self._config["S3_BUCKET"],
                    ex,
                )
                raise exc.S3Error(
                    "Failed to init/verify bucket {}: {}".format(
                        self._config["S3_BUCKET"], ex
                    )
                )

    def delete(self, path, rid):
        self._logger.info("Trying to delete: %s for report: %s", path, rid)

        try:
            s3 = self._session.resource("s3", config=self._botoconfig)
            s3.Object(self._config["S3_BUCKET"], path).delete()
        except Exception as ex:
            self._logger.warning(
                "Could not delete: %s from bucket: %s for report: %s reason: %s",
                path,
                self._config["S3_BUCKET"],
                rid,
                ex,
            )

    def save(self, local_name, ext, content_type, rid):
        base_name = "{}_{}.{}".format(rid, uuid.uuid4(), ext)

        try:
            s3 = self._session.resource("s3", config=self._botoconfig)
            with open(local_name, "rb") as f:
                bucket = s3.Bucket(self._config["S3_BUCKET"])
                bucket.put_object(
                    Key=base_name, Body=f, ContentType=content_type, ACL="public-read"
                )
        except Exception as ex:
            self._logger.error(
                "Failed to save %s for report: %s error: %s", base_name, rid, ex
            )
            raise exc.S3Error("Failed to save image {}: {}".format(base_name, ex))

        return {
            "path": base_name,
            "s3bucket": self._config["S3_BUCKET"],
            "content_type": content_type,
        }

    def fetch(self, location_info) -> flask.Response:
        """ get an image
        N.B. Must be called in the context of a flask Request
        :param location_info:
        :return: Flask Resource object
        """

        s3kwargs = {}
        ims_date = flask.request.if_modified_since
        if ims_date:
            s3kwargs["IfModifiedSince"] = ims_date
        s3 = self._session.resource("s3", config=self._botoconfig)
        try:
            s3file = s3.Object(location_info["s3bucket"], location_info["path"]).get(
                **s3kwargs
            )
        except Exception as ex:
            self._logger.info(
                "S3 Key: %s Bucket: %s failed: %s",
                location_info["path"],
                location_info["s3bucket"],
                ex,
            )
            if isinstance(ex, ClientError):
                if ex.response["ResponseMetadata"]["HTTPStatusCode"] == 304:
                    return flask.Response(status=304)
            raise exc.S3Error(
                "Failed to fetch image {}: {}".format(location_info["path"], ex)
            )

        # we could use S3file['ContentType'] as well
        resp = flask.Response(
            iter(lambda: s3file["Body"].read(256 * 1024), b""),
            mimetype=location_info["content_type"],
        )
        resp.cache_control.no_transform = True
        resp.cache_control.public = True
        resp.content_length = s3file["ContentLength"]
        resp.last_modified = s3file["LastModified"]
        resp.cache_control.max_age = self._config["SEND_FILE_MAX_AGE_DEFAULT"]

        return resp

    def fetch_local(self, location_info, tmp_file):
        s3 = self._session.resource("s3", config=self._botoconfig)
        try:
            self._logger.info(
                "Fetching {}:{} to local file {}".format(
                    location_info["s3bucket"], location_info["path"], tmp_file.name
                )
            )
            s3object = s3.Object(location_info["s3bucket"], location_info["path"])
            s3object.download_fileobj(
                tmp_file,
                Config=boto3.s3.transfer.TransferConfig(
                    max_concurrency=2, max_io_queue=10
                ),
            )
            tmp_file.flush()
        except Exception as ex:
            self._logger.info(
                "S3 Key: %s Bucket: %s failed: %s",
                location_info["path"],
                location_info["s3bucket"],
                ex,
            )
            raise exc.S3Error(
                "Failed to fetch image {}: {}".format(location_info["path"], ex)
            )
