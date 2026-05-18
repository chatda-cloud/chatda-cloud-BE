variable "project" {
  description = "프로젝트 이름. 리소스 name prefix로 사용됩니다."
  type        = string
  default     = "chatda"
}

variable "environment" {
  description = "배포 환경 이름"
  type        = string
  default     = "mvp"
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
}

variable "azs" {
  description = "사용할 Availability Zone 목록. RDS subnet group 때문에 2개 이상 권장."
  type        = list(string)
  default     = ["ap-northeast-2a", "ap-northeast-2c"]
}

variable "vpc_cidr" {
  type    = string
  default = "10.0.0.0/16"
}

variable "public_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.1.0/24", "10.0.2.0/24"]
}

variable "private_subnet_cidrs" {
  type    = list(string)
  default = ["10.0.101.0/24", "10.0.102.0/24"]
}

variable "container_port" {
  description = "FastAPI container port"
  type        = number
  default     = 8000
}

variable "app_image" {
  description = "ECS 최초 생성에 사용할 FastAPI Docker image. 실제 앱 배포 이후의 task definition 변경은 deploy-ecs.yml이 담당합니다."
  type        = string
  default     = "public.ecr.aws/docker/library/python:3.12-slim"
}

variable "ecr_force_delete" {
  description = "terraform destroy 시 ECR repository에 이미지가 남아 있어도 함께 삭제합니다. 운영 환경에서는 false로 바꾸는 것을 권장합니다."
  type        = bool
  default     = true
}

variable "desired_count" {
  description = "MVP 기본 task 수"
  type        = number
  default     = 1
}

variable "db_name" {
  type    = string
  default = "chatda"
}

variable "db_username" {
  type    = string
  default = "chatda_admin"
}

variable "db_password" {
  description = "RDS master password. 8~128자이며 /, @, 큰따옴표, 공백을 포함할 수 없습니다."
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.db_password) >= 8 && length(var.db_password) <= 128 && can(regex("^[^/\\\"@[:space:]]+$", var.db_password))
    error_message = "db_password must be 8-128 characters and must not contain '/', '@', double quote, or whitespace."
  }
}

variable "db_password_secret_recovery_window_in_days" {
  description = "DB password secret 삭제 시 복구 대기 기간. 개발/부트스트랩 환경에서는 같은 이름 재생성을 막지 않도록 0을 기본값으로 둡니다."
  type        = number
  default     = 0

  validation {
    condition     = var.db_password_secret_recovery_window_in_days == 0 || (var.db_password_secret_recovery_window_in_days >= 7 && var.db_password_secret_recovery_window_in_days <= 30)
    error_message = "db_password_secret_recovery_window_in_days must be 0, or between 7 and 30."
  }
}

variable "github_org" {
  description = "GitHub organization 또는 username"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "github_branch" {
  description = "OIDC assume role을 허용할 branch. 기존 terraform.tfvars 호환용이며 github_branches와 함께 허용됩니다."
  type        = string
  default     = "develop"
}

variable "github_branches" {
  description = "OIDC assume role을 허용할 branch 목록"
  type        = list(string)
  default     = ["develop", "main", "feature/gitops-terraform"]
}

variable "github_oidc_provider_arn" {
  description = "기존 GitHub Actions OIDC provider ARN. 비워두면 account에 이미 있는 https://token.actions.githubusercontent.com provider를 조회합니다."
  type        = string
  default     = ""
}

variable "alarm_email" {
  description = "CloudWatch/SNS 알림 수신 이메일. 비워두면 email subscription은 생성하지 않습니다."
  type        = string
  default     = ""
}

variable "fcm_server_key_secret_arn" {
  description = "Google FCM server key를 저장한 Secrets Manager secret ARN. Lambda에서 사용하려면 값을 넣으세요."
  type        = string
  default     = ""
}
