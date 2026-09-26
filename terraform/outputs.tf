output "ecr_repository_url" {
  description = "Push the API image here (when enable_ecr = true)."
  value       = try(aws_ecr_repository.api[0].repository_url, null)
}

output "eks_cluster_name" {
  description = "EKS cluster name (when enable_eks = true)."
  value       = try(module.eks[0].cluster_name, null)
}

output "eks_cluster_endpoint" {
  description = "EKS API endpoint (when enable_eks = true)."
  value       = try(module.eks[0].cluster_endpoint, null)
}

output "api_irsa_role_arn" {
  description = "Annotate k8s ServiceAccount anatomy-chatbot-api with this role ARN."
  value       = try(aws_iam_role.api[0].arn, null)
}

output "s3_bucket_name" {
  description = "Frontend static bucket (when enable_frontend = true)."
  value       = try(aws_s3_bucket.frontend[0].id, null)
}

output "cloudfront_distribution_id" {
  description = "CloudFront distribution id for invalidations."
  value       = try(aws_cloudfront_distribution.frontend[0].id, null)
}

output "cloudfront_domain_name" {
  description = "CloudFront domain (https:// + this)."
  value       = try(aws_cloudfront_distribution.frontend[0].domain_name, null)
}

output "frontend_url" {
  description = "Suggested frontend base URL."
  value = try(
    "https://${aws_cloudfront_distribution.frontend[0].domain_name}",
    null
  )
}
