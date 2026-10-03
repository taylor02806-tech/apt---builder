import os
import re
from datetime import datetime, date
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Any
import xml.etree.ElementTree as ET
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("API_KEY") or os.environ.get("MOLIT_API_KEY")

API_ENDPOINTS = {
    'sale': {
        'apt': 'https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev',
        'officetel': 'https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade',
        'rowhouse': 'https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade',
        'singlehouse': 'https://apis.data.go.kr/1613000/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade',
        'land': 'https://apis.data.go.kr/1613000/RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade'
    },
    'rent': {
        'apt': 'https://apis.data.go.kr/1613000/RTMSDataSvcAptRent/getRTMSDataSvcAptRent',
        'officetel': 'https://apis.data.go.kr/1613000/RTMSDataSvcOffiRent/getRTMSDataSvcOffiRent',
        'rowhouse': 'https://apis.data.go.kr/1613000/RTMSDataSvcRHRent/getRTMSDataSvcRHRent',
        'singlehouse': 'https://apis.data.go.kr/1613000/RTMSDataSvcSHRent/getRTMSDataSvcSHRent'
    }
}

# In-memory cache for monthly deals
# Key: (lawd_cd, prop_type, api_category, ymd) -> List[Dict]
_MONTH_CACHE: Dict[tuple, List[Dict[str, Any]]] = {}

def normalize_name(name: str) -> str:
    """단지명 또는 건물명 정규화 (공백, 동 호수, 아파트 접미사 제거)"""
    if not name:
        return ""
    n = re.sub(r'\s*\d+동.*$', '', name)
    n = re.sub(r'아파트$', '', n)
    n = re.sub(r'[(（].*?[)）]', '', n)
    n = re.sub(r'[^\w가-힣0-9]', '', n)
    return n.strip()

def calculate_pyeong(prop_type: str, area_sqm: float) -> int:
    """
    국토교통부 전용면적(㎡)을 한국 부동산 표준 공급 평형으로 변환.
    - 아파트: 평균 전용률 약 74~76% 반영 (59㎡ -> 24평형, 84㎡ -> 34평형)
    - 오피스텔: 전용률 약 50% 반영
    - 연립/다세대/단독: 전용면적 기준 평형
    """
    if area_sqm <= 0:
        return 34
    if prop_type == 'apt':
        supply_area = area_sqm / 0.75
        return max(1, round(supply_area / 3.3058))
    elif prop_type == 'officetel':
        supply_area = area_sqm / 0.50
        return max(1, round(supply_area / 3.3058))
    else:
        return max(1, round(area_sqm / 3.3058))

def generate_month_list(start: Optional[str] = None, end: Optional[str] = None, default_count: int = 36) -> List[str]:
    """시작월(YYYYMM)부터 종료월(YYYYMM)까지의 리스트 생성 (없으면 최근 default_count 개월)"""
    if start and end and len(start) == 6 and len(end) == 6:
        start_y, start_m = int(start[:4]), int(start[4:])
        end_y, end_m = int(end[:4]), int(end[4:])
        if (start_y > end_y) or (start_y == end_y and start_m > end_m):
            start_y, start_m, end_y, end_m = end_y, end_m, start_y, start_m
        months = []
        curr_y, curr_m = start_y, start_m
        while (curr_y < end_y) or (curr_y == end_y and curr_m <= end_m):
            months.append(f"{curr_y}{curr_m:02d}")
            curr_m += 1
            if curr_m > 12:
                curr_m = 1
                curr_y += 1
        return sorted(months, reverse=True)
    
    today = date.today()
    curr_y, curr_m = today.year, today.month
    months = []
    for _ in range(default_count):
        months.append(f"{curr_y}{curr_m:02d}")
        curr_m -= 1
        if curr_m < 1:
            curr_m = 12
            curr_y -= 1
    return months

def fetch_single_month(lawd_cd: str, prop_type: str, api_category: str, ymd: str) -> List[Dict[str, Any]]:
    """공공데이터포털 API에서 단일 월의 실거래가 데이터를 조회 및 캐싱"""
    cache_key = (lawd_cd, prop_type, api_category, ymd)
    if cache_key in _MONTH_CACHE:
        return _MONTH_CACHE[cache_key]

    endpoint_map = API_ENDPOINTS.get(api_category, {})
    url = endpoint_map.get(prop_type)
    if not url:
        return []

    params = {
        'serviceKey': API_KEY,
        'LAWD_CD': lawd_cd,
        'DEAL_YMD': ymd,
        'numOfRows': '9999'
    }

    deals = []
    try:
        resp = requests.get(url, params=params, timeout=12)
        if resp.status_code == 200 and resp.content:
            root = ET.fromstring(resp.content)
            for it in root.findall('.//item'):
                # 1. 이름 추출
                name = ""
                if prop_type == 'apt':
                    name = (it.findtext('aptNm') or it.findtext('아파트') or "").strip()
                elif prop_type == 'officetel':
                    name = (it.findtext('offiNm') or it.findtext('단지') or "").strip()
                elif prop_type == 'rowhouse':
                    name = (it.findtext('mhouseNm') or it.findtext('연립다세대') or "").strip()
                elif prop_type == 'singlehouse':
                    house_type = (it.findtext('houseType') or it.findtext('주택유형') or "단독").strip()
                    dong_txt = (it.findtext('umdNm') or it.findtext('법정동') or "").strip()
                    jibun_txt = (it.findtext('jibun') or it.findtext('지번') or "").strip()
                    name = f"{dong_txt} {house_type} {jibun_txt}".strip()

                # 2. 전용면적 추출
                area_str = (it.findtext('excluUseAr') or it.findtext('전용면적') or 
                            it.findtext('totalFloorAr') or it.findtext('연면적') or "0").strip()
                try:
                    area_val = round(float(area_str.replace(',', '')), 2)
                except ValueError:
                    area_val = 0.0

                # 3. 법정동 및 지번
                dong = (it.findtext('umdNm') or it.findtext('법정동') or "").strip()
                jibun = (it.findtext('jibun') or it.findtext('지번') or "").strip()

                # 4. 건축년도
                build_year_str = (it.findtext('buildYear') or it.findtext('건축년도') or "").strip()
                build_year = int(build_year_str) if build_year_str.isdigit() else None

                # 5. 거래금액 (매매 vs 전월세)
                price = 0
                deposit = 0
                monthly_rent = 0
                deal_type_desc = "매매"

                if api_category == 'sale':
                    price_str = (it.findtext('dealAmount') or it.findtext('거래금액') or "0").replace(',', '').strip()
                    price = int(price_str) if price_str.isdigit() else 0
                else:
                    dep_str = (it.findtext('deposit') or it.findtext('보증금액') or "0").replace(',', '').strip()
                    rent_str = (it.findtext('monthlyRent') or it.findtext('월세금액') or "0").replace(',', '').strip()
                    deposit = int(dep_str) if dep_str.isdigit() else 0
                    monthly_rent = int(rent_str) if rent_str.isdigit() else 0
                    price = deposit
                    deal_type_desc = "월세" if monthly_rent > 0 else "전세"

                if price <= 0 and deposit <= 0:
                    continue

                # 6. 거래 일자
                y = (it.findtext('dealYear') or it.findtext('년') or ymd[:4]).strip()
                m = str(it.findtext('dealMonth') or it.findtext('월') or ymd[4:]).strip().zfill(2)
                d = str(it.findtext('dealDay') or it.findtext('일') or "1").strip().zfill(2)
                date_str = f"{y}.{m}.{d}"
                raw_date = f"{y}{m}{d}"

                # 7. 층
                floor_str = (it.findtext('floor') or it.findtext('층') or "").strip()
                floor_display = f"{floor_str}층" if floor_str and not floor_str.endswith('층') else (floor_str or "-")

                deals.append({
                    'name': name,
                    'area': area_val,
                    'dong': dong,
                    'jibun': jibun,
                    'price': price,
                    'deposit': deposit,
                    'monthly_rent': monthly_rent,
                    'deal_type': deal_type_desc,
                    'date': date_str,
                    'raw_date': raw_date,
                    'year_month': f"{y}.{m}",
                    'floor': floor_display,
                    'build_year': build_year,
                    'prop_type': prop_type
                })
    except Exception as e:
        print(f"[building_service] Error fetching {url} ({lawd_cd}, {ymd}): {e}")

    _MONTH_CACHE[cache_key] = deals
    return deals

def filter_matched_deals(deals: List[Dict[str, Any]], target_dong: str, target_jibun: str, target_name: str) -> List[Dict[str, Any]]:
    """지번과 단지명을 다단계(Tier)로 비교하여 정확한 대상 건물의 거래만 추출"""
    clean_target_name = normalize_name(target_name)
    clean_target_jibun = (target_jibun or "").replace("*", "").replace("~", "").strip()
    main_jibun = clean_target_jibun.split("-")[0] if clean_target_jibun else ""

    is_generic_name = not clean_target_name or any(g in clean_target_name for g in ["단독", "다가구", "주택", "아파트", "빌라", "토지", "부동산"])

    # 1순위: 지번 완전 일치 (동일 번지 실거래)
    if clean_target_jibun:
        exact_jibun_deals = [
            d for d in deals
            if (not target_dong or not d.get("dong") or target_dong == d["dong"])
            and (d.get("jibun") or "").replace("*", "").replace("~", "").strip() == clean_target_jibun
        ]
        if exact_jibun_deals:
            if not is_generic_name:
                name_matched = [
                    d for d in exact_jibun_deals
                    if clean_target_name in normalize_name(d.get("name")) or normalize_name(d.get("name")) in clean_target_name
                ]
                if name_matched:
                    return name_matched
            return exact_jibun_deals

    # 2순위: 단지명/건물명 완전/부분 일치 (대단지 아파트 번지 상이 또는 검색어 매칭)
    if clean_target_name and not is_generic_name:
        name_deals = [
            d for d in deals
            if (not target_dong or not d.get("dong") or target_dong == d["dong"])
            and (clean_target_name in normalize_name(d.get("name")) or normalize_name(d.get("name")) in clean_target_name)
        ]
        if name_deals:
            return name_deals

    # 3순위: 본번(대표 번지) 일치
    if main_jibun:
        main_jibun_deals = [
            d for d in deals
            if (not target_dong or not d.get("dong") or target_dong == d["dong"])
            and (d.get("jibun") or "").replace("*", "").replace("~", "").strip().split("-")[0] == main_jibun
        ]
        if main_jibun_deals:
            if not is_generic_name:
                name_matched = [
                    d for d in main_jibun_deals
                    if clean_target_name in normalize_name(d.get("name")) or normalize_name(d.get("name")) in clean_target_name
                ]
                if name_matched:
                    return name_matched
            return main_jibun_deals

    return []

def get_building_info_from_gov(
    lawd_cd: str,
    dong: str = "",
    jibun: str = "",
    name: str = "",
    prop_type: str = "apt",
    trade_type: str = "sale",
    start_month: Optional[str] = None,
    end_month: Optional[str] = None
) -> Dict[str, Any]:
    """
    공공데이터포털(국토교통부 실거래가 API)을 중계하여
    특정 건물/단지의 100% 실거래 기반 평형 목록, 면적, 거래 내역, 월별 시세 추이를 제공합니다.
    """
    if not lawd_cd:
        return {"has_real_deals": False, "error": "lawd_cd required"}

    api_category = 'rent' if trade_type in ['jeonse', 'rent'] else 'sale'
    months = generate_month_list(start_month, end_month, default_count=36)

    # 1. 24~36개월 데이터 병렬 요청
    fetch_prop_types = [prop_type]
    if prop_type == 'apt' and jibun:
        fetch_prop_types.extend(['officetel', 'rowhouse'])

    all_fetched_deals: List[Dict[str, Any]] = []

    tasks = []
    with ThreadPoolExecutor(max_workers=24) as executor:
        for pt in fetch_prop_types:
            for ymd in months:
                tasks.append(executor.submit(fetch_single_month, lawd_cd, pt, api_category, ymd))
        for t in tasks:
            all_fetched_deals.extend(t.result())

    # 2. 거래 유형 세부 필터 (전세 vs 월세)
    if api_category == 'rent':
        if trade_type == 'jeonse':
            all_fetched_deals = [d for d in all_fetched_deals if d.get('monthly_rent', 0) == 0]
        elif trade_type == 'rent':
            all_fetched_deals = [d for d in all_fetched_deals if d.get('monthly_rent', 0) > 0]

    # 3. 대상 단지/건물 정밀 매칭
    matched_deals = filter_matched_deals(all_fetched_deals, dong, jibun, name)

    # 매칭된 실거래가 없는 경우
    if not matched_deals:
        return {
            "has_real_deals": False,
            "dong": dong,
            "jibun": jibun,
            "name": name,
            "prop_type": prop_type,
            "build_year": None,
            "total_deals": 0,
            "pyeongs": [],
            "history": [],
            "recent_transactions": []
        }

    # 4. 실거래 데이터 종합 분석
    # 준공년도 결정 (실거래 데이터 중 가장 빈번한 build_year 채택)
    build_years = [d['build_year'] for d in matched_deals if d.get('build_year')]
    best_build_year = max(set(build_years), key=build_years.count) if build_years else None

    # 대표 명칭 및 지번 결정
    official_name = max(set([d['name'] for d in matched_deals if d.get('name')]), key=[d['name'] for d in matched_deals].count)
    official_jibun = matched_deals[0].get('jibun') or jibun
    detected_prop_type = matched_deals[0].get('prop_type') or prop_type
    official_dong = matched_deals[0].get('dong') or dong

    # 5. 평형(전용면적)별 그룹화
    pyeong_groups: Dict[int, List[Dict[str, Any]]] = {}

    for d in matched_deals:
        area = d['area']
        p = calculate_pyeong(detected_prop_type, area)
        if p not in pyeong_groups:
            pyeong_groups[p] = []
        pyeong_groups[p].append(d)

    pyeong_result_list = []
    for p, deals in pyeong_groups.items():
        deals_sorted = sorted(deals, key=lambda x: x['raw_date'], reverse=True)
        areas = [d['area'] for d in deals_sorted]
        best_area = max(set(areas), key=areas.count)
        
        latest_deal = deals_sorted[0]
        prev_deal = deals_sorted[1] if len(deals_sorted) > 1 else latest_deal
        diff = latest_deal['price'] - prev_deal['price']

        pyeong_result_list.append({
            'pyeong': p,
            'area': best_area,
            'exclusive_pyeong': round(best_area / 3.3058, 1),
            'has_data': True,
            'deal_count': len(deals_sorted),
            'latest_price': latest_deal['price'],
            'latest_date': latest_deal['raw_date'],
            'previous_price': prev_deal['price'],
            'previous_date': prev_deal['raw_date'],
            'diff': diff,
            'deals': [
                {
                    'date': d['date'],
                    'price': d['price'],
                    'deposit': d.get('deposit', 0),
                    'monthly_rent': d.get('monthly_rent', 0),
                    'floor': d['floor'],
                    'area': f"{d['area']}㎡",
                    'deal_type': d['deal_type']
                }
                for d in deals_sorted
            ]
        })

    pyeong_result_list.sort(key=lambda x: x['pyeong'])

    # 6. 월별 시세 추이 (history) 생성
    monthly_stats: Dict[str, List[int]] = {}
    for d in matched_deals:
        ym = d['year_month']
        if ym not in monthly_stats:
            monthly_stats[ym] = []
        monthly_stats[ym].append(d['price'])

    timeline_months = sorted(list(set([f"{m[:4]}.{m[4:]}" for m in months])))
    history = []
    last_known_price = matched_deals[-1]['price'] if matched_deals else 50000

    for ym in timeline_months:
        if ym in monthly_stats and monthly_stats[ym]:
            prices = monthly_stats[ym]
            avg_p = int(round(sum(prices) / len(prices)))
            vol = len(prices)
            last_known_price = avg_p
            history.append({
                'month': ym,
                'avg_price': avg_p,
                'volume': vol
            })
        else:
            history.append({
                'month': ym,
                'avg_price': last_known_price,
                'volume': 0
            })

    # 7. 전체 최근 실거래 내역 20건
    all_sorted_deals = sorted(matched_deals, key=lambda x: x['raw_date'], reverse=True)[:20]
    recent_transactions = [
        {
            'date': d['date'],
            'price': d['price'],
            'deposit': d.get('deposit', 0),
            'monthly_rent': d.get('monthly_rent', 0),
            'floor': d['floor'],
            'area': f"{d['area']}㎡",
            'deal_type': d['deal_type']
        }
        for d in all_sorted_deals
    ]

    return {
        "has_real_deals": True,
        "dong": official_dong,
        "jibun": official_jibun,
        "name": official_name,
        "prop_type": detected_prop_type,
        "build_year": best_build_year,
        "total_deals": len(matched_deals),
        "pyeongs": pyeong_result_list,
        "history": history,
        "recent_transactions": recent_transactions
    }
