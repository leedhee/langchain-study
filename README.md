# 의료 정보 안내 Agent

FastAPI, LangChain, LangGraph 기반의 의료 정보 안내 Agent입니다. 사용자 질문에 따라 증상/질병 정보, 의약품 정보, 병원 정보를 조회하고 SSE 방식으로 응답합니다.

의료 상담이나 진단을 대체하지 않으며, 공공데이터 API와 Elasticsearch 검색 결과를 바탕으로 참고용 정보를 제공합니다.

## 프로젝트 소개

의료 관련 자연어 질문을 이해한 뒤 3개 tool 중 하나를 선택해 정보를 조회하고, 결과를 한국어로 정리해 답변하는 Agent입니다.

## 주요 기능

- 증상/질병 정보 검색
- 약 효능, 복용법, 주의사항 안내
- 지역/진료과목 기반 병원 검색
- `thread_id` 기반 멀티턴 대화

## 기술 스택

- Python
- FastAPI
- LangChain / LangGraph
- OpenAI
- Elasticsearch
- httpx
- uv

## 폴더 구조

```text
agent/
├── app/
│   ├── agents/          # Agent, prompt, tools
│   ├── api/routes/      # chat, threads API
│   ├── core/            # config
│   ├── models/          # request/response model
│   ├── services/        # agent, thread service
│   ├── data/            # 샘플 thread/favorite 데이터
│   └── main.py          # FastAPI 진입점
├── tests/
├── env.sample
└── README.md
```

## 실행 방법

```bash
uv sync
cp env.sample .env
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

실행 후:

- `GET /docs`
- `GET /health`

## 환경변수

- `API_V1_PREFIX`: API prefix
- `CORS_ORIGINS`: 허용 origin
- `OPENAI_API_KEY`: OpenAI API Key
- `OPENAI_MODEL`: 사용할 모델명
- `PUBLIC_DATA_API_KEY`: 공공데이터 API Key
- `ES_URL`, `ES_USER`, `ES_PASSWORD`, `INDEX_NAME`: Elasticsearch 접속 정보
- `CONTENT_FIELD`, `TOP_K`: 증상 검색 옵션

## Agent 동작 방식

사용자 질문을 분석한 뒤 3개 tool 중 하나를 최대 1회 호출하고, 그 결과를 `ChatResponse` 형식으로 정리해 SSE로 반환합니다.

흐름:

- 질문 수신
- tool 선택
- 외부 데이터 조회
- 최종 답변 생성
- 스트리밍 응답 반환

## Tool 설명

- `analyze_symptom`: Elasticsearch 기반 증상/질병 정보 검색
- `analyze_medicine`: 공공데이터 의약품 정보 조회
- `search_hospital`: 공공데이터 병원 정보 조회

## API 명세

- `GET /`: 서비스 정보
- `GET /health`: 헬스 체크
- `POST /api/v1/chat`: 채팅 요청, SSE 응답
- `GET /api/v1/threads`: 최근 대화 목록 조회
- `GET /api/v1/threads/{thread_id}`: 특정 대화 조회
- `GET /api/v1/favorites/questions`: 즐겨찾기 질문 조회

채팅 요청 예시:

```json
{
  "thread_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "message": "구로구 내과 병원 알려줘"
}
```

## 예시 질의응답

- `기침 관련 질병 정보 알려줘`
- `타이레놀 효능 알려줘`
- `구로구 구로동 내과 병원 알려줘`