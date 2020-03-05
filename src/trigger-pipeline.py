import json
import boto3
import time
import logging
import re

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def extract_data_from_s3_key(s3_key):
    gh_org_symbols = r"\S+"
    gh_repo_symbols = r"\S+"
    gh_branch_symbols = r"\S+"
    sha_symbols = r"[a-zA-Z0-9]+"
    pattern = re.compile(
        rf"/(?P<gh_org>{gh_org_symbols})"
        rf"/(?P<gh_repo>{gh_repo_symbols})"
        rf"/branches"
        rf"/(?P<gh_branch>{gh_branch_symbols})"
        rf"/(?P<sha>{sha_symbols})\.zip$"
    )
    m = pattern.match(s3_key)
    groups = m.groupdict() if m else {}
    if groups:
        reconstructed_s3_key = f"{groups['gh_org']}/{groups['gh_repo']}/branches/{groups['gh_branch']}/{groups['sha']}.zip"
        if reconstructed_s3_key != s3_key:
            logger.error(
                "Reconstructed S3 key '%s' is not equal to original S3 key '%s'",
                reconstructed_s3_key,
                s3_key,
            )
            raise Exception()
    return groups

def get_content_from_s3(s3_bucket,s3_key,expected_keys):
    try:
        s3 = boto3.resource("s3")
        obj = s3.Object(s3_bucket, s3_key)
        body = obj.get()["Body"].read().decode("utf-8")
        content = json.loads(body)
    except Exception:
        logger.exception(
            "Something went wrong when trying to load 's3://%s/%s' as JSON",
            s3_bucket,
            s3_key,
        )
    if expected_keys != "" and not all(key in content for key in expected_keys):
        logger.error(
            "Expected trigger event file to have keys '%s', but found '%s'",
            expected_keys,
            content.keys(),
        )
        raise Exception()
    return content

def lambda_handler(event, context):
    logger.info("Lambda started with input event '%s'", event)

    service_account_id = (
        boto3.client("sts").get_caller_identity().get("Account")
    )



    # tar s3 event og henter bucketnavn og filpath
    s3_bucket = event["Records"][0]["s3"]["bucket"]["name"]
    s3_key = event["Records"][0]["s3"]["object"]["key"]
    data_from_s3_key = extract_data_from_s3_key(s3_key)
    gh_org, gh_repo, gh_branch, sha = data_from_s3_key["gh_org"], data_from_s3_key["gh_repo"], data_from_s3_key["gh_branch"], data_from_s3_key["sha"]
    s3_prefix = f"{gh_org}/{gh_repo}/branches/{gh_branch}"
    s3_filename = f"{sha}.zip"

    logger.info(
        "Lambda was triggered by file 's3://%s/%s/%s'",
        s3_bucket,
        s3_prefix,
        s3_filename,
    )

    pipeline_trigger_expected_keys = ["SHA", "date", "name_prefix"]
    original_pipeline_trigger = get_content_from_s3(s3_bucket,s3_key,pipeline_trigger_expected_keys)
    if original_pipeline_trigger['aws_repo_name'] == gh_repo:
        # Triggered by update to aws repo
        pipeline_trigger = original_pipeline_trigger
        content = {'content': f"s3://{s3_bucket}/{s3_prefix}/{pipeline_trigger['SHA']}.zip"}
    else:
        # Triggered by update to an application repo (e.g., frontend, Docker, etc.).
        # Need to read trigger-event.json belonging to aws-repo
        s3_key_aws_repo = f"{gh_org}/{original_pipeline_trigger['aws_repo_name']}/branches/master/trigger-event.json"
        pipeline_trigger = get_content_from_s3(s3_bucket,s3_key_aws_repo,pipeline_trigger_expected_keys)
        content = {'content': f"s3://{s3_bucket}/{original_pipeline_trigger['aws_repo_name']}/branches/master/{pipeline_trigger['SHA']}.zip"
    logger.info("Using source code location '%s'", content['content'])

    # starter codepipeline med input parametere
    state_machine = f"arn:aws:states:eu-west-1:{service_account_id}:stateMachine:{pipeline_trigger['name_prefix']}-state-machine"
    client = boto3.client("stepfunctions")
    client.start_execution(
        stateMachineArn=state_machine,
        name=pipeline_trigger['SHA'] + '-' + time.strftime("%Y%m%d-%H%M%S"),
        input=json.dumps(content)
    )
