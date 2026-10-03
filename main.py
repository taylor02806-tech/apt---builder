import hashlib
import random
from datetime import date
from typing import List, Optional, Any, Dict

from dateutil.relativedelta import relativedelta
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
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
    area: Optional[str] = "84.9㎡"


class ComplexHistoryResponse(BaseModel):
    dong: str
    name: str
    build_year: Optional[int] = None
    history: List[MonthlyHistoryItem]
    recent_transactions: List[RecentTransactionItem]
    pyeongs: Optional[List[Any]] = None
    matched_dong_pyeong: Optional[Dict[str, Any]] = None
    is_real_data: Optional[bool] = False


# 전국 주요 시/도 선택 시 종합 분석을 위한 주요 자치구 매핑
SIDO_MAJOR_DISTRICTS = {
    "11": ["11680", "11650", "11710", "11440", "11170", "11350", "11380", "11500"], # 서울: 강남, 서초, 송파, 마포, 용산, 노원, 은평, 강서
    "41": ["41135", "41117", "41465", "41450", "41590", "41281", "41210"], # 경기: 성남분당, 수원영통, 용인수지, 하남, 화성, 고양덕양, 광명
    "28": ["28185", "28200", "28260", "28237"], # 인천: 연수, 남동, 서구, 부평
    "26": ["26350", "26500", "26260", "26290", "26230"], # 부산: 해운대, 수영, 동래, 남구, 부산진
    "27": ["27260", "27290", "27110", "27230"], # 대구: 수성, 달서, 중구, 북구
    "29": ["29155", "29200", "29140", "29170"], # 광주: 남구, 광산, 서구, 북구
    "30": ["30200", "30170", "30140"], # 대전: 유성, 서구, 중구
    "31": ["31140", "31110", "31200"], # 울산: 남구, 중구, 북구
    "36": ["36110"], # 세종
}


# --- Endpoints ---
@app.get("/")
def read_root():
    return {
        "message": "부동산 실거래가 인사이트 FastAPI 서버가 정상 동작 중입니다.",
        "docs_url": "/docs",
        "web_app": "/app",
        "example_endpoint": "/api/complex-history?dong=반포동&name=아크로리버파크"
    }


@app.get("/app", response_class=HTMLResponse, summary="부동산 실거래 인사이트 웹 애플리케이션")
def view_app():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.get(
    "/api/building-info",
    summary="공공데이터포털 실거래가 기반 건물 상세 및 평형 정보 중계",
    description="국토교통부 실거래가 API를 조회하여 단지/건물의 전용면적별 평형 목록과 실거래 내역을 반환합니다."
)
def get_building_info(
    lawd_cd: str = Query(default="11650", description="법정동 시군구코드 (예: 11650)"),
    dong: str = Query(default="", description="법정동 이름 (예: 반포동)"),
    jibun: str = Query(default="", description="지번 (예: 20-43)"),
    name: str = Query(default="", description="단지명 (예: 반포자이)"),
    prop_type: str = Query(default="apt", description="부동산 종류 (apt, officetel, rowhouse, singlehouse)"),
    trade_type: str = Query(default="sale", description="거래 유형 (sale, jeonse, rent)"),
    start_month: Optional[str] = Query(default=None),
    end_month: Optional[str] = Query(default=None),
    building_dong: Optional[str] = Query(default=None, description="선택한 건물 동 (예: 924동, 101동)")
):
    from building_service import get_building_info_from_gov
    return get_building_info_from_gov(
        lawd_cd=lawd_cd,
        dong=dong,
        jibun=jibun,
        name=name,
        prop_type=prop_type,
        trade_type=trade_type,
        start_month=start_month,
        end_month=end_month,
        building_dong=building_dong
    )


@app.get(
    "/api/complex-history",
    response_model=ComplexHistoryResponse,
    summary="단지별 시세 추이 및 최근 실거래 내역 조회",
    description="법정동과 단지명을 받아 국토교통부 실거래 데이터를 우선 조회하고, 없을 경우 시뮬레이션 데이터를 반환합니다."
)
def get_complex_history(
    dong: str = Query(..., description="법정동 이름 (예: 반포동)"),
    name: str = Query(..., description="아파트 단지명 (예: 아크로리버파크)"),
    jibun: Optional[str] = Query(default="", description="지번"),
    lawd_cd: Optional[str] = Query(default="11650", description="법정동코드"),
    prop_type: Optional[str] = Query(default="apt", description="부동산종류"),
    trade_type: Optional[str] = Query(default="sale", description="거래유형"),
    start_month: Optional[str] = Query(default=None),
    end_month: Optional[str] = Query(default=None),
    building_dong: Optional[str] = Query(default=None, description="선택한 건물 동 (예: 924동, 101동)")
):
    from building_service import get_building_info_from_gov
    real_data = get_building_info_from_gov(
        lawd_cd=lawd_cd or "11650",
        dong=dong,
        jibun=jibun or "",
        name=name,
        prop_type=prop_type or "apt",
        trade_type=trade_type or "sale",
        start_month=start_month,
        end_month=end_month,
        building_dong=building_dong
    )
    if real_data.get("has_real_deals"):
        return ComplexHistoryResponse(
            dong=real_data["dong"],
            name=real_data["name"],
            build_year=real_data["build_year"],
            history=[
                MonthlyHistoryItem(
                    month=h["month"],
                    avg_price=h["avg_price"],
                    volume=h["volume"]
                )
                for h in real_data["history"]
            ],
            recent_transactions=[
                RecentTransactionItem(
                    date=t["date"],
                    price=t["price"],
                    floor=t["floor"],
                    area=t["area"]
                )
                for t in real_data["recent_transactions"]
            ],
            pyeongs=real_data.get("pyeongs"),
            matched_dong_pyeong=real_data.get("matched_dong_pyeong"),
            is_real_data=True
        )

    # 실거래 내역이 없는 경우: 절대로 가짜 랜덤/목업 데이터를 생성하지 않고, 투명하게 빈 내역을 반환
    return ComplexHistoryResponse(
        dong=dong,
        name=name,
        build_year=None,
        history=[],
        recent_transactions=[],
        pyeongs=[],
        matched_dong_pyeong=None,
        is_real_data=False
    )


@app.get(
    "/api/rankings",
    summary="부동산 실거래가 랭킹 및 단지 목록 조회",
    description="국토교통부 실거래가 공공데이터를 기반으로 최고가, 급상승, 급하락 및 단지 목록을 제공합니다."
)
def get_rankings(
    lawd_cd: str = Query(..., description="시군구코드 5자리 또는 시/도 2자리"),
    prop_type: str = Query(default="apt", description="부동산 종류 (apt, officetel, rowhouse, singlehouse, land)"),
    trade_type: str = Query(default="sale", description="거래 유형 (sale, jeonse, rent)"),
    scope: str = Query(default="all", description="조회 범위 (all, dong)"),
    dong_name: Optional[str] = Query(default="", description="읍면동 이름 (scope='dong'일 때)"),
    start_month: Optional[str] = Query(default=None),
    end_month: Optional[str] = Query(default=None)
):
    from concurrent.futures import ThreadPoolExecutor
    from building_service import fetch_single_month, generate_month_list, is_dong_match

    if not lawd_cd:
        return {"error": "필수 파라미터(lawd_cd)가 누락되었습니다."}

    api_category = 'rent' if trade_type in ['jeonse', 'rent'] else 'sale'
    months_to_fetch = generate_month_list(start_month, end_month, default_count=6)

    # 과도한 트래픽 방지 (최대 36개월)
    if len(months_to_fetch) > 36:
        months_to_fetch = months_to_fetch[:36]

    districts = [lawd_cd]
    if len(lawd_cd) == 2:
        districts = SIDO_MAJOR_DISTRICTS.get(lawd_cd, [])
        if not districts:
            return {"soaring": [], "plunging": [], "items": []}

    fetch_tasks = []
    for d_cd in districts:
        for deal_ymd in months_to_fetch:
            fetch_tasks.append((d_cd, deal_ymd))

    all_deals = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = [
            executor.submit(fetch_single_month, d_cd, prop_type, api_category, deal_ymd)
            for d_cd, deal_ymd in fetch_tasks
        ]
        for f in futures:
            try:
                deals = f.result()
                all_deals.extend(deals)
            except Exception:
                pass

    # 거래 유형 및 지역 세부 필터링
    filtered_deals = []
    for d in all_deals:
        if api_category == 'rent':
            if trade_type == 'jeonse' and d.get('monthly_rent', 0) > 0:
                continue
            if trade_type == 'rent' and d.get('monthly_rent', 0) == 0:
                continue
        if scope == 'dong' and dong_name:
            if not is_dong_match(dong_name, d.get('dong', '')):
                continue
        filtered_deals.append(d)

    transactions = {}
    for deal in filtered_deals:
        key = f"{deal['name']}_{deal['area']}"
        if key not in transactions:
            transactions[key] = {
                'name': deal['name'],
                'area': str(deal['area']),
                'dong': deal['dong'],
                'jibun': deal.get('jibun', ''),
                'build_year': deal.get('build_year'),
                'lawd_cd': lawd_cd,
                'prop_type': prop_type,
                'deals': []
            }
        elif not transactions[key].get('build_year') and deal.get('build_year'):
            transactions[key]['build_year'] = deal.get('build_year')
        transactions[key]['deals'].append(deal)

    results = []
    for key, data in transactions.items():
        deals = data['deals']
        # 중복 계약 필터링 (동일 일자 동일 금액 제외)
        unique_deals = {}
        for d in deals:
            d_key = f"{d['date']}_{d['price']}"
            unique_deals[d_key] = d
        deals = list(unique_deals.values())

        date_groups = {}
        for d in deals:
            dt = d['raw_date'] if 'raw_date' in d else d['date'].replace('.', '')
            if dt not in date_groups:
                date_groups[dt] = []
            date_groups[dt].append(d['price'])

        if len(date_groups) >= 2:
            sorted_dates = sorted(date_groups.keys(), reverse=True)
            latest_date = sorted_dates[0]
            latest_prices = date_groups[latest_date]
            latest_price = int(round(sum(latest_prices) / len(latest_prices)))

            prev_date = sorted_dates[1]
            prev_prices = date_groups[prev_date]
            prev_price = int(round(sum(prev_prices) / len(prev_prices)))

            diff = latest_price - prev_price
            results.append({
                'name': data['name'],
                'area': data['area'],
                'dong': data['dong'],
                'jibun': data['jibun'],
                'build_year': data.get('build_year'),
                'lawd_cd': data['lawd_cd'],
                'prop_type': data['prop_type'],
                'latest_date': latest_date,
                'latest_price': latest_price,
                'previous_date': prev_date,
                'previous_price': prev_price,
                'diff': diff
            })
        elif len(date_groups) == 1:
            sorted_dates = list(date_groups.keys())
            latest_date = sorted_dates[0]
            latest_prices = date_groups[latest_date]
            latest_price = int(round(sum(latest_prices) / len(latest_prices)))

            results.append({
                'name': data['name'],
                'area': data['area'],
                'dong': data['dong'],
                'jibun': data['jibun'],
                'build_year': data.get('build_year'),
                'lawd_cd': data['lawd_cd'],
                'prop_type': data['prop_type'],
                'latest_date': latest_date,
                'latest_price': latest_price,
                'previous_date': latest_date,
                'previous_price': latest_price,
                'diff': 0
            })

    soaring = sorted([r for r in results if r['diff'] > 0], key=lambda x: x['diff'], reverse=True)[:50]
    plunging = sorted([r for r in results if r['diff'] < 0], key=lambda x: x['diff'])[:50]
    items = sorted(results, key=lambda x: x['latest_price'], reverse=True)[:1000]

    return {
        'soaring': soaring,
        'plunging': plunging,
        'items': items
    }
