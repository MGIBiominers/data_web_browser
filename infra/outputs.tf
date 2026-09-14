output "bucket_name" {
  value = aws_s3_bucket.portal.bucket
}

output "cloudfront_domain_name" {
  value       = aws_cloudfront_distribution.portal.domain_name
  description = "Use as VITE_METADATA_BASE_URL=https://<this>/metadata for the web app build."
}

output "cloudfront_distribution_id" {
  value       = aws_cloudfront_distribution.portal.id
  description = "Pass to pipeline/publish.py --distribution-id"
}

output "publish_policy_arn" {
  value = aws_iam_policy.publish.arn
}
