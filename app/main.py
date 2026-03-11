"""
main.py 역할 
1. FastAPI 앱 생성 
2. CORS 설정 
3. threads/chat 라우터 연결 
4. 모든 요청에 대한 공통 로그 기록 
5. uvicorn으로 서버 실행 

FastAPI app
: UI에서 들어오는 HTTP 요청을 받아서, 알맞은 파이썬 함수로 연결하고 응답을 돌려주는 중심 객체 
"""

import time
from fastapi import FastAPI, APIRouter, Request
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes.threads import threads_router
from app.api.routes.chat import chat_router
from app.utils.logger import custom_logger

# FastAPI 앱 객체 생성 
app = FastAPI(
    title="Edu Agent Template",
    description="LangChain 기반 에이전트 교육용 템플릿",
    version="0.1.0",
)

# API prefix용 라우터 생성 
# .env 파일에 설정한 공통 prefix 사용 : /api/v1
api_router = APIRouter(prefix=settings.API_V1_PREFIX)


# CORS 설정 : UI에서 agent 서버 호출 허용
app.add_middleware(
    CORSMiddleware,
    # 어느 주소에서 오는 요청을 허용할지 
    allow_origins=settings.CORS_ORIGINS,
    # 쿠키/인증 정보 허용 여부 
    allow_credentials=True,
    # GET, POST 등 모든 메서드 허용 
    allow_methods=["*"],
    # 모든 헤더 허용
    allow_headers=["*"],
)

# API 라우터 등록 : 실제 기능별 라우터 묶는 부분 
api_router.include_router(threads_router, tags=["threads"]) # 스레드 관련 API
api_router.include_router(chat_router, tags=["chat"])       # 채팅 관련 API 
"""
예시 - API 라우터 등록 
@chat_router.post("/chat") -> 최종 경로 : /api/v1/chat
"""

# FastAPI app에 최종 등록
# - 지금까지 만든 api_router를 FastAPI 앱에 실제 연결 
# - 결과 : 외부 요청이 들어왔을 때 FastAPI가 라우팅 가능 
app.include_router(api_router)


# HTTP 요청 미들웨어 
# - 모든 HTTP 요청의 앞뒤를 감싸는 공통 처리 
# - 요청 시작/종료 로그 + 처리 시간 측정 
@app.middleware("http")
async def log_requests(request: Request, call_next):
    custom_logger.info(f"➡️ 요청 시작: {request.method} {request.url.path}")
    start_time = time.time()

    # 실제 라우터 실행
    # call_next() : URL/HTTP method 매칭 -> 해당 라우터 함수 실행 -> 결과 응답 반환
    # - FastAPI가 /api/v1/chat 요청을 chat.py의 post_chat()으로 라우팅
    # - post_chat() 내부에서 AgentService() 생성해서 실제 처리 로직 실행 
    # - 현재 AgentService 안에서 app.agents.dummy.Agent를 사용 
    response = await call_next(request)

    process_time = time.time() - start_time
    custom_logger.info(
        f"⬅️ 요청 종료: {request.method} {request.url.path} "
        f"(실행 시간: {process_time:.3f}초) "
        f"상태코드: {response.status_code}"
    )

    return response


# 기본 Endpoint
@app.get("/")
async def root():
    return {"message": "Edu Agent API", "version": "0.1.0"}


# 헬스 체크 
@app.get("/health")
async def health():
    return {"status": "healthy"}


# 실행 부분 
# - 이 파일을 직접 실행했을 때 서버를 띄우는 코드 
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",     # app/main/py 안의 app 객체 실행
        host="0.0.0.0",
        port=8000,
        reload=True
    )