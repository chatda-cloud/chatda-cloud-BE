# chatda-cloud-BE

> AI 기반 캠퍼스 분실물 스마트 매칭 플랫폼
> FastAPI + PostgreSQL + pgvector + CLIP + Gemini

---

## 기술 스택

| 구분      | 기술                                             |
| --------- | ------------------------------------------------ |
| Framework | FastAPI (Async)                                  |
| Runtime   | Python 3.11+                                     |
| Database  | PostgreSQL 15 + pgvector                         |
| ORM       | SQLAlchemy 2.0 (Async)                           |
| AI        | OpenAI CLIP / Gemini 2.5 Flash / AWS Rekognition |
| Storage   | AWS S3                                           |
| 알림      | AWS SNS / FCM                                    |
| 배포      | AWS ECS (app/) + AWS Lambda (lambda/)            |

---

## 프로젝트 구조

```
chatda-cloud-BE/
├── app/                    # ECS에서 실행 (FastAPI)
│   ├── main.py             # 라우터 등록, 앱 초기화
│   ├── db.py               # DB 연결 (Async SQLAlchemy)
│   ├── models.py           # SQLAlchemy 모델
│   ├── dependencies.py     # JWT 인증 등 공통 의존성
│   ├── config.py           # 환경변수 관리
│   ├── auth/               # 로그인 / 토큰
│   ├── users/              # 유저 CRUD
│   ├── items/              # 분실물 / 습득물 등록
│   ├── tagging/            # CLIP / Gemini / Rekognition
│   └── matching/           # pgvector 유사도 매칭
├── lambda/                 # S3 Presigned URL 발급
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

---

## 로컬 개발 환경 세팅

### 1. 사전 준비

- Python 3.11 이상
- PostgreSQL 15 이상 (pgvector 익스텐션 포함)
- Git

### 2. 저장소 클론

```bash
git clone https://github.com/chatda-cloud/chatda-cloud-BE.git
cd chatda-cloud-BE
```

### 3. 가상환경 생성 및 활성화

가상환경을 사용하면 패키지가 프로젝트 안에만 설치되어 다른 프로젝트와 버전 충돌이 없습니다.

```bash
# 생성
python -m venv venv

# 활성화
source venv/bin/activate        # Mac / Linux
venv\Scripts\activate           # Windows PowerShell
```

활성화되면 터미널 앞에 `(venv)` 가 붙습니다.

```bash
(venv) PS C:\chatda-cloud-BE>    # 활성화 확인
```

### 4. 패키지 설치

```bash
pip install -r requirements.txt
```

> **참고 (Windows / CPU 전용 환경)**  
> torch를 CPU 버전으로 설치하면 용량을 크게 줄일 수 있습니다.
>
> ```bash
> pip install torch --index-url https://download.pytorch.org/whl/cpu
> pip install -r requirements.txt
> ```

### 5. 환경변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 아래 항목을 실제 값으로 수정합니다.

```env
# 필수 수정 항목
DATABASE_URL=postgresql+asyncpg://유저:비밀번호@localhost:5432/chatda
SECRET_KEY=랜덤_32바이트_문자열     # openssl rand -hex 32
GEMINI_API_KEY=발급받은_키
AWS_ACCESS_KEY_ID=발급받은_키
AWS_SECRET_ACCESS_KEY=발급받은_키
S3_BUCKET_NAME=버킷명
SNS_TOPIC_ARN=ARN_주소
```

> **SECRET_KEY 생성 방법**
>
> ```bash
> openssl rand -hex 32
> ```

### 6. PostgreSQL pgvector 익스텐션 활성화

DB에 접속 후 한 번만 실행하면 됩니다.

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 7. 서버 실행

```bash
# 반드시 프로젝트 루트(chatda-cloud-BE/)에서 실행
uvicorn app.main:app --reload --port 8000
```

정상 실행되면 아래 주소로 확인합니다.

| 주소                         | 설명                     |
| ---------------------------- | ------------------------ |
| http://localhost:8000/health | 서버 생존 확인           |
| http://localhost:8000/docs   | Swagger UI (개발 환경만) |
| http://localhost:8000/redoc  | ReDoc (개발 환경만)      |

---

## 자주 발생하는 에러

### `Attribute "app" not found in module "app.main"`

임포트 실패로 `app` 객체 생성 전에 죽은 것입니다. 아래 명령어로 실제 원인을 확인합니다.

```bash
python -c "from app.main import app"
```

주요 원인은 세 가지입니다.

**① `__init__.py` 누락**

```bash
touch app/__init__.py
touch app/auth/__init__.py
touch app/users/__init__.py
touch app/items/__init__.py
touch app/tagging/__init__.py
touch app/matching/__init__.py
```

**② 실행 위치 오류** — 반드시 `chatda-cloud-BE/` 루트에서 실행

```bash
cd chatda-cloud-BE       # 여기서 실행
uvicorn app.main:app --reload --port 8000
```

**③ 가상환경 미활성화** — `(venv)` 확인 후 재실행

```bash
source venv/bin/activate    # Mac / Linux
venv\Scripts\activate       # Windows
```

### `DATABASE_URL must use asyncpg driver`

`.env`의 `DATABASE_URL` 프로토콜을 확인합니다.

```env
# X  틀림
DATABASE_URL=postgresql://user:pw@localhost/db

# O  맞음
DATABASE_URL=postgresql+asyncpg://user:pw@localhost/db
```

---

## 프로덕션 실행 (ECS)

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

`workers` 수는 `CPU 코어 수 × 2` 를 기준으로 조정합니다.  
FastAPI는 async 기반이라 코어당 1~2개로도 충분한 경우가 많습니다.

---

## API 엔드포인트 요약

| Method | URL                                    | 서버     | 설명                        | 인증 |
| ------ | -------------------------------------- | -------- | --------------------------- | ---- |
| `GET`  | `/health`                              | ECS      | 서버 헬스체크               | 불필요 |
| `POST` | `/api/auth/token`                      | ECS      | 로그인 (JWT 발급)           | 불필요 |
| `POST` | `/api/users`                           | ECS      | 회원가입                    | 불필요 |
| `GET`  | `/api/users/me`                        | ECS      | 내 정보 조회                | Bearer |
| `POST` | `/api/items/lost`                      | ECS      | 분실물 등록                 | Bearer |
| `POST` | `/api/items/found`                     | ECS      | 습득물 등록                 | Bearer |
| `POST` | `/presigned-url`                       | Lambda   | S3 업로드용 서명 URL 발급   | 불필요 |
| `POST` | `/api/items/{itemId}/process-tags`     | ECS      | 이미지 업로드 후 AI 태깅 요청 | Bearer |
| `GET`  | `/api/items/{itemId}/tags`             | ECS      | AI 태깅 결과 조회           | Bearer |
| `GET`  | `/api/items/lost/{id}/similarity`      | ECS      | 유사도 매칭 결과 조회       | Bearer |

---

## 이미지 업로드 & 태깅 플로우

이미지는 클라이언트가 S3에 직접 업로드합니다 (서버를 경유하지 않음). 순서는 아래와 같습니다.

```
[Step 1] POST /presigned-url  (Lambda)
         → S3 서명 URL + s3Key 수령

[Step 2] PUT {presignedUrl}  (S3 직접)
         → 이미지 바이너리 업로드

[Step 3] POST /api/items/{itemId}/process-tags  (ECS)
         body: { "s3Key": "items/1/uuid_jacket.jpg" }
         → 백그라운드에서 AI 태깅 파이프라인 실행 (202 즉시 응답)

[Step 4] GET /api/items/{itemId}/tags  (ECS)
         → 태깅 완료 후 결과 조회
```

---

## 상세 API 명세

### POST `/presigned-url` — S3 업로드용 서명 URL 발급

> 실행 서버: **AWS Lambda**  
> 인증: 불필요

**Request Body** `application/json`

```json
{
  "itemId": 1,
  "filename": "jacket.jpg",
  "contentType": "image/jpeg"
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `itemId` | integer | ✅ | 아이템 ID |
| `filename` | string | ✅ | 업로드할 파일명 |
| `contentType` | string | | MIME 타입 (기본값: `image/jpeg`) |

**Response** `200 OK`

```json
{
  "presignedUrl": "https://s3.amazonaws.com/chatda/items/1/uuid_jacket.jpg?X-Amz-...",
  "s3Key": "items/1/550e8400-e29b-41d4-a716-446655440000_jacket.jpg",
  "expiresIn": 300
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `presignedUrl` | string | PUT 요청에 사용할 서명된 S3 URL (5분간 유효) |
| `s3Key` | string | S3 객체 키 — Step 3에서 그대로 전달 |
| `expiresIn` | integer | URL 유효 시간 (초) |

**Error Response** `400 Bad Request`

```json
{ "message": "잘못된 요청: 'itemId'" }
```

---

### PUT `{presignedUrl}` — S3 직접 업로드

> 실행 서버: **AWS S3** (직접 통신)

**Request Headers**

| 헤더 | 값 | 설명 |
| --- | --- | --- |
| `Content-Type` | `image/jpeg` 등 | presigned-url 발급 시 지정한 contentType과 일치해야 함 |

**Request Body** `application/octet-stream`

이미지 바이너리

**Response** `200 OK` (본문 없음)

---

### POST `/api/items/{itemId}/process-tags` — AI 태깅 요청

> 실행 서버: **ECS (FastAPI)**  
> 인증: `Authorization: Bearer {token}`

S3 업로드 완료 후 호출합니다. 태깅은 백그라운드에서 실행되며 즉시 202를 반환합니다.

**Path Parameter**

| 파라미터 | 타입 | 설명 |
| --- | --- | --- |
| `itemId` | integer | 아이템 ID |

**Request Body** `application/json`

```json
{
  "s3Key": "items/1/550e8400-e29b-41d4-a716-446655440000_jacket.jpg"
}
```

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `s3Key` | string | ✅ | Step 1에서 수령한 s3Key |

**Response** `202 Accepted`

```json
{
  "success": true,
  "message": "태깅 처리가 시작되었습니다."
}
```

> 태깅 파이프라인: Rekognition → CLIP(이미지 벡터) → Gemini(category + features) → DB 저장  
> 실패해도 아이템 등록에 영향 없음 (백그라운드 처리)

---

### GET `/api/items/{itemId}/tags` — AI 태깅 결과 조회

> 실행 서버: **ECS (FastAPI)**  
> 인증: `Authorization: Bearer {token}`

**Path Parameter**

| 파라미터 | 타입 | 설명 |
| --- | --- | --- |
| `itemId` | integer | 아이템 ID |

**Response** `200 OK`

```json
{
  "itemId": 1,
  "category": "가방",
  "features": ["Backpack", "Blue", "Zipper"],
  "hasVector": true,
  "imageUrl": "https://chatda.s3.ap-northeast-2.amazonaws.com/items/1/uuid_jacket.jpg"
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `itemId` | integer | 아이템 ID |
| `category` | string \| null | AI가 분류한 카테고리 |
| `features` | string[] | 색상·형태·특이사항 등 특징 키워드 목록 |
| `hasVector` | boolean | CLIP 벡터 임베딩 완료 여부 |
| `imageUrl` | string \| null | S3 이미지 URL |

**Error Response** `404 Not Found`

```json
{
  "success": false,
  "code": 404,
  "message": "아이템을 찾을 수 없습니다.",
  "data": null
}
```
