data "aws_iam_policy_document" "lambda_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]
    principals {
      identifiers = ["lambda.amazonaws.com"]
      type        = "Service"
    }
  }
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

data "aws_iam_policy_document" "s3_for_lambda" {
  statement {
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${data.aws_s3_bucket.trigger_bucket.arn}/*"]
  }
}

data "aws_iam_policy_document" "stepfunctions_for_lambda" {
  statement {
    effect    = "Allow"
    actions   = ["states:StartExecution"]
    resources = [var.statemachine_arn]
  }
}