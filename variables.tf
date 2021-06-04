variable "name_prefix" {
  description = "A prefix used for naming resources."
  type        = string
}

variable "allowed_branches" {
  description = "A list of GitHub branches that are allowed to trigger an AWS Step Functions pipeline. A single wildcard item can be used to signify all. (NOTE: Rules specified in `var.trigger_rules` will override this for the pipelines in question)."
  default     = ["master", "main"]
}

variable "allowed_repositories" {
  description = "A list of GitHub repositories (e.g., `nsbno/my-repository`) that are allowed to trigger an AWS Step Functions pipeline. A single wildcard item can be used to signify all. (NOTE: Rules specified in `var.trigger_rules` will override this for the pipelines in question)."
  default     = ["*"]
}

variable "trigger_rules" {
  description = <<DOC
An optional list of objects that describe which branches and repositories are allowed to trigger an AWS Step Functions state machine.

Object fields:
state_machine_arn: The ARN (without wildcards) of the state machine that the rule is valid for.
allowed_branches: Optional list of branches that can trigger the state machine (defaults to the value of `var.allowed_branches`). A single wildcard item can be used to signify all.
allowed_repositories: Optional list of GitHub repositories that can trigger the state machine (defaults to ["*"]). A single wildcard item can be used to signify all.
DOC
  type        = list(any)
  default     = []
}

variable "state_machine_arns" {
  description = "A list of ARNs of AWS Step Functions state machines that the Lambda can trigger."
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
