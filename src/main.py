import json
import boto3
import time
import logging
import os
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Read config file outside Lambda handler to allow reuse
# between executions
with open("config.json") as f:
    CONFIG = json.load(f)


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


def read_json_from_s3(s3_bucket, s3_key, s3_version_id=None):
    """Reads the content of a JSON file in S3.

    Args:
        s3_bucket: The name of the S3 bucket where the JSON file is located.
        s3_key: The S3 key of the JSON file.
        s3_version_id: Optional S3 object version.

    Returns:
        The content of the JSON file converted to a Python dictionary.

    Raises:
        Exception: Could not load S3 file as JSON.
        json.decoder.JSONDecodeError: Could not read file as JSON.
    """
    logger.debug(
        "Reading file 's3://%s/%s' (%s)",
        s3_bucket,
        s3_key,
        f"version '{s3_version_id}'" if s3_version_id else "latest version",
    )
    try:
        s3 = boto3.resource("s3")
        obj = s3.Object(s3_bucket, s3_key)
        body = (
            obj.get(**({"VersionId": s3_version_id} if s3_version_id else {}))[
                "Body"
            ]
            .read()
            .decode("utf-8")
        )
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
    return content


def verify_rule(rule, repo, branch):
    """Verify that the pipeline is being triggered by an approved
    branch and repository"""
    logger.info(
        "Verifying rule '%s' against repo '%s' and branch '%s'",
        rule,
        repo,
        branch,
    )
    if not (
        "*" in rule["allowed_branches"] or branch in rule["allowed_branches"]
    ):
        logger.warn(
            "The branch '%s' is not allowed to trigger the pipeline",
            branch,
        )
        return False
    if not (
        "*" in rule["allowed_repositories"]
        or repo in rule["allowed_repositories"]
    ):
        logger.warn(
            "The repository '%s' is not allowed to trigger the pipeline",
            repo,
        )
        return False
    return True


def get_parsed_trigger_file(
    trigger_file, s3_key, expected_keys=[], legacy_keys=[]
):
    """Check that trigger file has the correct keys, add default values,
    and potentially fall back to a legacy format if the first set of
    keys are not present"""
    if all(key in trigger_file for key in expected_keys):
        return {
            "deployment_repo": trigger_file["git_repo"],
            "deployment_branch": trigger_file["git_branch"],
            **trigger_file,
        }
    elif all(key in trigger_file for key in legacy_keys):
        logger.warn("Parsing trigger file using legacy format")
        extracted_data = extract_data_from_s3_key(s3_key)
        return {
            "git_owner": extracted_data["gh_org"],
            "git_repo": extracted_data["gh_repo"],
            "git_branch": extracted_data["gh_branch"],
            "git_user": None,
            "git_sha1": trigger_file["SHA"],
            "deployment_repo": trigger_file["aws_repo_name"],
            "deployment_branch": extracted_data["gh_branch"]
            if extracted_data["gh_repo"] == trigger_file["aws_repo_name"]
            else "master",
            "pipeline_name": f"{trigger_file['name_prefix']}-state-machine",
        }
    logger.error(
        "Expected trigger event file to have keys '%s' or keys '%s', but found '%s'",
        expected_keys,
        legacy_keys,
        trigger_file.keys(),
    )
    raise LookupError


def lambda_handler(event, context):
    logger.info("Lambda started with input event '%s'", event)
    trigger_rules = CONFIG["trigger_rules"]
    name_of_trigger_file = CONFIG["name_of_trigger_file"]
    service_account_id = CONFIG["current_account_id"]
    region = os.environ["AWS_REGION"]
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
        s3_version_id = None
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
        s3_version_id = event["Records"][0]["s3"]["object"].get(
            "versionId", None
        )
        logger.info(
            "Lambda was triggered by file 's3://%s/%s'", s3_bucket, s3_key
        )

    legacy_keys = ["SHA", "date", "name_prefix", "aws_repo_name"]
    required_keys = [
        "git_owner",
        "git_repo",
        "git_branch",
        "git_user",
        "git_sha1",
        "pipeline_name",
    ]

    trigger_file = read_json_from_s3(
        s3_bucket,
        s3_key,
        s3_version_id=s3_version_id,
    )
    trigger_file = get_parsed_trigger_file(
        trigger_file,
        s3_key,
        expected_keys=required_keys,
        legacy_keys=legacy_keys,
    )

    s3_prefix = (
        f"{trigger_file['git_owner']}/{trigger_file['git_repo']}/branches/"
        f"{trigger_file['git_branch']}"
    )
    deployment_package = (
        f"s3://{s3_bucket}/{s3_prefix}/{trigger_file['git_sha1']}.zip"
    )
    deployment_package_sha1 = trigger_file["git_sha1"]
    if trigger_file["git_repo"] != trigger_file["deployment_repo"]:
        deployment_s3_key = (
            f"{trigger_file['git_owner']}/"
            f"{trigger_file['deployment_repo']}/branches/"
            f"{trigger_file['deployment_branch']}/"
            f"{name_of_trigger_file}"
        )
        deployment_trigger_file = read_json_from_s3(
            s3_bucket, deployment_s3_key
        )
        deployment_trigger_file = get_parsed_trigger_file(
            deployment_trigger_file,
            deployment_s3_key,
            expected_keys=required_keys,
            legacy_keys=legacy_keys,
        )
        deployment_package = (
            f"s3://{s3_bucket}/{trigger_file['git_owner']}/"
            f"{trigger_file['deployment_repo']}/branches/"
            f"{trigger_file['deployment_branch']}/"
            f"{deployment_trigger_file['git_sha1']}.zip"
        )
        deployment_package_sha1 = deployment_trigger_file["git_sha1"]
    logger.info("Using source code location '%s'", deployment_package)

    pipeline_arn = (
        f"arn:aws:states:{region}:{service_account_id}:stateMachine:"
        f"{trigger_file['pipeline_name']}"
    )

    execution_name = (
        f"{deployment_package_sha1}-{time.strftime('%Y%m%d-%H%M%S')}"
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
            "content": deployment_package,
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
        if not rule:
            logger.warn(
                "No trigger rule found for state machine '%s'", pipeline_arn
            )
        else:
            verified = verify_rule(
                rule,
                trigger_file["git_repo"],
                trigger_file["git_branch"],
            )
            if not verified:
                raise ValueError

    client = boto3.client("stepfunctions")
    client.start_execution(
        stateMachineArn=pipeline_arn,
        name=execution_name,
        input=execution_input,
    )
