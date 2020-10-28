import json
import boto3
import time
import logging
import os
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def extract_data_from_s3_key(s3_key):
    """Extracts various values from an S3 key.

    Args:
        s3_key: The S3 key of the file that triggered the pipeline.

    Returns:
        A dictionary containing the name of the GitHub organization, repository,
        branch and S3 file, or an empty dictionary if none or only a subset
        of these values could be extracted.

    Raises:
        ValueError: The input S3 key could not be reconstructed by using the
            extracted values.
    """
    gh_org_symbols = r"\S+"
    gh_repo_symbols = r"\S+"
    gh_branch_symbols = r"\S+"
    s3_filename_symbols = r"[a-zA-Z0-9_.-]+"
    pattern = re.compile(
        rf"(?P<gh_org>{gh_org_symbols})"
        rf"/(?P<gh_repo>{gh_repo_symbols})"
        rf"/branches"
        rf"/(?P<gh_branch>{gh_branch_symbols})"
        rf"/(?P<s3_filename>{s3_filename_symbols})$"
    )
    m = pattern.match(s3_key)
    groups = m.groupdict() if m else {}
    if groups:
        reconstructed_s3_key = f"{groups['gh_org']}/{groups['gh_repo']}/branches/{groups['gh_branch']}/{groups['s3_filename']}"
        if reconstructed_s3_key != s3_key:
            logger.error(
                "Reconstructed S3 key '%s' is not equal to original S3 key '%s'",
                reconstructed_s3_key,
                s3_key,
            )
            raise ValueError()
    return groups


def read_json_from_s3(s3_bucket, s3_key, expected_keys=[]):
    """Reads the content of a JSON file in S3.

    Args:
        s3_bucket: The name of the S3 bucket where the JSON file is located.
        s3_key: The S3 key of the JSON file.
        expected_keys: The keys that are expected to be found inside the JSON file.

    Returns:
        The content of the JSON file converted to a Python dictionary.

    Raises:
        Exception: Could not load S3 file as JSON.
        json.decoder.JSONDecodeError: Could not read file as JSON.
        LookupError: Did not find expected keys in dictionary.
    """
    logger.debug(
        "Reading file 's3://%s/%s",
        s3_bucket,
        s3_key,
    )
    try:
        s3 = boto3.resource("s3")
        obj = s3.Object(s3_bucket, s3_key)
        body = obj.get()["Body"].read().decode("utf-8")
    except Exception:
        logger.exception(
            "Something went wrong when trying to download file 's3://%s/%s'",
            s3_bucket,
            s3_key,
        )
        raise
    try:
        content = json.loads(body)
    except (TypeError, json.decoder.JSONDecodeError):
        logger.exception(
            "Something went wrong when trying to load file content '%s' as JSON",
            body,
        )
        raise

    if expected_keys and not all(key in content for key in expected_keys):
        logger.error(
            "Expected trigger event file to have keys '%s', but found '%s'",
            expected_keys,
            content.keys(),
        )
        raise LookupError
    return content


def lambda_handler(event, context):
    logger.info("Lambda started with input event '%s'", event)

    allowed_branches = json.loads(os.environ["ALLOWED_BRANCHES"])
    region = os.environ["AWS_REGION"]
    service_account_id = os.environ["SERVICE_ACCOUNT_ID"]

    cost_saving_mode = event.get("cost_saving_mode", False)
    toggling_cost_saving_mode = event.get("toggling_cost_saving_mode", False)
    s3_bucket = event.get("s3_bucket", "")
    s3_key = event.get("s3_key", "")
    if s3_bucket and s3_key:
        logger.info(
            "Path to trigger file was manually passed in to Lambda 's3://%s/%s'",
            s3_bucket,
            s3_key,
        )

    else:
        s3_bucket = event["Records"][0]["s3"]["bucket"]["name"]
        s3_key = event["Records"][0]["s3"]["object"]["key"]
        logger.info(
            "Lambda was triggered by file 's3://%s/%s'", s3_bucket, s3_key
        )

    required_keys = [
        "git_owner",
        "git_repo",
        "git_branch",
        "git_owner",
        "git_sha1",
        "pipeline_name",
        "deployment_repo",
        "trigger_file",
    ]

    trigger_file = read_json_from_s3(s3_bucket, s3_key, required_keys)
    s3_prefix = (
        f"{trigger_file['git_owner']}/{trigger_file['git_repo']}/branches/"
        f"{trigger_file['git_branch']}"
    )
    deployment_package = (
        f"s3://{s3_bucket}/{s3_prefix}/{trigger_file['git_sha1']}.zip"
    )
    if trigger_file["git_repo"] != trigger_file["deployment_repo"]:
        deployment_trigger_file = read_json_from_s3(
            s3_bucket,
            (
                f"{s3_bucket}/{trigger_file['git_owner']}/"
                f"{trigger_file['deployment_repo']}/branches/master/"
                f"{trigger_file['trigger_file']}"
            ),
            required_keys,
        )
        deployment_package = (
            f"{s3_bucket}/{trigger_file['git_owner']}/"
            f"{trigger_file['deployment_repo']}/branches/master/"
            f"{deployment_trigger_file['git_sha1']}.zip"
        )
    logger.info("Using source code location '%s'", deployment_package)

    pipeline_arn = (
        f"arn:aws:states:{region}:{service_account_id}:stateMachine:"
        "{trigger_file['pipeline_name']}"
    )
    execution_name = (
        f"{trigger_file['git_sha1']}-{time.strftime('%Y%m%d-%H%M%S')}"
    )
    execution_input = json.dumps(
        {
            **trigger_file,
            "deployment_package": deployment_package,
            "content": deployment_package,
        }
    )

    client = boto3.client("stepfunctions")
    client.start_execution(
        stateMachineArn=pipeline_arn,
        name=execution_name,
        input=execution_input,
    )
