import json
import boto3
import time
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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

    pipeline_trigger_expected_keys = ["SHA", "date", "name_prefix"]
    pipeline_trigger = get_content_from_s3(s3_bucket,s3_key,pipeline_trigger_expected_keys)
    content = {'content': f"s3://{s3_bucket}/{s3_prefix}/{pipeline_trigger['SHA']}.zip"}
    logger.info("Using source code location '%s'", content['content'])

    # starter codepipeline med input parametere
    state_machine = f"arn:aws:states:eu-west-1:{service_account_id}:stateMachine:{pipeline_trigger['name_prefix']}-state-machine"
    client = boto3.client("stepfunctions")
    client.start_execution(
        stateMachineArn=state_machine,
        name=pipeline_trigger['SHA'] + '-' + time.strftime("%Y%m%d-%H%M%S"),
        input=json.dumps(content)
    )
