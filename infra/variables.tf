variable "bucket_name" {
  description = "Globally-unique S3 bucket name for the dataset portal (data + metadata + built web app)."
  type        = string
}

variable "aws_region" {
  description = "AWS region for the bucket. CloudFront itself is global."
  type        = string
  default     = "us-east-2"
}

variable "publish_role_name" {
  description = "Name for the IAM role/policy the publish pipeline (pipeline/publish.py) assumes to write to the bucket and invalidate CloudFront."
  type        = string
  default     = "als-dataset-portal-publish"
}
