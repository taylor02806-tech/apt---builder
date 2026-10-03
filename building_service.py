import os
import re
import time
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

# 서울/수도권 주요 법정동 -> 시군구코드(LAWD_CD) 매핑 사전
# 클라이언트에서 lawd_cd가 누락되거나 이전 위치 값으로 전달되더라도 100% 자동 교정
DONG_TO_LAWD_CD = {
    # 은평구 (11380) - 구파발, 진관동 등
    '진관동': '11380', '구파발동': '11380', '불광동': '11380', '갈현동': '11380',
    '대조동': '11380', '응암동': '11380', '역촌동': '11380', '신사동_은평': '11380',
    '증산동': '11380', '수색동': '11380',
    
    # 서초구 (11650)
    '반포동': '11650', '서초동': '11650', '방배동': '11650', '잠원동': '11650',
    '양재동': '11650', '우면동': '11650', '원지동': '11650', '신원동': '11650',
    '염곡동': '11650', '내곡동': '11650',

    # 강남구 (11680)
    '역삼동': '11680', '개포동': '11680', '청담동': '11680', '삼성동': '11680',
    '대치동': '11680', '논현동': '11680', '압구정동': '11680', '세곡동': '11680',
    '자곡동': '11680', '율현동': '11680', '일원동': '11680', '수서동': '11680', '도곡동': '11680',

    # 송파구 (11710)
    '잠실동': '11710', '신천동': '11710', '풍납동': '11710', '송파동': '11710',
    '석촌동': '11710', '삼전동': '11710', '가락동': '11710', '문정동': '11710',
    '장지동': '11710', '방이동': '11710', '오금동': '11710', '거여동': '11710', '마천동': '11710',

    # 마포구 (11440)
    '아현동': '11440', '공덕동': '11440', '신공덕동': '11440', '도화동': '11440',
    '용강동': '11440', '대흥동': '11440', '염리동': '11440', '노고산동': '11440',
    '신수동': '11440', '서교동': '11440', '동교동': '11440', '합정동': '11440',
    '망원동': '11440', '연남동': '11440', '성산동': '11440', '상암동': '11440',

    # 용산구 (11170)
    '후암동': '11170', '용산동': '11170', '갈월동': '11170', '남영동': '11170',
    '동자동': '11170', '청파동': '11170', '원효로': '11170', '효창동': '11170',
    '한강로': '11170', '이촌동': '11170', '이태원동': '11170', '한남동': '11170',
    '서빙고동': '11170', '보광동': '11170',

    # 성동구 (11200)
    '상왕십리동': '11200', '하왕십리동': '11200', '홍익동': '11200', '도선동': '11200',
    '마장동': '11200', '사근동': '11200', '행당동': '11200', '응봉동': '11200',
    '금호동': '11200', '옥수동': '11200', '성수동': '11200', '송정동': '11200', '용답동': '11200',

    # 노원구 (11350)
    '월계동': '11350', '공릉동': '11350', '하계동': '11350', '상계동': '11350', '중계동': '11350',

    # 양천구 (11470)
    '신정동': '11470', '목동': '11470', '신월동': '11470',

    # 영등포구 (11560)
    '영등포동': '11560', '여의도동': '11560', '당산동': '11560', '문래동': '11560',
    '양평동': '11560', '신길동': '11560', '대림동': '11560',

    # 강동구 (11740)
    '명일동': '11740', '고덕동': '11740', '상일동': '11740', '길동': '11740',
    '둔촌동': '11740', '암사동': '11740', '천호동': '11740', '강일동': '11740',

    # 동작구 (11590)
    '노량진동': '11590', '상도동': '11590', '흑석동': '11590', '사당동': '11590', '대방동': '11590',

    # 광진구 (11215)
    '화양동': '11215', '군자동': '11215', '중곡동': '11215', '구의동': '11215', '광장동': '11215', '자양동': '11215',

    # 서대문구 (11410)
    '북아현동': '11410', '홍제동': '11410', '신촌동': '11410', '연희동': '11410', '홍은동': '11410', '남가좌동': '11410', '북가좌동': '11410',

    # 종로구 (11110)
    '평창동': '11110', '혜화동': '11110', '명륜동': '11110', '창신동': '11110', '숭인동': '11110', '무악동': '11110',

    # 중구 (11140)
    '회현동': '11140', '명동': '11140', '신당동': '11140', '황학동': '11140', '중림동': '11140',

    # 성남시 분당구 (41135)
    '정자동': '41135', '서현동': '41135', '이매동': '41135', '야탑동': '41135',
    '판교동': '41135', '삼평동': '41135', '백현동': '41135', '운중동': '41135', '구미동': '41135',

    # 과천시 (41290)
    '별양동': '41290', '중앙동': '41290', '원문동': '41290', '부림동': '41290'
}

def resolve_lawd_cd(lawd_cd: Optional[str], dong: Optional[str]) -> str:
    """법정동 명칭을 기반으로 누락되거나 불일치하는 시군구코드(lawd_cd)를 자동 교정"""
    if dong:
        d_clean = dong.strip()
        # 특수 케이스: 진관동/구파발 -> 은평구 (11380)
        if '진관' in d_clean or '구파발' in d_clean:
            return '11380'
        if d_clean in DONG_TO_LAWD_CD:
            return DONG_TO_LAWD_CD[d_clean]
        for k, v in DONG_TO_LAWD_CD.items():
            if k.rstrip('동') == d_clean.rstrip('동'):
                return v

    if lawd_cd and len(lawd_cd) == 5:
        return lawd_cd
    return '11650'

# In-memory cache for monthly deals
# Key: (lawd_cd, prop_type, api_category, ymd) -> List[Dict]
_MONTH_CACHE: Dict[tuple, List[Dict[str, Any]]] = {}

def normalize_name(name: str) -> str:
    """
    단지명 또는 건물명 정규화 (은평뉴타운, 판교 등 복합 신도시 단지명 호환)
    예: '우물골2단지두산위브(223~244동)BL2-7' -> '우물골2단지두산위브'
    """
    if not name:
        return ""
    # 1. 괄호 내용 먼저 제거: (223~244동), (916~928동) 등
    n = re.sub(r'[(（].*?[)）]', '', name)
    # 2. 블록/단지 번호 표기 제거 (BL3-2 등)
    n = re.sub(r'BL\s*\d+[-~]\d+', '', n, flags=re.IGNORECASE)
    n = re.sub(r'\bBL\b.*$', '', n, flags=re.IGNORECASE)
    # 3. 신도시 접두어 제거
    n = re.sub(r'은평뉴타운|판교|동탄|미사강변|위례', '', n)
    # 4. 동 번호 접미사 제거
    n = re.sub(r'\s*\d+동.*$', '', n)
    n = re.sub(r'아파트$', '', n)
    n = re.sub(r'[^\w가-힣0-9]', '', n)
    return n.strip()

def get_normalized_tokens(name: str) -> List[str]:
    """단지명의 핵심 토큰(키워드) 목록 추출 (단지 번호 및 브랜드 분리)"""
    if not name:
        return []
    n = re.sub(r'[(（].*?[)）]', '', name)
    n = re.sub(r'BL\s*\d+[-~]\d+', '', n, flags=re.IGNORECASE)
    n = re.sub(r'\bBL\b.*$', '', n, flags=re.IGNORECASE)
    n = re.sub(r'은평뉴타운|판교|동탄|미사강변|위례', '', n)
    n = re.sub(r'아파트$', '', n)
    tokens = [t for t in re.split(r'(\d+단지|\d+차|\d+)', n) if t.strip()]
    return [t.strip() for t in tokens if len(t.strip()) >= 2 or re.match(r'^\d+$', t.strip())]

def is_complex_name_match(gov_name: str, target_name: str) -> bool:
    """공식 단지명과 사용자/지도 검색 단지명 간의 고도화된 매칭"""
    if not gov_name or not target_name:
        return False
    g_norm = normalize_name(gov_name)
    t_norm = normalize_name(target_name)
    if not g_norm or not t_norm:
        return False

    # 1. 완전 일치 또는 부분 문자열 포함
    if g_norm == t_norm or g_norm in t_norm or t_norm in g_norm:
        return True

    # 2. 토큰 단위 포함 검사 (단어 순서가 바뀐 경우 대응: '박석고개 1단지 힐스테이트' vs '박석고개 힐스테이트 1단지')
    g_tokens = get_normalized_tokens(gov_name)
    t_tokens = get_normalized_tokens(target_name)

    if len(t_tokens) >= 2 and all(tok in g_norm for tok in t_tokens if len(tok) >= 2):
        return True
    if len(g_tokens) >= 2 and all(tok in t_norm for tok in g_tokens if len(tok) >= 2):
        return True

    return False

def calculate_pyeong(prop_type: str, area_sqm: float) -> int:
    """
    국토교통부 전용면적(㎡)을 한국 부동산 표준 공급 평형으로 변환.
    - 아파트: 평균 전용률 약 74~76% 반영 (59㎡ -> 24평형, 84㎡ -> 34평형, 101㎡ -> 41평형, 134㎡ -> 54평형)
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

# 주요 대단지 아파트 동별 공급 평형 매핑 테이블 (Known Complex Dong Registry)
# ((시작동, 끝동), 공급평형(pyeong)) 리스트
KNOWN_COMPLEX_DONG_PYEONGS = {
    # 은평구 구파발 / 진관동 대단지
    '구파발9단지래미안': [
        ((916, 920), 34),
        ((921, 922), 41),
        ((923, 926), 54),
        ((927, 928), 67),
    ],
    '구파발9단지': [
        ((916, 920), 34),
        ((921, 922), 41),
        ((923, 926), 54),
        ((927, 928), 67),
    ],
    '우물골9단지': [
        ((916, 920), 34),
        ((921, 922), 41),
        ((923, 926), 54),
        ((927, 928), 67),
    ],
    '우물골2단지': [
        ((201, 205), 24),
        ((206, 215), 34),
        ((216, 220), 41),
        ((221, 230), 54),
        ((231, 244), 67),
    ],
    '우물골두산위브': [
        ((201, 205), 24),
        ((206, 215), 34),
        ((216, 220), 41),
        ((221, 230), 54),
        ((231, 244), 67),
    ],
    '박석고개1단지': [
        ((101, 110), 24),
        ((111, 122), 34),
        ((123, 128), 41),
        ((129, 131), 54),
    ],
    '박석고개힐스테이트': [
        ((101, 110), 24),
        ((111, 122), 34),
        ((123, 128), 41),
        ((129, 131), 54),
    ],
    '박석고개12단지': [
        ((1201, 1208), 34),
        ((1209, 1215), 41),
    ],
    '마고정3단지': [
        ((301, 308), 34),
        ((309, 316), 41),
        ((317, 324), 54),
        ((325, 330), 67),
    ],
    '제각말5단지': [
        ((501, 510), 34),
        ((511, 518), 41),
    ],
    '은평스카이뷰자이': [
        ((101, 103), 34),
    ],
    # 서초 / 강남
    '반포자이': [
        ((101, 114), 35),
        ((115, 120), 50),
        ((121, 125), 60),
        ((126, 130), 70),
        ((131, 144), 35),
    ],
    '래미안원베일리': [
        ((101, 110), 34),
        ((111, 116), 24),
        ((117, 123), 46),
    ],
    '아크로리버파크': [
        ((101, 108), 34),
        ((109, 112), 24),
        ((113, 116), 45),
        ((117, 120), 52),
    ],
    '반포래미안퍼스티지': [
        ((101, 115), 34),
        ((116, 122), 26),
        ((123, 128), 44),
    ],
    '디에이치퍼스티어아이파크': [
        ((101, 130), 34),
        ((131, 160), 25),
        ((161, 174), 43),
    ],
    # 송파
    '잠실엘스': [
        ((101, 140), 34),
        ((141, 155), 25),
        ((156, 172), 45),
    ],
    '리센츠': [
        ((201, 220), 33),
        ((221, 240), 24),
        ((241, 265), 48),
    ],
    '트리지움': [
        ((301, 325), 33),
        ((326, 338), 25),
        ((339, 346), 43),
    ],
    '헬리오시티': [
        ((101, 118), 33),
        ((201, 215), 25),
        ((301, 320), 38),
        ((401, 418), 42),
        ((501, 514), 50),
    ],
    '파크리오': [
        ((101, 130), 33),
        ((201, 218), 26),
        ((301, 320), 45),
    ],
    # 마포
    '마포래미안푸르지오': [
        ((101, 114), 34),
        ((201, 214), 24),
        ((301, 315), 34),
        ((401, 415), 45),
    ],
    # 강동
    '고덕그라시움': [
        ((101, 125), 34),
        ((126, 140), 25),
        ((141, 153), 40),
    ],
    '올림픽선수기자촌': [
        ((101, 120), 34),
        ((201, 220), 40),
        ((301, 325), 49),
        ((326, 340), 57),
    ]
}

def resolve_dong_pyeong(
    complex_name: str,
    dong_str: Optional[str],
    pyeongs: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:
    """
    지도에서 클릭한 동(예: '924동', '101동')을 단지의 실거래 평형(pyeong)에 정확히 매칭합니다.
    """
    if not dong_str or not pyeongs:
        return None

    # 동 번호 숫자 추출
    dong_digits = re.search(r'\d+', str(dong_str))
    if not dong_digits:
        return None
    dong_num = int(dong_digits.group(0))
    dong_label = f"{dong_num}동"

    # 1. 단일 평형 단지 (예: 은평스카이뷰자이 34평 단독)
    if len(pyeongs) == 1:
        p = pyeongs[0]
        return {
            "dong": dong_label,
            "dong_num": dong_num,
            "pyeong": p["pyeong"],
            "area": p["area"],
            "exclusive_pyeong": p.get("exclusive_pyeong", round(p["area"] / 3.3058, 1)),
            "confidence": "high",
            "matched_by": "단일 평형 단지 (100% 일치)",
            "description": f"{dong_label} (전용 {p['area']}㎡ · {p['pyeong']}평형 자동 연동)"
        }

    # 2. 알려진 단지 매핑 사전 조회
    clean_target = normalize_name(complex_name)
    for known_key, rules in KNOWN_COMPLEX_DONG_PYEONGS.items():
        k_norm = normalize_name(known_key)
        if (k_norm and (k_norm in clean_target or clean_target in k_norm)) or (known_key in complex_name):
            for (start_d, end_d), target_p in rules:
                if start_d <= dong_num <= end_d:
                    exact_p = next((p for p in pyeongs if p['pyeong'] == target_p), None)
                    if not exact_p:
                        exact_p = min(pyeongs, key=lambda p: abs(p['pyeong'] - target_p))
                    return {
                        "dong": dong_label,
                        "dong_num": dong_num,
                        "pyeong": exact_p["pyeong"],
                        "area": exact_p["area"],
                        "exclusive_pyeong": exact_p.get("exclusive_pyeong", round(exact_p["area"] / 3.3058, 1)),
                        "confidence": "high",
                        "matched_by": "단지 동별 공식 평형 배치도",
                        "description": f"{dong_label} (전용 {exact_p['area']}㎡ · {exact_p['pyeong']}평형 자동 연동)"
                    }

    # 3. 단지명에 표기된 동 범위 파싱 (예: '... (916~928동) ...')
    range_match = re.search(r'(\d+)\s*[-~]\s*(\d+)동', complex_name)
    if range_match:
        range_start = int(range_match.group(1))
        range_end = int(range_match.group(2))
        if range_start <= dong_num <= range_end and range_end > range_start:
            rel_pos = (dong_num - range_start) / (range_end - range_start)
            sorted_pyeongs = sorted(pyeongs, key=lambda p: p['pyeong'])
            total_deals = sum(p.get('deal_count', 1) for p in sorted_pyeongs) or 1
            cum_share = 0.0
            chosen_p = sorted_pyeongs[-1]
            for p in sorted_pyeongs:
                cum_share += (p.get('deal_count', 1) / total_deals)
                if rel_pos <= cum_share:
                    chosen_p = p
                    break
            return {
                "dong": dong_label,
                "dong_num": dong_num,
                "pyeong": chosen_p["pyeong"],
                "area": chosen_p["area"],
                "exclusive_pyeong": chosen_p.get("exclusive_pyeong", round(chosen_p["area"] / 3.3058, 1)),
                "confidence": "medium",
                "matched_by": "단지 동 범위 가중 분배",
                "description": f"{dong_label} (전용 {chosen_p['area']}㎡ · {chosen_p['pyeong']}평형 자동 매칭)"
            }

    # 4. 휴리스틱 최적 매칭 (국민평형 34평 우선 또는 최다 거래 평형)
    sorted_by_deals = sorted(pyeongs, key=lambda p: p.get('deal_count', 0), reverse=True)
    p34 = next((p for p in pyeongs if p['pyeong'] == 34), None)
    best_p = p34 if p34 else sorted_by_deals[0]

    return {
        "dong": dong_label,
        "dong_num": dong_num,
        "pyeong": best_p["pyeong"],
        "area": best_p["area"],
        "exclusive_pyeong": best_p.get("exclusive_pyeong", round(best_p["area"] / 3.3058, 1)),
        "confidence": "heuristic",
        "matched_by": "단지 대표 평형",
        "description": f"{dong_label} (대표 {best_p['pyeong']}평형 연동)"
    }

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
    """
    공공데이터포털 API에서 단일 월의 실거래가 데이터를 조회 및 캐싱.
    초당 요청 제한(HTTP 429) 발생 시 지수 백오프 자동 재시도로 안정성 보장.
    """
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
    # 최대 4회 재시도 (초당 요청 제한 429 대응)
    for attempt in range(4):
        try:
            resp = requests.get(url, params=params, timeout=12)
            
            # 초당 요청제한 초과 에러(429) 시 대기 후 재시도
            if resp.status_code == 429 or "LIMITED_NUMBER_OF_SERVICE_REQUESTS" in (resp.text or ""):
                time.sleep(0.35 * (attempt + 1))
                continue

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
                
                # 성공적으로 파싱된 경우만 캐싱 후 루프 종료
                _MONTH_CACHE[cache_key] = deals
                return deals
        except Exception as e:
            time.sleep(0.2)

    return deals

def filter_matched_deals(deals: List[Dict[str, Any]], target_dong: str, target_jibun: str, target_name: str) -> List[Dict[str, Any]]:
    """지번과 단지명을 다단계(Tier)로 비교하여 정확한 대상 건물의 거래만 추출"""
    clean_target_jibun = (target_jibun or "").replace("*", "").replace("~", "").strip()
    main_jibun = clean_target_jibun.split("-")[0] if clean_target_jibun else ""
    target_clean = (target_name or "").strip()
    is_generic_name = not target_clean or any(g in target_clean for g in ["단독", "다가구", "주택", "아파트", "빌라", "토지", "부동산"])

    # 1순위: 지번 완전 일치 (동일 번지 실거래)
    if clean_target_jibun:
        exact_jibun_deals = [
            d for d in deals
            if (not target_dong or not d.get("dong") or target_dong == d["dong"])
            and (d.get("jibun") or "").replace("*", "").replace("~", "").strip() == clean_target_jibun
        ]
        if exact_jibun_deals:
            if not is_generic_name:
                name_matched = [d for d in exact_jibun_deals if is_complex_name_match(d.get("name", ""), target_clean)]
                if name_matched:
                    return name_matched
            return exact_jibun_deals

    # 2순위: 단지명/건물명 고도화 토큰 일치
    if target_clean and not is_generic_name:
        name_deals = [
            d for d in deals
            if (not target_dong or not d.get("dong") or target_dong == d["dong"])
            and is_complex_name_match(d.get("name", ""), target_clean)
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
                name_matched = [d for d in main_jibun_deals if is_complex_name_match(d.get("name", ""), target_clean)]
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
    end_month: Optional[str] = None,
    building_dong: Optional[str] = None
) -> Dict[str, Any]:
    """
    공공데이터포털(국토교통부 실거래가 API)을 중계하여
    특정 건물/단지의 100% 실거래 기반 평형 목록, 면적, 거래 내역, 월별 시세 추이를 제공합니다.
    선택한 동(building_dong)이 제공되면 해당 동에 맞춰 평형을 지능형 자동 연동합니다.
    """
    # 법정동 명칭 기반 시군구코드(LAWD_CD) 자동 검증 및 교정
    actual_lawd_cd = resolve_lawd_cd(lawd_cd, dong)

    api_category = 'rent' if trade_type in ['jeonse', 'rent'] else 'sale'
    months = generate_month_list(start_month, end_month, default_count=36)

    # 1. 24~36개월 데이터 병렬 요청 (초당 요청 제한을 피해 worker 6개로 안정적 쿼리)
    fetch_prop_types = [prop_type]
    if prop_type == 'apt' and jibun:
        fetch_prop_types.extend(['officetel', 'rowhouse'])

    all_fetched_deals: List[Dict[str, Any]] = []

    tasks = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        for pt in fetch_prop_types:
            for ymd in months:
                tasks.append(executor.submit(fetch_single_month, actual_lawd_cd, pt, api_category, ymd))
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
            "matched_dong_pyeong": None,
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

    # 6. 선택한 동(building_dong) 기반 공급 평형 자동 연동 매칭
    matched_dong_pyeong = resolve_dong_pyeong(official_name or name, building_dong, pyeong_result_list)

    # 7. 월별 시세 추이 (history) 생성
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

    # 8. 전체 최근 실거래 내역 20건
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
        "matched_dong_pyeong": matched_dong_pyeong,
        "pyeongs": pyeong_result_list,
        "history": history,
        "recent_transactions": recent_transactions
    }
