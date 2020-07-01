variable "name_prefix" {
  description = "A prefix used for naming resources."
  type        = string
}

variable "statemachine_arn" {
  description = "The ARN of the state machhine this lambda can trigger"
  type        = string
}

variable "additional_state_machine_arns" {
  description = "A list of ARNs of additional state machines that the Lambda can trigger"
  default     = []
  type        = list(string)
}

variable "artifact_bucket_name" {
  description = "The name of the bucket used for trigger files and artifacts"
  type        = string
}

variable "tags" {
  description = "A map of tags (key-value pairs) passed to resources."
  type        = map(string)
  default     = {}
}

variable "lambda_timeout" {
  description = "The maximum number of seconds the Lambda is allowed to run."
  default     = 10
}
