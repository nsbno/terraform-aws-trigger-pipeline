# terraform-aws-trigger-pipeline
A Terraform module that creates a Lambda function that can be used to bridge together a Continuous Integration (CI) service and an AWS Step Functions state machine: your CI service uploads a JSON file to S3, which is then read by the Lambda to determine which state machine to trigger with which input.

## Triggering Mechanism
The triggering mechanism is based on the upload of a special file `trigger-event.json` to S3. The Lambda expects you to store artifacts in an S3 bucket under the following prefix: `<github-owner>/<github-repo>/branches/<branch-name>`. In general, two types of files are expected to be uploaded to this prefix:
1. A ZIP file ("_deployment package_") containing the files that will be deployed by the state machine (typically source code).
2. A special file called `trigger-event.json`.

Your CI service can initiate a deployment by uploading the file `trigger-event.json` at the end of its workflow. The contents of this file is read by the Lambda to determine which AWS Step Functions state machine to start with which JSON input. The file needs to contain at least the five keys `pipeline_name`, `git_owner`, `git_repo`, `git_branch` and `git_sha1` (see example below).

In addition to the keys above, the keys `deployment_repo` and `deployment_branch` can optionally be added to signal to the Lambda function that it should read the `trigger-event.json` file belonging to another GitHub repository in order to determine which state machine to trigger with which input. This can be useful if the triggering GitHub repository only contains application code, while another repository contains the actual infrastructure and deployment code.

### Example
Take the following JSON snippet as an example:
```json
{
  "pipeline_name": "example-state-machine",
  "git_owner": "stekern",
  "git_repo": "my-repo",
  "git_branch":"master",
  "git_sha1": "1234567"
}
```

If your CI service uploads this file to S3 under the key `example-bucket/stekern/my-repo/branches/master/trigger-event.json`, the Lambda will start an execution of a state machine named *example-state-machine* with an input equal to:
```json
{
  "deployment_repo": "my-repo",
  "deployment_branch": "master",
  "deployment_package": "s3://example-bucket/stekern/my-repo/branches/master/124567.zip",
  "pipeline_name": "example-state-machine",
  "git_owner": "stekern",
  "git_repo": "my-repo",
  "git_branch":"master",
  "git_sha1": "1234567"
}
```

Note that the Lambda has augmented the original JSON snippet with three new keys. The Amazon States Language can be used in your state machine definition to refer to the value of the deployment package (e.g., `{ "deployment_package.$": "$.deployment_package" }`), and then utilize this however you'd like (e.g., pass the ZIP file to CodeBuild, ECS, etc.). The remaining input fields serve as a way to store information about who triggered the state machine and with which input.
