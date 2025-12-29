# Real Estate Contract Analysis System

이 프로젝트는 부동산 임대차 계약서와 등기부등본을 분석하여 권리 위험을 진단하는 시스템입니다.

## 1. 사전 요구사항 (Prerequisites)

- Python 3.9+
- Node.js 18+
- Azure 계정 및 API 키 (Document Intelligence, OpenAI, AI Search, Blob Storage)

## 2. 환경 변수 설정

`backend/.env.example` 파일을 복사하여 `backend/.env`를 생성하고 키를 입력하세요.

```bash
cp backend/.env.example backend/.env
# .env 파일을 열어 키 값을 채워주세요. (키가 없으면 Mock 모드로 동작하거나 에러가 발생할 수 있습니다)
```

## 3. 백엔드 실행 (Backend)

```bash
# Backend 폴더로 이동
cd backend

# 가상환경 생성 (권장)
python -m venv venv

# 가상환경 활성화
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

# 라이브러리 설치
pip install -r requirements.txt

# 서버 실행
uvicorn main:app --reload --port 8000
```

API 문서는 `http://localhost:8000/docs`에서 확인할 수 있습니다.

## 4. 데이터베이스 설정 (Database)

기본적으로 별도의 설정이 없으면 **SQLite** (`test.db`)가 자동으로 사용되어 즉시 테스트할 수 있습니다.

**PostgreSQL 전환 방법**:
`.env` 파일에 `DATABASE_URL`을 설정하면, SQLite 대신 해당 DB를 사용합니다.

```bash
# .env 파일 예시
DATABASE_URL="postgresql://user:password@localhost:5432/real_estate_db"
```

## 5. 프론트엔드 실행 (Frontend)

새로운 터미널을 열고 실행하세요.

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:3000`으로 접속하세요.

## 5. 테스트 방법

1. 웹 화면에서 "임대차 계약서"와 "등기부등본" 파일을 업로드합니다.
2. "분석 시작하기" 버튼을 클릭합니다.
3. 결과를 확인합니다. (현재 Mock 로직이 일부 포함되어 있어 텍스트 추출이 완벽하지 않을 수 있습니다)

## 6. RAG 데이터 구축 (Knowledge Base)

법률 및 판례 데이터를 Azure AI Search에 주입하려면 아래 스크립트를 실행하세요. 도메인별로 분리되어 있습니다.

### 🏠 임대차 계약 (Lease/Rent) RAG

1.  **인덱스 생성 (초기 1회)**

    ```bash
    python backend/scripts/init_lease_index.py
    ```

2.  **데이터 주입 (PDF -> Vector DB)**
    `backend/data/laws`, `cases`, `forms` 폴더에 PDF를 넣고 실행하세요.
    ```bash
    python backend/scripts/ingest_lease.py
    ```

### 💼 근로 계약 (Labor) RAG

1.  **인덱스 생성 (초기 1회)**

    ```bash
    python backend/scripts/init_labor_index.py
    ```

2.  **데이터 주입 (PDF -> Vector DB)**
    `backend/data/labor_laws`, `labor_cases`, `labor_forms` 폴더에 PDF를 넣고 실행하세요.
    ```bash
    python backend/scripts/ingest_labor.py
    ```
