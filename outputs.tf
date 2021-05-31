output "lambda_function_arn" {
  value = aws_lambda_function.infra_trigger_pipeline.arn
}

output "function_name" {
  value = aws_lambda_function.infra_trigger_pipeline.function_name
}
