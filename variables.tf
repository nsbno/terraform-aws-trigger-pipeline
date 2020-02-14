variable "name_prefix" {
  description = "A prefix used for naming resources."
  type        = string
}

variable "statemachine_arn" {
  description = "The arn of the statemachine this lambda should trigger"
  type = string
}

variable "artifact_bucket_name" {
  description = "The name of the bucket used for trigger files and artifacts"
  type = string
}

variable "tags" {
  description = "A map of tags (key-value pairs) passed to resources."
  type        = map(string)
  default     = {}
}
