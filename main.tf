data "aws_caller_identity" "current-account" {}
data "aws_region" "current" {}

locals {
  current_account_id = data.aws_caller_identity.current-account.account_id
  current_region     = data.aws_region.current.name
}

data "archive_file" "lambda_infra_trigger_pipeline_src" {
  type        = "zip"
  source_file = "${path.module}/../../lambda/infra_trigger_pipeline/main.py"
  output_path = "${path.module}/../../lambda/infra_trigger_pipeline/bundle.zip"
}

resource "aws_lambda_function" "infra_trigger_pipeline" {
  function_name    = "${var.name_prefix}-infra-trigger-pipeline"
  handler          = "main.lambda_handler"
  role             = aws_iam_role.lambda_infra_trigger_pipeline_exec.arn
  runtime          = "python3.7"
  filename         = data.archive_file.lambda_infra_trigger_pipeline_src.output_path
  source_code_hash = filebase64sha256(data.archive_file.lambda_infra_trigger_pipeline_src.output_path)
  tags             = var.tags
}

resource "aws_iam_role" "lambda_infra_trigger_pipeline_exec" {
  name               = "${var.name_prefix}-infra-trigger-pipeline"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy" "logs_to_infra_trigger_pipeline_lambda" {
  policy = data.aws_iam_policy_document.logs_for_lambda.json
  role   = aws_iam_role.lambda_infra_trigger_pipeline_exec.id
}

data "aws_iam_policy_document" "logs_for_lambda" {
  statement {
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup"]
    resources = ["arn:aws:logs:${local.current_region}:${local.current_account_id}:*"]
  }
  statement {
    effect = "Allow"
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]
    resources = [
      "arn:aws:logs:${local.current_region}:${local.current_account_id}:log-group:/aws/lambda/${aws_lambda_function.infra_trigger_pipeline.function_name}*",
    ]
  }
}

data "aws_s3_bucket" "trigger_bucket" {
  bucket = var.artifact_bucket_name
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = data.aws_s3_bucket.trigger_bucket
  lambda_function {
    lambda_function_arn = aws_lambda_function.infra_trigger_pipeline.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = "trigger-event.json"
  }
}

data "aws_iam_policy_document" "s3_for_lambda" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = "${data.aws_s3_bucket.trigger_bucket.arn}/*"
  }
}

data "aws_iam_policy_document" "stepfunctions_for_lambda" {
  statement {
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [var.statemachine_arn]
  }
}

