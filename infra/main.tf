# ALS dataset portal infrastructure: one S3 bucket holding processed data,
# metadata JSON, and the built web app; one CloudFront distribution in front
# of it; one IAM policy for the publish pipeline. See ../DESIGN.md for the
# reasoning behind this shape.
#
# NOT applied yet as of this writing -- see DESIGN.md's "Not yet done"
# section. Provisioning real, billed AWS resources is a deliberate step the
# user takes explicitly (choosing a bucket name/region), not something to
# run automatically from a plan.

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

resource "aws_s3_bucket" "portal" {
  bucket = var.bucket_name
}

# No public bucket policy / ACLs anywhere -- CloudFront reads via Origin
# Access Control (below), never the public internet reading S3 directly.
resource "aws_s3_bucket_public_access_block" "portal" {
  bucket                  = aws_s3_bucket.portal.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "portal" {
  name                              = "${var.bucket_name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Two origins pointed at the same bucket, differing only in OriginPath, so
# cache behaviors can route /web/* (the built SPA) and /metadata/,/processed/
# (data) differently without needing separate buckets.
resource "aws_cloudfront_distribution" "portal" {
  enabled             = true
  default_root_object = "index.html"
  comment             = "ALS dataset portal (data_web_browser)"

  origin {
    domain_name              = aws_s3_bucket.portal.bucket_regional_domain_name
    origin_id                = "web"
    origin_path              = "/web"
    origin_access_control_id = aws_cloudfront_origin_access_control.portal.id
  }

  origin {
    domain_name              = aws_s3_bucket.portal.bucket_regional_domain_name
    origin_id                = "data"
    origin_access_control_id = aws_cloudfront_origin_access_control.portal.id
  }

  default_cache_behavior {
    target_origin_id       = "web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
    min_ttl     = 0
    default_ttl = 300
    max_ttl     = 3600
  }

  # Metadata is small and changes on every publish run -- keep TTLs at zero
  # and rely on publish.py's explicit invalidation for "visible right away";
  # a nonzero TTL here would just mean the invalidation is the only thing
  # standing between an old and new view.
  ordered_cache_behavior {
    path_pattern           = "/metadata/*"
    target_origin_id       = "data"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    forwarded_values {
      query_string = true # api.js cache-busts with ?t=<timestamp>
      cookies { forward = "none" }
    }
    min_ttl     = 0
    default_ttl = 0
    max_ttl     = 0
  }

  # Processed data files are large and effectively immutable (a changed
  # file gets a new sha256 in its receipt, but keeps the same S3 key) --
  # cache aggressively, and rely on publish.py's per-study invalidation for
  # the rare case a file at an existing key actually changes.
  ordered_cache_behavior {
    path_pattern           = "/processed/*"
    target_origin_id       = "data"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = false
    forwarded_values {
      query_string = false
      cookies { forward = "none" }
    }
    min_ttl     = 0
    default_ttl = 86400
    max_ttl     = 604800
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

data "aws_iam_policy_document" "bucket_policy" {
  statement {
    sid    = "AllowCloudFrontReadViaOAC"
    effect = "Allow"
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.portal.arn}/*"]
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.portal.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "portal" {
  bucket = aws_s3_bucket.portal.id
  policy = data.aws_iam_policy_document.bucket_policy.json
}

data "aws_iam_policy_document" "publish_policy" {
  statement {
    sid       = "ReadWriteBucket"
    effect    = "Allow"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket"]
    resources = [aws_s3_bucket.portal.arn, "${aws_s3_bucket.portal.arn}/*"]
  }
  statement {
    sid       = "InvalidateDistribution"
    effect    = "Allow"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [aws_cloudfront_distribution.portal.arn]
  }
}

# A standalone policy, not bound to a specific principal -- attach it to
# whichever IAM user/role actually runs pipeline/publish.py (e.g. the
# user's own IAM user, if run interactively/from HTCF with configured
# credentials, as is already the case per the existing `aws configure list`
# default profile on this machine).
resource "aws_iam_policy" "publish" {
  name        = var.publish_role_name
  description = "Permissions for pipeline/publish.py: write bucket, invalidate CloudFront"
  policy      = data.aws_iam_policy_document.publish_policy.json
}
