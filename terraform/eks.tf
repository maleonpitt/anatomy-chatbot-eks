# Optional VPC + EKS (disabled by default). Enable with enable_eks = true after review.
# Uses widely adopted community modules — industry-standard shape for greenfield EKS.

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"
  count   = var.enable_eks ? 1 : 0

  name = "${var.project_name}-${var.environment}"
  cidr = "10.42.0.0/16"

  azs             = slice(data.aws_availability_zones.available[0].names, 0, 2)
  private_subnets = ["10.42.1.0/24", "10.42.2.0/24"]
  public_subnets  = ["10.42.101.0/24", "10.42.102.0/24"]

  enable_nat_gateway = true
  single_nat_gateway = true

  public_subnet_tags = {
    "kubernetes.io/role/elb" = 1
  }
  private_subnet_tags = {
    "kubernetes.io/role/internal-elb" = 1
  }
}

data "aws_availability_zones" "available" {
  count = var.enable_eks ? 1 : 0
  state = "available"
}

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"
  count   = var.enable_eks ? 1 : 0

  cluster_name    = "${var.project_name}-${var.environment}"
  cluster_version = var.eks_cluster_version

  vpc_id     = module.vpc[0].vpc_id
  subnet_ids = module.vpc[0].private_subnets

  cluster_endpoint_public_access = true

  eks_managed_node_groups = {
    default = {
      instance_types = var.eks_node_instance_types
      desired_size   = var.eks_desired_size
      min_size       = 1
      max_size       = 4
    }
  }

  # Grant the creator admin access (adjust for real teams / SSO roles)
  enable_cluster_creator_admin_permissions = true
}
