output "aws_region" {
  description = "The AWS region where resources are deployed"
  value       = var.aws_region
}

output "ecr_repository_url" {
  description = "The URL of the ECR repository for the backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_bucket_name" {
  description = "The name of the S3 bucket hosting the frontend static files"
  value       = aws_s3_bucket.frontend.id
}

output "cloudfront_distribution_id" {
  description = "The ID of the CloudFront distribution"
  value       = aws_cloudfront_distribution.cdn.id
}

output "cloudfront_domain_name" {
  description = "The domain name of the CloudFront distribution"
  value       = aws_cloudfront_distribution.cdn.domain_name
}

output "rds_endpoint" {
  description = "The connection endpoint for the RDS PostgreSQL database"
  value       = aws_db_instance.postgres.endpoint
}



output "db_password" {
  description = "The dynamically generated master database password"
  value       = random_password.db_password.result
  sensitive   = true
}
