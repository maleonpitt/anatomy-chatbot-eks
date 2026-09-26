# IRSA-oriented IAM role for the API ServiceAccount (anatomy-chatbot-api).
# Only created when EKS is enabled. Attach DynamoDB / Secrets Manager policies as needed.

data "aws_iam_policy_document" "api_assume" {
  count = var.enable_eks ? 1 : 0

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [module.eks[0].oidc_provider_arn]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(module.eks[0].oidc_provider, "https://", "")}:sub"
      values   = ["system:serviceaccount:anatomy-chatbot:anatomy-chatbot-api"]
    }

    condition {
      test     = "StringEquals"
      variable = "${replace(module.eks[0].oidc_provider, "https://", "")}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "api" {
  count = var.enable_eks ? 1 : 0

  name               = "${var.project_name}-${var.environment}-api"
  assume_role_policy = data.aws_iam_policy_document.api_assume[0].json
}

# Least-privilege stubs — tighten resource ARNs before production apply.
data "aws_iam_policy_document" "api_permissions" {
  count = var.enable_eks ? 1 : 0

  statement {
    sid    = "DynamoDBAppTables"
    effect = "Allow"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
      "dynamodb:UpdateItem",
    ]
    resources = ["*"] # replace with table ARNs
  }

  statement {
    sid    = "SecretsManagerRead"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = ["*"] # replace with anatomy-chatbot/backend secret ARN
  }
}

resource "aws_iam_role_policy" "api" {
  count = var.enable_eks ? 1 : 0

  name   = "${var.project_name}-${var.environment}-api"
  role   = aws_iam_role.api[0].id
  policy = data.aws_iam_policy_document.api_permissions[0].json
}
