#!/usr/bin/env python
#
# Copyright (C) 2020 Erlend Ekern <dev@ekern.me>
#
# Distributed under terms of the MIT license.

"""
Unit-tests for pytest.
"""
import json
import os
import sys
import boto3
import pytest
from botocore.stub import Stubber
from unittest.mock import patch, MagicMock

import main


def test_read_json_from_s3_should_raise_exception_if_missing_keys(
    s3_resource_stub,
):
    expected_keys = {"expected_key": 123}
    expected_result = {"hello": 123}
    body = MagicMock()
    body.read.return_value.decode.return_value = json.dumps(expected_result)

    expected_params = {"Bucket": "bucket", "Key": "key"}
    s3_resource_stub.add_response(
        "get_object",
        expected_params=expected_params,
        service_response={"Body": body},
    )
    with pytest.raises(LookupError):
        main.read_json_from_s3(
            expected_params["Bucket"], expected_params["Key"], expected_keys
        )


def test_read_json_from_s3_should_raise_exception_on_non_serialized_dict(
    s3_resource_stub,
):
    expected_result = {"hello": "test"}
    expected_params = {"Bucket": "bucket", "Key": "test"}
    body = MagicMock()
    body.read.return_value.decode.return_value = expected_result

    s3_resource_stub.add_response(
        "get_object",
        expected_params=expected_params,
        service_response={"Body": body},
    )
    with pytest.raises(TypeError):
        main.read_json_from_s3(
            expected_params["Bucket"], expected_params["Key"]
        )


def test_read_json_from_s3_should_raise_exception_on_non_serialized_str(
    s3_resource_stub,
):
    expected_result = "hello"
    expected_params = {"Bucket": "bucket", "Key": "test"}
    body = MagicMock()
    body.read.return_value.decode.return_value = expected_result

    s3_resource_stub.add_response(
        "get_object",
        expected_params=expected_params,
        service_response={"Body": body},
    )
    with pytest.raises(json.decoder.JSONDecodeError):
        main.read_json_from_s3(
            expected_params["Bucket"], expected_params["Key"]
        )


def test_extract_data_from_s3_key_should_return_empty_dict():
    s3_key = "nsbno/trafficgui-aws/master/trigger-event.json"
    groups = main.extract_data_from_s3_key(s3_key)
    assert groups == {}


def test_extract_data_from_s3_key_should_return_full_dict():
    expected_result = {
        "gh_org": "nsbno",
        "gh_repo": "trafficgui-aws",
        "gh_branch": "master",
        "s3_filename": "trigger-event.json",
    }
    s3_key = (
        f"{expected_result['gh_org']}/{expected_result['gh_repo']}"
        f"/branches/{expected_result['gh_branch']}"
        f"/{expected_result['s3_filename']}"
    )
    groups = main.extract_data_from_s3_key(s3_key)
    assert groups == expected_result


def test_extract_data_from_s3_key_should_handle_branch_name_with_slash():
    expected_result = {
        "gh_org": "nsbno",
        "gh_repo": "trafficgui-aws",
        "gh_branch": "fix/fix-the-bug",
        "s3_filename": "trigger-event.json",
    }
    s3_key = (
        f"{expected_result['gh_org']}/{expected_result['gh_repo']}"
        f"/branches/{expected_result['gh_branch']}"
        f"/{expected_result['s3_filename']}"
    )
    groups = main.extract_data_from_s3_key(s3_key)
    assert groups == expected_result
