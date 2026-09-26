variable "aws_region" {
  type        = string
  description = "AWS region for ECR / EKS / regional resources."
  default     = "us-east-1"
}

variable "project_name" {
  type        = string
  description = "Short name prefix for resources."
  default     = "anatomy-chatbot"
}

variable "environment" {
  type        = string
  description = "Environment label (dev, staging, prod)."
  default     = "dev"
}

variable "enable_ecr" {
  type        = bool
  description = "Create ECR repository for the API image."
  default     = true
}

variable "enable_eks" {
  type        = bool
  description = "Create VPC + EKS cluster. Default false so accidental apply is safer in practice repos."
  default     = false
}

variable "enable_frontend" {
  type        = bool
  description = "Create private S3 + CloudFront for the React SPA."
  default     = true
}

variable "eks_cluster_version" {
  type        = string
  description = "Kubernetes version for EKS."
  default     = "1.29"
}

variable "eks_node_instance_types" {
  type        = list(string)
  description = "Instance types for the default managed node group."
  default     = ["t3.medium"]
}

variable "eks_desired_size" {
  type        = number
  description = "Desired nodes in the managed node group."
  default     = 2
}

variable "api_origin_domain" {
  type        = string
  description = "Optional HTTPS origin hostname for CloudFront /api/* (e.g. api.example.com ALB DNS)."
  default     = ""
}

variable "domain_aliases" {
  type        = list(string)
  description = "Optional CloudFront aliases (custom domain)."
  default     = []
}

variable "acm_certificate_arn" {
  type        = string
  description = "ACM cert ARN in us-east-1 for CloudFront aliases."
  default     = ""
}
