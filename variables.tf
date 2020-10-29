variable "name_prefix" {
  description = "A prefix used for naming resources."
  type        = string
}

variable "statemachine_arn" {
  description = "The ARN of the state machhine this lambda can trigger"
  type        = string
}

variable "allowed_branches" {
  description = "The branches that are allowed to trigger an AWS Step Functions pipeline (NOTE: `var.trigger_rules` takes presedence over this)."
  default     = ["master"]
}

variable "trigger_rules" {
  description = "A list of objects that describe which branches and repositories are allowed to trigger a AWS Step Functions pipeline. A single wildcard item can be used to signify all (i.e., no restrictions)."
  type = list(object({
    state_machine_arn = string
    allowed_branches = list(string)
    allowed_repositories = list(string)
  })
  default     = null
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
