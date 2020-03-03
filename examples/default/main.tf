provider "aws" {
  version             = "~> 2.46"
  region              = "eu-west-1"
}

data "aws_caller_identity" "current-account" {}

locals {
  name_prefix = "default-example"
  tags =  {
    terraform   = "true"
    environment = "test"
    application = "trigger-pipeline-lambda-default-example"
  }
}


module "trigger_pipeline_lambda" {
  source = "../../"
  name_prefix = local.name_prefix
  artifact_bucket_name = aws_s3_bucket.artifact_bucket.id
  statemachine_arn = aws_sfn_state_machine.state_machine.id
}

resource "aws_s3_bucket" "artifact_bucket" {
  bucket = "${data.aws_caller_identity.current-account.account_id}-${local.name_prefix}-artifacts"
}

resource "aws_sfn_state_machine" "state_machine" {
  definition = local.state_definition
  name       = "${local.name_prefix}-state-machine"
  role_arn   = aws_iam_role.state_machine_role.arn
  tags       = local.tags
}

resource "aws_iam_role" "state_machine_role" {
  assume_role_policy = data.aws_iam_policy_document.state_machine_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "state_machine_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = ["states.amazonaws.com"]
      type        = "Service"
    }
  }
}