# GitOps & Terraform Setup Guide

이 문서는 `chatda-cloud-BE` 리포지토리에서 Terraform 인프라와 GitHub Actions 기반 배포를 운영하는 방법을 정리합니다.

## 1. 현재 구성

인프라 코드는 `infra/`에서 관리합니다. GitHub Actions는 AWS 장기 Access Key 대신 OIDC로 AWS IAM Role을 assume합니다.

현재 Terraform 구성의 주요 리소스는 다음과 같습니다.

| 영역 | 리소스 |
|---|---|
| 네트워크 | VPC, public/private subnet, route table, security group |
| API | ECS Fargate Spot service, ALB, CloudFront, WAF |
| 이미지 | ECR repository |
| DB | RDS PostgreSQL, Secrets Manager DB password secret |
| 업로드 | S3 images bucket, Lambda presigned URL, API Gateway HTTP API |
| 알림 | SNS topic, CloudWatch alarms |
| GitOps | GitHub Actions OIDC provider 조회, Terraform role, deploy role |

ECS FastAPI task는 ARM64 Fargate Spot으로 실행합니다.

```hcl
cpu    = "2048"
memory = "4096"
```

서비스 기본 task 수는 `desired_count = 1`입니다. ALB target group의 deregistration delay는 30초로 설정되어 있습니다.

## 2. 최초 1회 로컬 부트스트랩

GitHub Actions가 OIDC로 AWS에 접근하려면 AWS 계정 안에 GitHub Actions용 IAM Role이 먼저 있어야 합니다. 최초 1회는 로컬에서 관리자 권한 AWS 자격 증명으로 Terraform을 적용합니다.

부트스트랩의 목표는 다음 리소스를 한 번에 만드는 것입니다.

- FastAPI를 실행할 ECS/Fargate, ALB, CloudFront
- 이미지 저장소인 ECR
- PostgreSQL RDS와 DB password secret
- 이미지 업로드용 S3, presigned URL Lambda, API Gateway
- GitHub Actions가 사용할 OIDC IAM Role

### 2.1 사전 확인

로컬에 AWS CLI와 Terraform이 설치되어 있어야 합니다.

```bash
aws --version
terraform version
```

AWS CLI가 대상 계정을 보고 있는지 확인합니다.

```bash
aws sts get-caller-identity
```

출력되는 `Account`가 실제 배포할 AWS 계정인지 확인합니다.

### 2.2 AWS 자격 증명 준비

관리자 권한이 있는 임시 AWS 자격 증명을 환경 변수로 등록합니다.

```bash
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="ap-northeast-2"
```

세션 토큰을 사용하는 계정이면 `AWS_SESSION_TOKEN`도 함께 등록합니다.

```bash
export AWS_SESSION_TOKEN="..."
```

### 2.3 Terraform 변수 파일 준비

프로젝트 루트에서 `infra/`로 이동하고 변수 파일을 만듭니다.

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars
```

`terraform.tfvars`에서 GitHub 저장소 정보를 Actions가 실행될 저장소와 정확히 맞춥니다.

```hcl
github_org  = "YOUR_GITHUB_OWNER"   # 예시: "chatda-cloud"
github_repo = "chatda-cloud-BE"
```

Actions를 실행할 브랜치는 `github_branches`에 포함되어야 합니다.

```hcl
github_branches = ["develop", "main", "feature/gitops-terraform"]
```

DB password도 실제 운영에 사용할 값으로 설정합니다. 비밀번호는 8~128자이며 `/`, `@`, 큰따옴표, 공백을 포함할 수 없습니다.

```hcl
db_password = "CHANGE_ME_TO_A_STRONG_PASSWORD"
```

### 2.4 Terraform 초기화와 계획 확인

provider와 module을 초기화합니다.

```bash
terraform init
```

문법과 provider 구성을 검증합니다.

```bash
terraform validate
```

생성될 리소스를 확인합니다.

```bash
terraform plan
```

`plan`에서 생성 대상이 너무 많아 보이는 것은 정상입니다. 최초 부트스트랩은 VPC, ECS, RDS, CloudFront, Lambda, IAM Role 등을 한 번에 만듭니다.

### 2.5 Terraform 적용

계획이 맞으면 적용합니다.

```bash
terraform apply
```

적용 중 `yes`를 입력합니다. 완료까지 몇 분 걸릴 수 있습니다. 특히 RDS와 CloudFront는 생성 시간이 길 수 있습니다.

완료되면 출력된 role ARN을 기록합니다.

```text
github_actions_terraform_role_arn
github_actions_role_arn
```

이 두 값은 다음 단계에서 GitHub Actions Secret에 등록합니다.

### 2.6 배포 상태 확인

Terraform 적용 직후에는 AWS 리소스가 만들어졌는지 먼저 확인합니다.

```bash
terraform output
```

CloudFront 도메인을 따로 뽑아 확인할 수도 있습니다.

```bash
terraform output -raw cloudfront_domain_name
```

ECS service 상태를 확인합니다.

```bash
aws ecs describe-services \
  --cluster chatda-mvp-cluster \
  --services chatda-mvp-fastapi \
  --region ap-northeast-2 \
  --query 'services[0].{status:status,desired:desiredCount,running:runningCount,pending:pendingCount,taskDefinition:taskDefinition}'
```

`desired`와 `running`이 모두 `1`이면 task가 실행 중입니다.

Target group health도 확인합니다. 먼저 target group ARN을 조회합니다.

```bash
aws elbv2 describe-target-groups \
  --names chatda-mvp-tg \
  --region ap-northeast-2 \
  --query 'TargetGroups[0].TargetGroupArn' \
  --output text
```

조회한 ARN으로 target health를 확인합니다.

```bash
aws elbv2 describe-target-health \
  --target-group-arn "<TARGET_GROUP_ARN>" \
  --region ap-northeast-2
```

target 상태가 `healthy`이면 ALB가 ECS task를 정상 대상으로 보고 있는 것입니다.

### 2.7 헬스체크

CloudFront 도메인으로 `/health`를 호출합니다.

```bash
CF_DOMAIN="$(terraform output -raw cloudfront_domain_name)"
curl -i "https://${CF_DOMAIN}/health"
```

정상 응답은 다음과 같습니다.

```http
HTTP/2 200
```

```json
{"status":"ok","env":"production"}
```

HTTP로 호출하면 CloudFront 설정에 의해 HTTPS로 redirect됩니다.

```bash
curl -i "http://${CF_DOMAIN}/health"
```

예상 응답:

```http
HTTP/1.1 301 Moved Permanently
Location: https://<cloudfront-domain>/health
```

배포 직후에는 ECS task 시작, ALB target 등록, CloudFront origin 연결 때문에 일시적으로 502가 보일 수 있습니다. 1~3분 뒤 다시 확인하고, 계속 실패하면 ECS service event와 target group health를 먼저 확인합니다.

## 3. GitHub Secrets

GitHub repository의 `Settings` > `Secrets and variables` > `Actions`에 아래 값을 등록합니다.

| Secret | 값 |
|---|---|
| `AWS_TERRAFORM_ROLE_ARN` | Terraform output의 `github_actions_terraform_role_arn` |
| `AWS_DEPLOY_ROLE_ARN` | Terraform output의 `github_actions_role_arn` |
| `TF_VAR_DB_PASSWORD` | RDS master password |

기존 `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` secret은 사용하지 않습니다.

아래 값은 기본 이름을 그대로 쓰면 생략할 수 있습니다. 리소스 이름을 바꿨을 때만 Secret 또는 Variable로 override합니다.

| 선택 항목 | 기본값 |
|---|---|
| `ECR_REPOSITORY` | `chatda-mvp-fastapi` |
| `ECS_CLUSTER` | `chatda-mvp-cluster` |
| `ECS_SERVICE` | `chatda-mvp-fastapi` |
| `ECS_TASK_DEFINITION` | `chatda-mvp-fastapi` |
| `CONTAINER_NAME` | `fastapi` |
| `LAMBDA_FUNCTION_NAME` | `chatda-mvp-presigned-url` |

## 4. GitHub Actions 워크플로우

### Terraform

파일: `.github/workflows/terraform.yml`

자동 실행 조건:

- `develop`, `main`, `feature/gitops-terraform` 브랜치 push
- 변경 경로가 `infra/**` 또는 `.github/workflows/terraform.yml`

수동 실행:

- GitHub Actions 탭에서 `Terraform` 선택
- `Run workflow`
- `plan`, `apply`, `destroy` 중 선택

workflow 내부에서는 다음을 수행합니다.

```text
checkout
configure AWS credentials with OIDC
terraform init
terraform validate
required secrets check
terraform plan
terraform apply 또는 destroy
```

### Deploy to ECS

파일: `.github/workflows/deploy-ecs.yml`

자동 실행 조건:

- `develop`, `main`, `feature/gitops-terraform` 브랜치 push
- 변경 경로가 `app/**`, `Dockerfile`, `requirements.txt`, `.github/workflows/deploy-ecs.yml`

수동 실행:

- GitHub Actions 탭에서 `Deploy to ECS` 선택
- `Run workflow`

workflow 내부에서는 ARM64 Docker image를 빌드하고 ECR에 `github.sha`, `latest` 태그로 push한 뒤 ECS service에 배포합니다.

### Deploy Lambda

파일: `.github/workflows/deploy-lambda.yml`

자동 실행 조건:

- `develop`, `main` 브랜치 push
- 변경 경로가 `lambda/**`

workflow 내부에서는 `lambda/requirements.txt` 의존성을 패키징하고 `lambda/handler.py`를 포함해 Lambda function code를 업데이트합니다.

## 5. Terraform Outputs 예시

아래는 형식을 보여주기 위한 예시입니다. 실제 값은 `terraform output`으로 확인합니다.

```text
alb_dns_name = "chatda-mvp-alb-1234567890.ap-northeast-2.elb.amazonaws.com"
cloudfront_domain_name = "d1exampleabc123.cloudfront.net"
db_password_secret_name = "chatda-mvp/db/password-a1b2c3d4"
ecr_repository_url = "123456789012.dkr.ecr.ap-northeast-2.amazonaws.com/chatda-mvp-fastapi"
github_actions_role_arn = "arn:aws:iam::123456789012:role/chatda-mvp-github-actions-role"
github_actions_terraform_role_arn = "arn:aws:iam::123456789012:role/chatda-mvp-github-actions-terraform-role"
presigned_url_api_endpoint = "https://abc123def4.execute-api.ap-northeast-2.amazonaws.com/presigned-url"
rds_endpoint = "chatda-mvp-postgres.abc123xyz789.ap-northeast-2.rds.amazonaws.com:5432"
s3_images_bucket = "chatda-mvp-images-a1b2c3d4"
sns_push_alerts_topic_arn = "arn:aws:sns:ap-northeast-2:123456789012:chatda-mvp-push-alerts"
```

운영 API 확인은 CloudFront 도메인으로 합니다.

```bash
CF_DOMAIN="$(terraform output -raw cloudfront_domain_name)"
curl -i "https://${CF_DOMAIN}/health"
```

정상 응답:

```json
{"status":"ok","env":"production"}
```
