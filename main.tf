data "aws_caller_identity" "current-account" {}
data "aws_region" "current" {}

locals {
  current_account_id   = data.aws_caller_identity.current-account.account_id
  current_region       = data.aws_region.current.name
  name_of_trigger_file = "trigger-event.json"
  default_trigger_rule = {
    allowed_branches     = var.allowed_branches
    allowed_repositories = var.allowed_repositories
  }
  trigger_rules_by_pipeline = var.trigger_rules == [] ? {} : { for obj in var.trigger_rules : obj.state_machine_arn => {
    state_machine_arn    = obj.state_machine_arn
    allowed_branches     = obj.allowed_branches
    allowed_repositories = obj.allowed_repositories
    }
  }
  trigger_rules = [for arn in var.state_machine_arns : lookup(local.trigger_rules_by_pipeline, arn, {
    state_machine_arn    = arn
    allowed_branches     = var.allowed_branches
    allowed_repositories = var.allowed_repositories
  })]
}

data "archive_file" "this" {
  type = "zip"
  source {
    filename = "main.py"
    content  = file("${path.module}/src/main.py")
  }
  source {
    filename = "config.json"
    content = jsonencode({
      name_of_trigger_file = local.name_of_trigger_file
      default_trigger_rule = local.default_trigger_rule
      trigger_rules        = local.trigger_rules
      current_account_id   = local.current_account_id
    })
  }
  output_path = "${path.module}/.terraform_artifacts/source.zip"
}

resource "aws_lambda_function" "infra_trigger_pipeline" {
  function_name    = "${var.name_prefix}-infra-trigger-pipeline"
  handler          = "main.lambda_handler"
  role             = aws_iam_role.lambda_infra_trigger_pipeline_exec.arn
  runtime          = "python3.7"
  filename         = data.archive_file.this.output_path
  source_code_hash = data.archive_file.this.output_base64sha256
  timeout          = var.lambda_timeout
  tags             = var.tags
}

resource "aws_lambda_function_event_invoke_config" "this" {
  function_name          = aws_lambda_function.infra_trigger_pipeline.function_name
  maximum_retry_attempts = 0
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

data "aws_s3_bucket" "trigger_bucket" {
  bucket = var.artifact_bucket_name
}

resource "aws_lambda_permission" "allow_bucket" {
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.infra_trigger_pipeline.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = data.aws_s3_bucket.trigger_bucket.arn
}

resource "aws_s3_bucket_notification" "bucket_notification" {
  bucket = data.aws_s3_bucket.trigger_bucket.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.infra_trigger_pipeline.arn
    events              = ["s3:ObjectCreated:*"]
    filter_suffix       = local.name_of_trigger_file
  }
}



resource "aws_iam_role_policy" "s3_to_lambda" {
  policy = data.aws_iam_policy_document.s3_for_lambda.json
  role   = aws_iam_role.lambda_infra_trigger_pipeline_exec.id
}

resource "aws_iam_role_policy" "stepfunctions_to_lambda" {
  policy = data.aws_iam_policy_document.stepfunctions_for_lambda.json
  role   = aws_iam_role.lambda_infra_trigger_pipeline_exec.id
}
