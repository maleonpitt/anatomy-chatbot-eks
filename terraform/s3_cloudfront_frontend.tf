resource "random_id" "frontend_suffix" {
  count       = var.enable_frontend ? 1 : 0
  byte_length = 4
}

resource "aws_s3_bucket" "frontend" {
  count  = var.enable_frontend ? 1 : 0
  bucket = "${var.project_name}-frontend-${var.environment}-${random_id.frontend_suffix[0].hex}"
}

resource "aws_s3_bucket_public_access_block" "frontend" {
  count  = var.enable_frontend ? 1 : 0
  bucket = aws_s3_bucket.frontend[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "frontend" {
  count  = var.enable_frontend ? 1 : 0
  bucket = aws_s3_bucket.frontend[0].id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_cloudfront_origin_access_control" "frontend" {
  count                             = var.enable_frontend ? 1 : 0
  name                              = "${var.project_name}-${var.environment}-oac"
  description                       = "OAC for ${var.project_name} frontend"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

locals {
  use_custom_domain  = var.enable_frontend && length(var.domain_aliases) > 0 && var.acm_certificate_arn != ""
  api_origin_enabled = var.enable_frontend && trimspace(var.api_origin_domain) != ""
}

data "aws_cloudfront_cache_policy" "caching_disabled" {
  count = local.api_origin_enabled ? 1 : 0
  name  = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host_header" {
  count = local.api_origin_enabled ? 1 : 0
  name  = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "frontend" {
  count               = var.enable_frontend ? 1 : 0
  enabled             = true
  is_ipv6_enabled     = true
  default_root_object = "index.html"
  price_class         = "PriceClass_100"
  comment             = "${var.project_name} ${var.environment} frontend"
  aliases             = local.use_custom_domain ? var.domain_aliases : []

  origin {
    domain_name              = aws_s3_bucket.frontend[0].bucket_regional_domain_name
    origin_id                = "s3-frontend"
    origin_access_control_id = aws_cloudfront_origin_access_control.frontend[0].id
  }

  dynamic "origin" {
    for_each = local.api_origin_enabled ? [1] : []
    content {
      domain_name = var.api_origin_domain
      origin_id   = "alb-api"

      custom_origin_config {
        http_port              = 80
        https_port             = 443
        origin_protocol_policy = "https-only"
        origin_ssl_protocols   = ["TLSv1.2"]
        origin_read_timeout    = 60
      }
    }
  }

  dynamic "ordered_cache_behavior" {
    for_each = local.api_origin_enabled ? [1] : []
    content {
      path_pattern     = "/api/*"
      target_origin_id = "alb-api"
      allowed_methods  = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
      cached_methods   = ["GET", "HEAD"]

      viewer_protocol_policy = "redirect-to-https"
      compress               = false

      cache_policy_id          = data.aws_cloudfront_cache_policy.caching_disabled[0].id
      origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host_header[0].id
    }
  }

  default_cache_behavior {
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    target_origin_id       = "s3-frontend"
    viewer_protocol_policy = "redirect-to-https"
    compress               = true

    forwarded_values {
      query_string = false
      cookies {
        forward = "none"
      }
    }
  }

  custom_error_response {
    error_code         = 403
    response_code      = 200
    response_page_path = "/index.html"
  }
  custom_error_response {
    error_code         = 404
    response_code      = 200
    response_page_path = "/index.html"
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = !local.use_custom_domain
    acm_certificate_arn            = local.use_custom_domain ? var.acm_certificate_arn : null
    ssl_support_method             = local.use_custom_domain ? "sni-only" : null
    minimum_protocol_version       = local.use_custom_domain ? "TLSv1.2_2021" : "TLSv1"
  }
}

resource "aws_s3_bucket_policy" "frontend" {
  count  = var.enable_frontend ? 1 : 0
  bucket = aws_s3_bucket.frontend[0].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "AllowCloudFrontRead"
        Effect = "Allow"
        Principal = {
          Service = "cloudfront.amazonaws.com"
        }
        Action   = ["s3:GetObject"]
        Resource = ["${aws_s3_bucket.frontend[0].arn}/*"]
        Condition = {
          StringEquals = {
            "AWS:SourceArn" = aws_cloudfront_distribution.frontend[0].arn
          }
        }
      }
    ]
  })
}
