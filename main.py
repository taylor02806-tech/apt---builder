import hashlib
import random
from datetime import date
from typing import List, Optional

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
    build_year: Optional[int] = None
    history: List[MonthlyHistoryItem]
    recent_transactions: List[RecentTransactionItem]


# --- Mock Data Generator ---
def generate_mock_complex_data(dong: str, name: str, total_months: int = 120):
    """
    공공데이터 실거래가 API 연동 전 프론트엔드 차트 및 대시보드 테스트용 Mock 데이터 생성기.
    3년(36개월), 5년(60개월), 전체(최대 120개월/10년) 기간별 조회를 위해 기본 120개월 치를 생성합니다.
    """
    seed_str = f"{dong.strip()}_{name.strip()}"
    seed_val = int(hashlib.md5(seed_str.encode("utf-8")).hexdigest()[:8], 16)
    rng = random.Random(seed_val)

    today = date.today()

    # 10년 전부터 현재 시점까지 자연스러운 장기 상승 흐름 (초기 약 58,000~72,000만원 -> 현재 132,000~148,000만원)
    base_price = rng.randint(58000, 72000)       # 약 10년 전 초기 가격
    target_price = rng.randint(132000, 148000)   # 현재 시점 목표 가격
    price_slope = (target_price - base_price) / float(max(1, total_months - 1))

    # 1. 과거 total_months (기본 120개월/10년) 치 월별 시세 및 거래량 데이터
    history: List[MonthlyHistoryItem] = []
    for i in range(total_months):
        month_offset = (total_months - 1) - i
        dt = today - relativedelta(months=month_offset)
        month_str = dt.strftime("%Y.%m")

        # 완만한 장기 우상향에 자연스러운 월별 등락(±2500만원) 추가
        fluctuation = rng.randint(-2500, 2500)
        simulated_price = int(base_price + (price_slope * i) + fluctuation)
        avg_price = max(40000, min(160000, (simulated_price // 100) * 100))

        # 1 ~ 15건 사이 월별 거래량
        volume = rng.randint(1, 15)

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

    # 3. 단지별 준공년도 매핑
    known_years = {
        '신현대11차': 1983, '신현대9차': 1982, '신현대': 1983, '현대1,2차': 1976, '현대': 1978,
        '은마': 1979, '은마아파트': 1979, '미도': 1983, '선경': 1983, '개포우성': 1983, '개포주공': 1982,
        '잠실주공5단지': 1978, '잠실엘스': 2008, '리센츠': 2008, '트리지움': 2007, '파크리오': 2008,
        '아크로리버파크': 2016, '래미안원베일리': 2023, '반포자이': 2009, '반포래미안퍼스티지': 2009,
        '올림픽선수기자촌': 1988, '아시아선수촌': 1986, '헬리오시티': 2018, '마포래미안푸르지오': 2014,
        '디에이치아너힐즈': 2019, '래미안대치팰리스': 2015, '고덕그라시움': 2019, '목동': 1986
    }
    build_year = None
    for k, v in known_years.items():
        if k in name:
            build_year = v
            break
    if not build_year:
        build_year = rng.randint(1985, 2022)

    return history, recent_transactions, build_year


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
    history, recent_transactions, build_year = generate_mock_complex_data(dong, name)
    return ComplexHistoryResponse(
        dong=dong,
        name=name,
        build_year=build_year,
        history=history,
        recent_transactions=recent_transactions
    )
