# MCP server infrastructure: one Lambda function (the mcp_server/ app,
# fronted by a public Function URL) plus its two IAM identities. Additive to
# main.tf -- nothing here modifies the existing S3 bucket/CloudFront/publish
# resources, it only reads from and writes to the same bucket (aws_s3_bucket.portal).
#
# NOT applied yet -- same standing rule as main.tf: provisioning real,
# billed AWS resources is a deliberate step the user takes explicitly.
#
# Two separate IAM identities are used deliberately (see s3_clients.py and
# DESIGN.md's "MCP server" section for the full reasoning):
#   - the Lambda's own execution role, for everything except presigning.
#   - a long-lived IAM user (mcp_presign), used ONLY to sign download URLs,
#     because a presigned URL signed with Lambda's own (temporary, STS)
#     execution-role credentials expires when that STS session expires --
#     regardless of the requested ExpiresIn -- typically well under the 24h
#     TTL download links need.
#
# Manual, one-time step required after `terraform apply` (deliberately NOT
# automated -- see the aws_iam_access_key comment below): create the
# mcp_presign user's access key and seed it into the SSM parameter this
# creates as a placeholder.
#   aws iam create-access-key --user-name <mcp_presign user name>
#   aws ssm put-parameter --name <mcp_presign_credentials output> \
#     --type SecureString --overwrite \
#     --value '{"access_key_id": "...", "secret_access_key": "..."}'

# ---------------------------------------------------------------------
# Lambda execution role: everything the function does EXCEPT presigning.
# ---------------------------------------------------------------------

data "aws_iam_policy_document" "mcp_lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "mcp_lambda_exec" {
  name               = "${var.bucket_name}-mcp-lambda-exec"
  assume_role_policy = data.aws_iam_policy_document.mcp_lambda_assume_role.json
}

resource "aws_iam_role_policy_attachment" "mcp_lambda_basic_logs" {
  role       = aws_iam_role.mcp_lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

data "aws_iam_policy_document" "mcp_lambda_exec_policy" {
  statement {
    sid       = "ReadCatalogMetadata"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.portal.arn}/metadata/*"]
  }
  statement {
    sid     = "WriteRequestsAndManifests"
    effect  = "Allow"
    actions = ["s3:PutObject", "s3:GetObject"]
    resources = [
      "${aws_s3_bucket.portal.arn}/manifests/*",
      "${aws_s3_bucket.portal.arn}/requests/*",
    ]
  }
  statement {
    sid       = "ReadPresignCredentialsParam"
    effect    = "Allow"
    actions   = ["ssm:GetParameter"]
    resources = [aws_ssm_parameter.mcp_presign_credentials.arn]
  }
}

resource "aws_iam_role_policy" "mcp_lambda_exec" {
  name   = "${var.bucket_name}-mcp-lambda-exec"
  role   = aws_iam_role.mcp_lambda_exec.id
  policy = data.aws_iam_policy_document.mcp_lambda_exec_policy.json
}

# ---------------------------------------------------------------------
# Presign identity: a dedicated, long-lived IAM user used ONLY to sign
# download URLs -- never assumed as a role, never used for anything else.
# ---------------------------------------------------------------------

resource "aws_iam_user" "mcp_presign" {
  name = "${var.bucket_name}-mcp-presign"
}

data "aws_iam_policy_document" "mcp_presign_policy" {
  statement {
    sid     = "PresignProcessedFilesAndManifests"
    effect  = "Allow"
    actions = ["s3:GetObject"]
    resources = [
      "${aws_s3_bucket.portal.arn}/processed/*",
      "${aws_s3_bucket.portal.arn}/manifests/*",
    ]
  }
}

resource "aws_iam_user_policy" "mcp_presign" {
  name   = "${var.bucket_name}-mcp-presign"
  user   = aws_iam_user.mcp_presign.name
  policy = data.aws_iam_policy_document.mcp_presign_policy.json
}

# Deliberately NOT an aws_iam_access_key resource -- that would put the
# secret access key in Terraform state permanently. This parameter is
# created with a placeholder value and never touched again by Terraform
# (lifecycle.ignore_changes); the real key is created and stored via the
# `aws iam create-access-key` / `aws ssm put-parameter` commands documented
# at the top of this file, as a one-time manual step after `apply`.
resource "aws_ssm_parameter" "mcp_presign_credentials" {
  name  = "/${var.bucket_name}/mcp-presign-credentials"
  type  = "SecureString"
  value = "PLACEHOLDER -- set via: aws ssm put-parameter --overwrite (see infra/mcp.tf header comment)"

  lifecycle {
    ignore_changes = [value]
  }
}

# ---------------------------------------------------------------------
# The Lambda function itself.
# ---------------------------------------------------------------------

# Zips whatever's already on disk under mcp_server/build/ -- Terraform does
# NOT run `pip install` for you. Run mcp_server/build.sh first (or on every
# code change); a failed pip install inside a Terraform provisioner would be
# far harder to debug than running it directly in a terminal.
data "archive_file" "mcp_lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../mcp_server/build"
  output_path = "${path.module}/../mcp_server/build.zip"
}

resource "aws_lambda_function" "mcp" {
  function_name    = "${var.bucket_name}-mcp"
  role             = aws_iam_role.mcp_lambda_exec.arn
  runtime          = "python3.12"
  architectures    = ["x86_64"]
  handler          = "run.sh" # unused by the Web Adapter, but required by the API
  filename         = data.archive_file.mcp_lambda.output_path
  source_code_hash = data.archive_file.mcp_lambda.output_base64sha256
  memory_size      = 512
  timeout          = 30

  layers = [var.lambda_web_adapter_layer_arn]

  environment {
    variables = {
      AWS_LAMBDA_EXEC_WRAPPER = "/opt/bootstrap"
      AWS_LWA_PORT            = "8000"
      PORT                    = "8000"
      BUCKET_NAME             = aws_s3_bucket.portal.bucket
      # Explicit, not relying on Lambda's own AWS_REGION -- see s3_clients.py's
      # comment: it wasn't reliably present when actually tested end to end.
      S3_REGION                        = var.aws_region
      PRESIGN_CREDENTIALS_PARAM        = aws_ssm_parameter.mcp_presign_credentials.name
      DOWNLOAD_LINK_MANIFEST_THRESHOLD = "5"
      PRESIGN_TTL_SECONDS              = "86400"
    }
  }
}

resource "aws_lambda_function_url" "mcp" {
  function_name      = aws_lambda_function.mcp.function_name
  authorization_type = "NONE"
}

# Required alongside the Function URL resource above for AuthType=NONE to
# actually be publicly invocable -- easy to forget, since the Function URL
# resource alone looks sufficient but silently isn't.
resource "aws_lambda_permission" "mcp_public_invoke" {
  statement_id           = "AllowPublicInvokeFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.mcp.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}

# Generated download manifests are meant to be short-lived (the presigned
# URLs inside them expire after 24h anyway) -- clean them up automatically
# rather than letting them accumulate forever.
resource "aws_s3_bucket_lifecycle_configuration" "manifests_ttl" {
  bucket = aws_s3_bucket.portal.id

  rule {
    id     = "expire-manifests"
    status = "Enabled"
    filter {
      prefix = "manifests/"
    }
    expiration {
      days = 3
    }
  }
}
