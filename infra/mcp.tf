# MCP server infrastructure: one Lambda function (the mcp_server/ app,
# fronted by a public Function URL) plus its execution role. Additive to
# main.tf -- nothing here modifies the existing S3 bucket/CloudFront/publish
# resources, it only reads from and writes to the same bucket (aws_s3_bucket.portal).
#
# Reactivated 2026-09-18 after a period marked deprecated -- see DESIGN.md's
# "MCP server reactivated" section. This version is deliberately simpler
# than the original: get_data_locations replaced get_download_links, so the
# server never hands out a copy of any file (presigned or otherwise) -- it
# only ever returns the real HTCF path where data already lives. That
# removed the entire reason a second, long-lived IAM identity existed (see
# git history for the old presign-user/SSM-parameter setup this file used
# to have): one execution role is now enough for everything this server
# does.

# ---------------------------------------------------------------------
# Lambda execution role.
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
    sid     = "ReadWriteDownloadRequestQueue"
    effect  = "Allow"
    actions = ["s3:PutObject", "s3:GetObject"]
    resources = [
      "${aws_s3_bucket.portal.arn}/requests/*",
    ]
  }
}

resource "aws_iam_role_policy" "mcp_lambda_exec" {
  name   = "${var.bucket_name}-mcp-lambda-exec"
  role   = aws_iam_role.mcp_lambda_exec.id
  policy = data.aws_iam_policy_document.mcp_lambda_exec_policy.json
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
  # Bumped from 512/30 on 2026-09-28 for gene_presence: its backing
  # artifact (metadata/gene_presence.json) is 103MB of raw JSON, which
  # parses into Python objects at roughly 1.5-2.5x that size -- close
  # enough to the old 512MB limit to risk an OOM on the very first call
  # after a cold start. Timeout bumped alongside it to give a cold start
  # enough room to download + parse that file over S3, not just execute.
  memory_size = 1024
  timeout     = 60

  layers = [var.lambda_web_adapter_layer_arn]

  environment {
    variables = {
      AWS_LAMBDA_EXEC_WRAPPER = "/opt/bootstrap"
      AWS_LWA_PORT            = "8000"
      PORT                    = "8000"
      BUCKET_NAME             = aws_s3_bucket.portal.bucket
      # Explicit, not relying on Lambda's own AWS_REGION -- see s3_clients.py's
      # comment: it wasn't reliably present when actually tested end to end.
      S3_REGION = var.aws_region
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
