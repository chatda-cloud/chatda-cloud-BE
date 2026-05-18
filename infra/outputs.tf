output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "alb_dns_name" {
  value = aws_lb.app.dns_name
}

output "cloudfront_domain_name" {
  value = aws_cloudfront_distribution.app.domain_name
}

output "presigned_url_api_endpoint" {
  value = "${aws_apigatewayv2_api.presigned.api_endpoint}/presigned-url"
}

output "s3_images_bucket" {
  value = aws_s3_bucket.images.bucket
}

output "rds_endpoint" {
  value = aws_db_instance.postgres.endpoint
}

output "db_password_secret_name" {
  description = "ECS task가 참조하는 DB password Secrets Manager secret 이름"
  value       = aws_secretsmanager_secret.db_password.name
}

output "github_actions_role_arn" {
  value = aws_iam_role.github_actions.arn
}

output "github_actions_terraform_role_arn" {
  description = "Terraform 관리용 OIDC role ARN — AWS_TERRAFORM_ROLE_ARN secret에 등록"
  value       = aws_iam_role.github_actions_terraform.arn
}

output "sns_push_alerts_topic_arn" {
  value = aws_sns_topic.push_alerts.arn
}
