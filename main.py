import hashlib
import random
from datetime import date
from typing import List

from dateutil.relativedelta import relativedelta
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Real Estate Insights API",
    description="부동산 실거래가 및 단지별 시세 분석 백엔드 API",
    version="1.0.0"
)

# 1. 프론트엔드(index.html 등)와 통신을 위한 CORS 미들웨어 활성화
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 실제 배포 환경에 맞춰 도메인 제한 가능
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Response Schemas ---
class MonthlyHistoryItem(BaseModel):
    month: str
    avg_price: int
    volume: int


class RecentTransactionItem(BaseModel):
    date: str
    price: int
    floor: str


class ComplexHistoryResponse(BaseModel):
    dong: str
    name: str
    history: List[MonthlyHistoryItem]
    recent_transactions: List[RecentTransactionItem]


# --- Mock Data Generator ---
def generate_mock_complex_data(dong: str, name: str):
    """
    공공데이터 실거래가 API 연동 전 프론트엔드 차트 및 대시보드 테스트용 Mock 데이터 생성기.
    동일한 단지(dong, name)에 대해 일관된 시세 패턴을 제공하도록 해시 시드를 적용합니다.
    """
    seed_str = f"{dong.strip()}_{name.strip()}"
    seed_val = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed_val)

    today = date.today()

    # 80000 ~ 150000 사이 우상향 트렌드 설정
    base_price = rng.randint(82000, 92000)       # 약 3년 전 초기 가격
    target_price = rng.randint(132000, 148000)   # 현재 시점 목표 가격
    price_slope = (target_price - base_price) / 35.0

    # 1. 과거 36개월(3년) 치 월별 시세 및 거래량 데이터
    history: List[MonthlyHistoryItem] = []
    for i in range(36):
        month_offset = 35 - i  # 35개월 전부터 이번 달까지
        dt = today - relativedelta(months=month_offset)
        month_str = dt.strftime("%Y.%m")

        # 완만한 우상향에 자연스러운 월별 등락(±2500만원) 추가
        fluctuation = rng.randint(-2500, 2500)
        simulated_price = int(base_price + (price_slope * i) + fluctuation)
        # 80,000 ~ 150,000 만원 범위 내 클램핑 및 백만원 단위 반올림
        avg_price = max(80000, min(150000, (simulated_price // 100) * 100))

        # 0 ~ 15건 사이 월별 거래량
        volume = rng.randint(0, 15)

        history.append(
            MonthlyHistoryItem(
                month=month_str,
                avg_price=avg_price,
                volume=volume
            )
        )

    # 2. 최근 실거래 내역 3건 (최신순)
    latest_avg = history[-1].avg_price
    recent_transactions: List[RecentTransactionItem] = []
    
    # 최근 며칠 전 거래인지 오름차순으로 생성 후 날짜 계산
    day_offsets = [rng.randint(2, 8), rng.randint(9, 20), rng.randint(21, 45)]
    for day_ago in day_offsets:
        tx_date = (today - relativedelta(days=day_ago)).strftime("%Y.%m.%d")
        tx_price = max(80000, min(150000, latest_avg + rng.randint(-3500, 4000)))
        tx_price = (tx_price // 100) * 100
        tx_floor = f"{rng.randint(2, 28)}층"

        recent_transactions.append(
            RecentTransactionItem(
                date=tx_date,
                price=tx_price,
                floor=tx_floor
            )
        )

    return history, recent_transactions


# --- Endpoints ---
@app.get("/")
def read_root():
    return {
        "message": "부동산 실거래가 인사이트 FastAPI 서버가 정상 동작 중입니다.",
        "docs_url": "/docs",
        "example_endpoint": "/api/complex-history?dong=반포동&name=아크로리버파크"
    }


@app.get(
    "/api/complex-history",
    response_model=ComplexHistoryResponse,
    summary="단지별 36개월 시세 추이 및 최근 실거래 내역 조회",
    description="법정동과 단지명을 받아 과거 36개월 월별 평균가(우상향 트렌드), 거래량 및 최근 실거래 3건을 반환합니다."
)
def get_complex_history(
    dong: str = Query(..., description="법정동 이름 (예: 반포동)"),
    name: str = Query(..., description="아파트 단지명 (예: 아크로리버파크)")
):
    history, recent_transactions = generate_mock_complex_data(dong, name)
    return ComplexHistoryResponse(
        dong=dong,
        name=name,
        history=history,
        recent_transactions=recent_transactions
    )
