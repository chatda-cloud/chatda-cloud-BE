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

| Method | URL                               | 설명                  |
| ------ | --------------------------------- | --------------------- |
| `GET`  | `/health`                         | 서버 헬스체크         |
| `POST` | `/api/auth/token`                 | 로그인 (JWT 발급)     |
| `POST` | `/api/users`                      | 회원가입              |
| `GET`  | `/api/users/me`                   | 내 정보 조회          |
| `POST` | `/api/items/lost`                 | 분실물 등록           |
| `POST` | `/api/items/found`                | 습득물 등록           |
| `GET`  | `/api/items/{itemId}/tags`        | AI 태그 조회          |
| `GET`  | `/api/items/lost/{id}/similarity` | 유사도 매칭 결과 조회 |
