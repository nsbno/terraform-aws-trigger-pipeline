import json
import boto3
import time
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

def get_content_of_trigger_event_file(s3_bucket, s3_key):
    expected_keys = ["SHA", "date", "activities_key"]
    try:
        s3 = boto3.resource("s3")
        obj = s3.Object(s3_bucket, s3_key)
        body = obj.get()["Body"].read().decode("utf-8")
        pipeline_trigger = json.loads(body)
    except Exception:
        logger.exception(
            "Something went wrong when trying to load 's3://%s/%s' as JSON",
            s3_bucket,
            s3_key,
        )
    if not all(key in pipeline_trigger for key in expected_keys):
        logger.error(
            "Expected trigger event file to have keys '%s', but found '%s'",
            expected_keys,
            pipeline_trigger.keys(),
        )
        raise Exception()

    return pipeline_trigger

def get_activities_config(s3_bucket,s3_key):


def lambda_handler(event, context):
    logger.info("Lambda started with input event '%s'", event)

    service_account_id = (
        boto3.client("sts").get_caller_identity().get("Account")
    )

    state_machine = f"arn:aws:states:eu-west-1:{service_account_id}:stateMachine:aws-infrademo-state-machine"

    # tar s3 event og henter bucketnavn og filpath
    s3_bucket = event["Records"][0]["s3"]["bucket"]["name"]
    s3_key = event["Records"][0]["s3"]["object"]["key"]
    s3_prefix, s3_filename = s3_key.rsplit("/", 1)

    if s3_key != f"{s3_prefix}/{s3_filename}":
        logger.error(
            "Tried to extract filename, but the resulting S3 key '%s' was not equal to the original key '%s'",
            f"{s3_prefix}/{s3_filename}",
            s3_key,
        )
        raise Exception()

    logger.info(
        "Lambda was triggered by file 's3://%s/%s/%s'",
        s3_bucket,
        s3_prefix,
        s3_filename,
    )

    pipeline_trigger = get_content_of_trigger_event_file(s3_bucket, s3_key)
    source_code = f"s3://{s3_bucket}/{s3_prefix}/{pipeline_trigger['SHA']}.zip"
    logger.info("Using source code location '%s'", source_code)
    activities_config = get_activities_config(s3_bucket,pipeline_trigger['activities_key'])

    try:
        for activityKey in activities_config["activities"]:
            activities_config["activities"][activityKey]["content"] = source_code

            rolename = activities_config["activities"][activityKey]["task_role_arn"]
            if "test" in activityKey:
                activities_config["activities"][activityKey]["task_role_arn"] = (
                        "arn:aws:iam::" + service_account_id + ":role/" + rolename
                )

            if "stage" in activityKey:
                activities_config["activities"][activityKey]["task_role_arn"] = (
                        "arn:aws:iam::" + service_account_id + ":role/" + rolename
                )

            if "prod" in activityKey:
                activities_config["activities"][activityKey]["task_role_arn"] = (
                        "arn:aws:iam::" + service_account_id + ":role/" + rolename
                )

            if "service" in activityKey:
                activities_config["activities"][activityKey]["task_role_arn"] = (
                        "arn:aws:iam::" + service_account_id + ":role/" + rolename
                )

    except Exception as e:
        logger.exception(
            "Failed when parsing json file for state config" + str(e)
        )

    # starter codepipeline med input parametere
    client = boto3.client("stepfunctions")
    client.start_execution(
        stateMachineArn=state_machine,
        name=pipeline_trigger['SHA'] + '-' + time.strftime("%Y%m%d-%H%M%S"),
        input=json.dumps(params),
    )
