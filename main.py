import hashlib
import random
from datetime import date
from typing import List, Optional, Any

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
    area: Optional[str] = "84.9㎡"


class ComplexHistoryResponse(BaseModel):
    dong: str
    name: str
    build_year: Optional[int] = None
    history: List[MonthlyHistoryItem]
    recent_transactions: List[RecentTransactionItem]
    pyeongs: Optional[List[Any]] = None
    is_real_data: Optional[bool] = False


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
        tx_price = max(40000, min(250000, latest_avg + rng.randint(-3500, 4000)))
        tx_price = (tx_price // 100) * 100
        tx_floor = f"{rng.randint(2, 28)}층"
        recent_transactions.append(
            RecentTransactionItem(
                date=tx_date,
                price=tx_price,
                floor=tx_floor,
                area="84.9㎡"
            )
        )

    # 3. 단지별 준공년도 매핑
    known_years = {
        # 서초구
        '아크로리버파크': 2016, '래미안원베일리': 2023, '반포자이': 2009, '반포래미안퍼스티지': 2009,
        '반포센트럴자이': 2020, '반포써밋': 2018, '래미안신반포원펜타스': 2024, '디에이치반포라클라스': 2021,
        '디에이치라클라스': 2021, '반포미도1차': 1987, '반포미도2차': 1989, '반포미도': 1987,
        '신반포1차': 1977, '신반포2차': 1978, '신반포3차': 1978, '신반포4차': 1979, '신반포7차': 1980,
        '신반포10차': 1981, '신반포12차': 1982, '신반포14차': 1983, '신반포15차': 1982, '신반포16차': 1983,
        '신반포18차': 1983, '신반포19차': 1983, '신반포20차': 1983, '신반포21차': 1984, '신반포22차': 1983,
        '신반포자이': 2018, '아크로리버뷰신반포': 2018, '아크로리버뷰': 2018, '래미안신반포리오센트': 2019,
        '잠원동아': 2002, '잠원한신': 1992, '잠원신동아': 1980, '메이플자이': 2025, '반포주공1단지': 1973,
        '방배삼호1차': 1976, '방배삼호2차': 1976, '방배삼호3차': 1976, '방배삼호': 1976,
        '방배신삼호': 1983, '방배래미안아트힐': 2004, '방배그랑자이': 2021, '방배롯데캐슬아르떼': 2013,
        '방배서리풀e편한세상': 2010, '방배아트자이': 2018, '방배우성': 1991, '방배임광': 1985,
        '방배대우효령': 1992, '서초그랑자이': 2021, '래미안리더스원': 2020, '래미안서초에스티지S': 2018,
        '래미안서초에스티지': 2016, '서초삼풍': 1988, '서초무지개': 1978, '서초우성1차': 1979,
        '서초우성2차': 1978, '서초우성3차': 1978, '서초신동아': 1978, '아크로비스타': 2004,
        '롯데캐슬클래식': 2006, '서초포레스타2단지': 2014, '서초포레스타3단지': 2014, '서초포레스타5단지': 2014,
        '서초포레스타': 2014, '삼호가든3차': 1982, '삼호가든4차': 1983, '삼호가든': 1982,
        '반포리체': 2010, '반포힐스테이트': 2011,

        # 강남구
        '압구정현대': 1976, '신현대11차': 1983, '신현대9차': 1982, '신현대12차': 1982, '신현대': 1983,
        '현대1,2차': 1976, '현대3차': 1977, '현대4차': 1977, '현대5차': 1977, '현대6,7차': 1978,
        '현대8차': 1980, '현대10차': 1982, '현대13차': 1982, '현대14차': 1987,
        '은마': 1979, '은마아파트': 1979, '한보미도맨션': 1983, '대치미도': 1983,
        '개포선경': 1983, '대치선경': 1983, '개포우성1차': 1983, '개포우성2차': 1984,
        '개포주공1단지': 1982, '개포주공5단지': 1983, '개포주공6단지': 1983, '개포주공7단지': 1983,
        '개포래미안블레스티지': 2019, '디에이치아너힐즈': 2019, '개포래미안포레스트': 2020,
        '디에이치퍼스티어아이파크': 2024, '래미안블레스티지': 2019, '래미안대치팰리스': 2015,
        '대치아이파크': 2007, '도곡렉슬': 2006, '타워팰리스1차': 2002, '타워팰리스2차': 2003,
        '타워팰리스3차': 2004, '대치동부센트레빌': 2005, '대치삼성': 2000, '역삼래미안': 2005,
        '역삼푸르지오': 2006, '개나리래미안': 2006, '삼성동아이파크': 2004, '래미안라클래시': 2021,
        '청담자이': 2011, '청담삼익': 1980, '한양1차': 1977, '한양2차': 1978,
        '한양3차': 1978, '한양4차': 1978, '한양5차': 1979, '한양6차': 1980,

        # 송파구
        '잠실주공5단지': 1978, '잠실엘스': 2008, '리센츠': 2008, '트리지움': 2007,
        '레이크팰리스': 2006, '파크리오': 2008, '헬리오시티': 2018, '올림픽선수기자촌': 1988,
        '올림픽훼밀리타운': 1988, '아시아선수촌': 1986, '잠실진주': 1980, '잠실미성': 1980,
        '잠실크로바': 1980, '장미1차': 1979, '장미2차': 1979, '송파시그니처롯데캐슬': 2022,
        '파크하비오': 2016,

        # 용산구/성동구/마포구
        '한남더힐': 2011, '나인원한남': 2019, '한강맨션': 1971, '용산센트럴파크': 2020,
        '래미안첼리투스': 2015, '이촌한강자이': 2003, '이촌현대': 1974, '이촌신동아': 1983,
        '트리마제': 2017, '아크로서울포레스트': 2020, '갤러리아포레': 2011, '옥수리버젠': 2012,
        '옥수파크힐스': 2016, '센트라스': 2016, '텐즈힐1단지': 2015, '텐즈힐2단지': 2014,
        '행당대림': 2000, '마포래미안푸르지오': 2014, '마포프레스티지자이': 2021, '마포더클래시': 2022,
        '신촌그랑자이': 2020, '래미안마포리버웰': 2014, '마포자이': 2004, '공덕자이': 2015,
        '공덕래미안': 2004, '경희궁자이': 2017, 'DMC래미안e편한세상': 2012,

        # 양천/강동/노원/기타
        '목동신시가지1단지': 1985, '목동신시가지2단지': 1986, '목동신시가지3단지': 1986,
        '목동신시가지4단지': 1986, '목동신시가지5단지': 1986, '목동신시가지6단지': 1986,
        '목동신시가지7단지': 1986, '목동신시가지8단지': 1987, '목동신시가지9단지': 1987,
        '목동신시가지10단지': 1987, '목동신시가지11단지': 1988, '목동신시가지12단지': 1988,
        '목동신시가지13단지': 1987, '목동신시가지14단지': 1987, '목동센트럴푸르지오': 2015,
        '목동힐스테이트': 2016, '고덕그라시움': 2019, '고덕아르테온': 2020,
        '올림픽파크포레온': 2024, '둔촌주공': 1980, '래미안명일역솔베뉴': 2019,
        '상계주공1단지': 1988, '상계주공2단지': 1987, '상계주공3단지': 1987,
        '상계주공5단지': 1987, '상계주공6단지': 1988, '상계주공7단지': 1988,
        '포레나노원': 2020, '중계무지개': 1991, '중계그린': 1990,
        '여의도시범': 1971, '여의도삼익': 1974, '여의도한양': 1975,
        '판교푸르지오그랑블': 2011, '과천위버필드': 2021
    }
    build_year = None
    # 긴 이름(구체적인 단지명)부터 우선 매칭하여 '현대', '목동' 등 단축명으로 인한 오매칭 방지
    dong_clean = dong.rstrip("동") if dong else ""
    combined_name = f"{dong_clean}{name}"
    for k in sorted(known_years.keys(), key=len, reverse=True):
        if k in name or (dong_clean and k in combined_name):
            build_year = known_years[k]
            break

    if not build_year:
        import re
        year_match = re.search(r'\b(19\d\d|20\d\d)\b', name)
        if year_match:
            cand = int(year_match.group(1))
            if 1970 <= cand <= today.year:
                build_year = cand

    if not build_year:
        if any(w in name for w in ['주공', '시영', '삼호', '한양', '맨션', '시민', '공영']):
            build_year = 1975 + (seed_val % 13) # 1975 ~ 1987 (재건축)
        elif any(w in name for w in ['자이', '푸르지오', '래미안', '힐스테이트', '아이파크', '더샵', '롯데캐슬', 'e편한세상', '디에이치', '아크로', '르엘', '포레나', '센트럴', '파크', '클래시', '베일리', '써밋']):
            build_year = 2009 + (seed_val % 15) # 2009 ~ 2023 (신축/준신축)
        elif any(w in name for w in ['현대', '우성', '동아', '대우', '대림', '극동', '삼풍', '미도', '선경', '벽산', '건영', '청구', '신동아', '한신']):
            build_year = 1988 + (seed_val % 13) # 1988 ~ 2000 (기축)
        else:
            build_year = 1996 + (seed_val % 24)

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
    end_month: Optional[str] = Query(default=None)
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
        end_month=end_month
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
    end_month: Optional[str] = Query(default=None)
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
        end_month=end_month
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
            is_real_data=True
        )

    history, recent_transactions, build_year = generate_mock_complex_data(dong, name)
    return ComplexHistoryResponse(
        dong=dong,
        name=name,
        build_year=build_year,
        history=history,
        recent_transactions=recent_transactions,
        is_real_data=False
    )
