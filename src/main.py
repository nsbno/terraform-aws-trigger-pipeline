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
        "Reading file 's3://%s/%s", s3_bucket, s3_key,
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


def get_trigger_file_and_s3_path(s3_bucket, s3_key):
    """Gets the content of the trigger file belonging to the
    GitHub repository containing the main AWS set up, as well
    as the S3 path of the zip file containing the latest source
    code for this repository.

    Args:
        s3_bucket: The name of the S3 bucket that triggered the Lambda.
        s3_key: The S3 key of the file that triggered the Lambda.

    Returns:
        A tuple containing the contents of the trigger file as a dictionary
        and the S3 path of the zip file containing the latest source code.
    """
    data_from_s3_key = extract_data_from_s3_key(s3_key)
    gh_org, gh_repo, gh_branch, s3_filename = (
        data_from_s3_key["gh_org"],
        data_from_s3_key["gh_repo"],
        data_from_s3_key["gh_branch"],
        data_from_s3_key["s3_filename"],
    )
    s3_prefix = f"{gh_org}/{gh_repo}/branches/{gh_branch}"

    expected_keys_in_trigger_file = [
        "SHA",
        "date",
        "name_prefix",
        "aws_repo_name",
    ]
    contents_of_trigger_file = read_json_from_s3(
        s3_bucket, s3_key, expected_keys_in_trigger_file
    )
    aws_gh_repo = contents_of_trigger_file["aws_repo_name"]
    if aws_gh_repo == gh_repo:
        # Triggered by update to aws repo
        logger.debug(
            "Lambda was triggered by GitHub repository containing the main AWS set up '%s'",
            gh_repo,
        )
        s3_path = f"s3://{s3_bucket}/{s3_prefix}/{contents_of_trigger_file['SHA']}.zip"
        return contents_of_trigger_file, s3_path

    # Triggered by update to an application repo (e.g., frontend, Docker, etc.).
    # Need to read trigger-event.json belonging to aws-repo
    logger.debug(
        "Lambda was triggered by GitHub repository containing application code '%s'",
        gh_repo,
    )
    s3_prefix_aws_repo = f"{gh_org}/{aws_gh_repo}/branches/master"
    s3_key_aws_repo = f"{s3_prefix_aws_repo}/{s3_filename}"
    logger.debug(
        "Reading the trigger file belonging to the GitHub repository containing the main AWS set up '%s'",
        aws_gh_repo,
    )
    contents_of_trigger_file = read_json_from_s3(
        s3_bucket, s3_key_aws_repo, expected_keys_in_trigger_file
    )
    s3_path = f"s3://{s3_bucket}/{s3_prefix_aws_repo}/{contents_of_trigger_file['SHA']}.zip"
    return contents_of_trigger_file, s3_path


def start_pipeline_execution(pipeline_arn, execution_name, execution_input):
    """Starts a pipeline execution.

    Args:
        pipeline_arn: The ARN of the pipeline that is to be executed.
        execution_name: The name of the execution.
        execution_input: The JSON input to the execution.
    """
    client = boto3.client("stepfunctions")
    client.start_execution(
        stateMachineArn=pipeline_arn,
        name=execution_name,
        input=execution_input,
    )


def lambda_handler(event, context):
    logger.info("Lambda started with input event '%s'", event)

    service_account_id = (
        boto3.client("sts").get_caller_identity().get("Account")
    )
    region = os.environ["AWS_REGION"]

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

    (
        contents_of_trigger_file,
        s3_path_of_aws_repository_zip,
    ) = get_trigger_file_and_s3_path(s3_bucket, s3_key)

    logger.info(
        "Using source code location '%s'", s3_path_of_aws_repository_zip
    )

    pipeline_arn = f"arn:aws:states:{region}:{service_account_id}:stateMachine:{contents_of_trigger_file['name_prefix']}-state-machine"
    execution_name = (
        f"{contents_of_trigger_file['SHA']}-{time.strftime('%Y%m%d-%H%M%S')}"
    )
    execution_input = json.dumps(
        {
            "content": s3_path_of_aws_repository_zip,
            "cost_saving_mode": cost_saving_mode,
            "toggling_cost_saving_mode": toggling_cost_saving_mode,
        }
    )
    start_pipeline_execution(pipeline_arn, execution_name, execution_input)
