import json
import boto3
import time
import logging
import os

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


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


def verify_rule(rule, pipeline_arn, branch, repo):
    """Verify that the pipeline is being triggered by an approved
    branch and repository"""
    if not rule:
        logger.error(
            "No trigger rule found for state machine '%s'", pipeline_arn
        )
        return False
    if not (
        "*" in rule["allowed_branches"] or branch in rule["allowed_branches"]
    ):
        logger.warn(
            "The branch '%s' is not allowed to trigger pipeline '%s'",
            branch,
            pipeline_arn,
        )
        return False
    if not (
        "*" in rule["allowed_repositories"]
        or repo in rule["allowed_repositories"]
    ):
        logger.warn(
            "The repository '%s' is not allowed to trigger pipeline '%s'",
            repo,
            pipeline_arn,
        )
        return False
    return True


def lambda_handler(event, context):
    logger.info("Lambda started with input event '%s'", event)

    trigger_rules = json.loads(os.environ["TRIGGER_RULES"])
    name_of_trigger_file = os.environ["NAME_OF_TRIGGER_FILE"]
    region = os.environ["AWS_REGION"]
    service_account_id = os.environ["CURRENT_ACCOUNT_ID"]
    state_machine_arns = list(
        map(lambda rule: rule["state_machine_arn"], trigger_rules)
    )

    eventbridge_input = {}
    if event.get("eventbridge_rule", False):
        triggered_by_ci = False
        if not all(key in event for key in ["s3_bucket", "s3_key"]):
            logger.error(
                "The CloudWatch Event did not pass in all expected keys"
            )
            raise ValueError
        s3_bucket = event["s3_bucket"]
        s3_key = event["s3_key"]
        logger.info(
            "Path to trigger file was manually passed in to Lambda 's3://%s/%s'",
            s3_bucket,
            s3_key,
        )
        eventbridge_input = event.get("input", {})
    else:
        triggered_by_ci = True
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
                f"{trigger_file['git_owner']}/"
                f"{trigger_file['deployment_repo']}/branches/"
                f"{trigger_file['deployment_branch']}/"
                f"{name_of_trigger_file}"
            ),
            required_keys,
        )
        deployment_package = (
            f"{s3_bucket}/{trigger_file['git_owner']}/"
            f"{trigger_file['deployment_repo']}/branches/"
            f"{trigger_file['deployment_branch']}/"
            f"{deployment_trigger_file['git_sha1']}.zip"
        )
    logger.info("Using source code location '%s'", deployment_package)

    pipeline_arn = (
        f"arn:aws:states:{region}:{service_account_id}:stateMachine:"
        f"{trigger_file['pipeline_name']}"
    )
    if pipeline_arn not in state_machine_arns:
        logger.error("Unexpected state machine ARN '%s'", state_machine_arns)
        return

    execution_name = (
        f"{trigger_file['git_sha1']}-{time.strftime('%Y%m%d-%H%M%S')}"
    )

    execution_input = json.dumps(
        {
            **trigger_file,
            **(
                {"eventbridge_input": eventbridge_input}
                if len(eventbridge_input)
                else {}
            ),
            "deployment_package": deployment_package,
        },
        sort_keys=True,
    )
    if triggered_by_ci:
        rule = next(
            (
                rule
                for rule in trigger_rules
                if rule["state_machine_arn"] == pipeline_arn
            ),
            None,
        )
        verified = verify_rule(
            rule,
            pipeline_arn,
            trigger_file["git_branch"],
            trigger_file["git_repo"],
        )
        if not verified:
            raise ValueError

    client = boto3.client("stepfunctions")
    client.start_execution(
        stateMachineArn=pipeline_arn,
        name=execution_name,
        input=execution_input,
    )
