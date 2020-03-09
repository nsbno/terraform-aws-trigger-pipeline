#!/usr/bin/env python
#
# Copyright (C) 2020 Erlend Ekern <dev@ekern.me>
#
# Distributed under terms of the MIT license.

"""

"""

import boto3
import os
import pytest
from botocore.stub import Stubber
from unittest.mock import patch


@pytest.fixture(autouse=True)
def aws_credentials():
    """Mocked AWS Credentials."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ.pop("AWS_PROFILE", None)


@pytest.fixture(autouse=True)
def s3_stub(aws_credentials):
    s3 = boto3.client("s3")

    def patch_wrapper(*args, **kwargs):
        return s3

    with patch("main.boto3.client", patch_wrapper):
        with Stubber(s3) as stub:
            yield stub
            stub.assert_no_pending_responses()


@pytest.fixture(autouse=True)
def s3_resource_stub(aws_credentials):
    s3 = boto3.resource("s3")
    client = s3.meta.client

    def patch_wrapper(*args, **kwargs):
        return s3

    with patch("main.boto3.resource", patch_wrapper):
        with Stubber(client) as stub:
            yield stub
            stub.assert_no_pending_responses()
