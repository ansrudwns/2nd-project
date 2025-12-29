# CheckMate: AI Real Estate & Labor Contract Analysis System

**CheckMate**는 부동산 임대차 계약서와 등기부등본, 그리고 근로 계약서를 AI로 분석하여 법적 위험 요소를 진단하고, 8개 국어로 번역된 리포트를 제공하는 지능형 계약 분석 플랫폼입니다.

![Project Status](https://img.shields.io/badge/Status-Active-success)
![Python](https://img.shields.io/badge/Backend-FastAPI-blue)
![React](https://img.shields.io/badge/Frontend-Next.js-black)
![Platform](https://img.shields.io/badge/Cloud-Azure-0078D4)

---

## ✨ Key Features (주요 기능)

### 1. 🏠 부동산 임대차 계약 분석 (Lease Contract Analysis)

- **계약서 & 등기부등본 교차 검증**: 주소, 소유자 일치 여부를 자동으로 확인합니다.
- **위험 요소 탐지**: 근저당권, 위반건축물, 깡통전세 위험 등을 정밀 진단합니다.
- **특약사항 독소조항 분석**: 임차인에게 불리한 특약사항을 AI가 찾아냅니다.

### 2. 💼 근로 계약 분석 (Labor Contract Analysis)

- **근로기준법 준수 여부**: 최저임금, 근로시간, 유급휴일 등 법적 필수 항목을 체크합니다.
- **불공정 조항 탐지**: 위약금 예정, 강제 저축 등 불법적인 내용을 식별합니다.

### 3. 🌏 다국어 지원 (Multi-language Support)

- 한국어, 영어(English), 네팔어, 캄보디아어, 인도네시아어, 베트남어, 미얀마어, 태국어 등 **8개국어**로 분석 결과를 제공합니다.
- 외국인 근로자나 유학생도 쉽게 계약 내용을 이해할 수 있습니다.

### 4. 👤 사용자 편의 기능

- **회원가입/로그인**: 이메일 중복 확인 및 보안 로그인.
- **이용약관 동의**: 필수 약관(개인정보, 법적 한계 등)에 대한 명확한 동의 절차.
- **분석 이력 관리**: 과거 분석 내역을 저장하고 언제든 다시 열람할 수 있습니다. (안전한 회원 탈퇴 기능 포함)
- **직관적인 UX**: 로딩 애니메이션 및 진행 상황 시각화로 사용자 경험을 강화했습니다.

---

## 🛠 Tech Stack (기술 스택)

### Frontend

- **Framework**: Next.js 14 (App Router)
- **Styling**: Tailwind CSS
- **Deployment**: Azure Static Web Apps

### Backend

- **Framework**: FastAPI (Python 3.9+)
- **Database**: PostgreSQL (Production) / SQLite (Dev)
- **AI/ML**: Azure OpenAI (GPT-4), Azure Document Intelligence (OCR), Azure AI Search (RAG), Azure Language (PII Masking)
- **Deployment**: Azure Container Apps

---

## 🏗 System Architecture & Workflow (시스템 구조 및 분석 프로세스)

### 1. Data Storage Strategy (데이터 저장 전략)

이 시스템은 데이터의 특성에 따라 두 가지 저장소를 효율적으로 분리하여 사용합니다.

| 저장소 (Storage)          | 저장 데이터 (Data Type)                                                                                                            | 용도 (Usage)                                        |
| :------------------------ | :--------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------- |
| **PostgreSQL (Database)** | • 사용자 정보 (회원가입, 로그인)<br>• 분석 결과 데이터 (JSON)<br>• 감사 로그 (Audit Logs)<br>• 파일 메타데이터 (경로, 업로드 시간) | 구조화된 데이터의 빠른 검색 및 트랜잭션 처리        |
| **Azure Blob Storage**    | • 원본 계약서 파일 (PDF, Image)<br>• 1차 가공된 텍스트 파일<br>• PII(개인정보) 마스킹된 결과 이미지                                | 대용량 비정형 데이터의 안전한 보관 및 URL 기반 접근 |

### 2. Analysis Pipeline (분석 프로세스)

사용자가 계약서를 업로드하면 다음과 같은 순서로 정밀 분석이 진행됩니다.

1.  **Ingestion (수집)**:
    - 프론트엔드에서 업로드된 파일은 즉시 **Azure Blob Storage**에 안전하게 암호화되어 저장됩니다.
2.  **Preprocessing (전처리)**:
    - **Azure Document Intelligence (OCR)**가 문서의 텍스트와 좌표 정보를 추출합니다.
    - **Azure Language Service**가 주민등록번호, 전화번호 등 민감 개인정보(PII)를 식별하고 마스킹(Masking) 처리합니다.
3.  **Cross-Validation (교차 검증)** - _임대차 계약의 경우_:
    - 업로드된 '임대차 계약서'와 '등기부등본'의 소유자 정보, 주소지 정보를 자동 비교하여 일치 여부를 판별합니다.
4.  **AI & Rule-Based Analysis (복합 분석)**:
    - **Rule Engine**: 법적으로 명확한 위반 사항(최저임금 미달, 근로시간 초과 등)을 Python 알고리즘으로 1차 필터링합니다.
    - **Azure OpenAI (GPT-4)**: 모호한 특약사항이나 복잡한 법률 조항을 해석하고, "독소 조항"이나 "불공정 계약" 위험을 탐지합니다.
    - **RAG (검색 증강)**: 분석 근거가 필요한 경우 **Azure AI Search**에 구축된 법률/판례 DB를 참조하여 정확도를 높입니다.
5.  **Result Generation (결과 도출)**:
    - 발견된 모든 위험 요소(Risk)를 종합하여 안전도 점수를 계산합니다.
    - 사용자가 이해하기 쉬운 요약 리포트를 생성하고 **PostgreSQL**에 최종 저장합니다.

---

## 📂 Project Structure

```bash
2nd_project2/
├── backend/            # FastAPI Server
│   ├── app/            # Application Logic
│   │   ├── api/        # Endpoints
│   │   ├── services/   # Business Logic (Analysis, OCR, PII)
│   │   └── models/     # Database Schemas
│   ├── data/           # RAG Source PDFs (Laws, Cases)
│   ├── scripts/        # Data Ingestion Scripts (RAG Setup)
│   ├── Dockerfile      # Deployment Config
│   └── requirements.txt
├── frontend/           # Next.js Client
│   ├── app/            # Pages & Routing
│   ├── components/     # UI Components
│   └── public/         # Static Assets
└── docker-compose.yml  # Local Development Config
```

---

## ✅ Prerequisites (사전 요구사항)

이 프로젝트를 실행하기 위해 다음 도구들이 필요합니다.

- **Python 3.9+** (백엔드 실행용)
- **Node.js 18+** (프론트엔드 실행용)
- **Git** (코드 버전 관리)
- **Azure 계정** (다음 리소스 필요):
  - Azure OpenAI Service
  - Azure Document Intelligence
  - Azure AI Search (Vector Store)
  - Azure Blob Storage
  - Azure Language Service (PII Masking)

---

## 🚀 Getting Started (설치 및 실행)

### 1. 환경 변수 설정 (.env)

백엔드 폴더의 예시 파일을 복사하여 `.env`를 생성하고 Azure API 키들을 입력합니다.

```bash
cp backend/.env.example backend/.env
# .env 파일을 열어 키 값을 채워주세요.
```

### 2. RAG Knowledge Base 구축 (초기 설정)

법률 및 판례 데이터를 Azure AI Search에 주입해야 AI가 이를 참고하여 분석할 수 있습니다.

**[옵션 A] 임대차 계약 (Lease) 데이터 구축**

```bash
# 1. 인덱스(그릇) 생성
python backend/scripts/init_lease_index.py

# 2. 데이터 주입 (PDF -> Vector DB)
# backend/data/laws, cases, forms 폴더의 파일들이 업로드됩니다.
python backend/scripts/ingest_lease.py
```

**[옵션 B] 근로 계약 (Labor) 데이터 구축**

```bash
# 1. 인덱스 생성
python backend/scripts/init_labor_index.py

# 2. 데이터 주입
# backend/data/labor_laws, labor_cases, labor_forms 폴더의 파일들이 업로드됩니다.
python backend/scripts/ingest_labor.py
```

### 3. 백엔드 실행

```bash
cd backend
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Mac/Linux:
# source venv/bin/activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API 문서는 `http://localhost:8000/docs`에서 확인할 수 있습니다.

### 4. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
```

브라우저에서 `http://localhost:3000`으로 접속하여 테스트합니다.

---

## ☁️ Deployment (배포 가이드)

### 1. GitHub Push

프로젝트 전체(`frontend`, `backend` 포함)를 GitHub 저장소에 Push 합니다.
**주의**: `.env` 파일은 보안상 절대 올리지 않아야 합니다. (이미 `.gitignore`에 처리되어 있습니다)

### 2. Azure Container Apps (백엔드)

- GitHub의 `backend` 폴더를 기준으로 배포합니다.
- `Dockerfile`이 이미 준비되어 있습니다.
- Azure Portal에서 App Settings(환경 변수)에 `.env` 내용을 직접 등록해야 합니다.

### 3. Azure Static Web Apps (프론트엔드)

- GitHub의 `frontend` 폴더를 기준으로 배포합니다.
- Build Presets으로 **Next.js**를 선택합니다.
- 환경 변수 `NEXT_PUBLIC_API_URL`에 위에서 배포한 백엔드 주소를 입력합니다.
