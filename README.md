# terraform-aws-trigger-pipeline
Terraform module that creates a Lambda function that can be used to bridge together a continuous integration (CI) service and an AWS Step Functions state machine.

The CI service uploads a JSON file to S3, which is then read by the Lambda to determine which state machine to trigger with which input.
