import os
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, render_template
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

# 공공데이터포털 일반 인증키 (Decoding) - 환경 변수에서 로드
API_KEY = os.environ.get("API_KEY") or os.environ.get("MOLIT_API_KEY")

# 거래유형(매매/전월세) 및 부동산 종류별 공공데이터 API 엔드포인트
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

# 시/도 선택 시 종합 분석을 위한 주요 자치구 매핑
SIDO_MAJOR_DISTRICTS = {
    "11": ["11680", "11650", "11710", "11440", "11170", "11350"], # 서울: 강남, 서초, 송파, 마포, 용산, 노원
    "41": ["41135", "41117", "41465", "41450", "41590", "41281"], # 경기: 성남분당, 수원영통, 용인수지, 하남, 화성, 고양일산
    "28": ["28185", "28200", "28260", "28237"], # 인천: 연수, 남동, 서구, 부평
    "26": ["26350", "26500", "26260", "26290", "26230"], # 부산: 해운대, 수영, 동래, 남구, 부산진
    "27": ["27260", "27290", "27110", "27230"], # 대구: 수성, 달서, 중구, 북구
    "29": ["29155", "29200", "29140", "29170"], # 광주: 남구, 광산, 서구, 북구
    "30": ["30200", "30170", "30140"], # 대전: 유성, 서구, 중구
    "31": ["31140", "31110", "31200"], # 울산: 남구, 중구, 북구
    "36": ["36110"], # 세종
}

def generate_month_list(start, end):
    """시작월(YYYYMM)부터 종료월(YYYYMM)까지의 리스트 생성"""
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

def parse_property_info(item, prop_type):
    """부동산 종류에 따라 XML 노드에서 이름과 면적, 준공년도를 추출 (영문 및 한글 태그 호환)"""
    name = "이름없음"
    area = "0"
    dong = (item.findtext('umdNm') or item.findtext('법정동') or "").strip()
    jibun = (item.findtext('jibun') or item.findtext('지번') or "").strip()

    build_year_str = (item.findtext('buildYear') or item.findtext('건축년도') or "").strip()
    build_year = int(build_year_str) if build_year_str.isdigit() else None

    if prop_type == 'apt':
        name = (item.findtext('aptNm') or item.findtext('아파트') or "이름없음").strip()
        area = (item.findtext('excluUseAr') or item.findtext('전용면적') or "0").strip()
    elif prop_type == 'officetel':
        name = (item.findtext('offiNm') or item.findtext('단지') or "이름없음").strip()
        area = (item.findtext('excluUseAr') or item.findtext('전용면적') or "0").strip()
    elif prop_type == 'rowhouse':
        name = (item.findtext('mhouseNm') or item.findtext('연립다세대') or "이름없음").strip()
        area = (item.findtext('excluUseAr') or item.findtext('전용면적') or "0").strip()
    elif prop_type == 'singlehouse':
        house_type = (item.findtext('houseType') or item.findtext('주택유형') or "단독다가구").strip()
        name = f"{dong} {house_type} {jibun}".strip() if jibun else f"{dong} {house_type}"
        area = (item.findtext('totalFloorAr') or item.findtext('plottageAr') or item.findtext('연면적') or item.findtext('대지면적') or "0").strip()
    elif prop_type == 'land':
        jimok = (item.findtext('jimok') or item.findtext('지목') or "토지").strip()
        name = f"{dong} 토지({jimok}) {jibun}".strip() if jibun else f"{dong} {jimok}"
        area = (item.findtext('dealArea') or item.findtext('거래면적') or "0").strip()
        
    try:
        area = str(round(float(area), 2))
    except Exception:
        pass
        
    return name, area, dong, jibun, build_year

def fetch_month_deals(api_url, district_code, deal_ymd, prop_type, scope, dong_name, api_category, trade_type):
    """단일 월 및 자치구의 거래 데이터를 조회하는 보조 함수"""
    deals = []
    params = {
        'serviceKey': API_KEY,
        'LAWD_CD': district_code,
        'DEAL_YMD': deal_ymd,
        'numOfRows': '9999'
    }
    
    try:
        response = requests.get(api_url, params=params, timeout=12)
        root = ET.fromstring(response.content)
        
        for item in root.findall('.//item'):
            xml_dong = (item.findtext('umdNm') or item.findtext('법정동') or "").strip()
            if scope == 'dong' and dong_name and xml_dong != dong_name:
                continue
                
            name, area, dong, jibun, build_year = parse_property_info(item, prop_type)
            
            price_str = None
            if api_category == 'sale':
                price_str = item.findtext('dealAmount') or item.findtext('거래금액')
            else:
                bojeung = item.findtext('deposit') or item.findtext('보증금액')
                wolse = item.findtext('monthlyRent') or item.findtext('월세금액') or "0"
                
                if bojeung: bojeung = bojeung.replace(',', '').strip()
                wolse = wolse.replace(',', '').strip()
                
                if trade_type == 'jeonse' and wolse == '0':
                    price_str = bojeung # 전세
                elif trade_type == 'rent' and wolse != '0':
                    price_str = wolse   # 월세

            if not price_str:
                continue
                
            price = int(price_str.replace(',', '').strip())
            
            y = (item.findtext('dealYear') or item.findtext('년'))
            m = str(item.findtext('dealMonth') or item.findtext('월')).zfill(2)
            d = str(item.findtext('dealDay') or item.findtext('일')).zfill(2)
            date_str = f"{y}{m}{d}"
            
            deals.append({
                'name': name,
                'area': area,
                'dong': dong,
                'jibun': jibun,
                'date': date_str,
                'price': price,
                'build_year': build_year
            })
    except Exception as e:
        print(f"[{api_category}] API 요청 오류 ({district_code}, {deal_ymd}): {str(e)}")
        
    return deals

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/rankings', methods=['GET'])
def get_rankings():
    lawd_cd = request.args.get('lawd_cd')
    prop_type = request.args.get('prop_type', 'apt')
    trade_type = request.args.get('trade_type', 'sale') # sale, jeonse, rent
    scope = request.args.get('scope', 'all')
    dong_name = request.args.get('dong_name', '')
    start_month = request.args.get('start_month')
    end_month = request.args.get('end_month')

    if not lawd_cd or not start_month or not end_month:
        return jsonify({'error': '필수 파라미터가 누락되었습니다.'}), 400

    api_category = 'rent' if trade_type in ['jeonse', 'rent'] else 'sale'

    if api_category == 'rent' and prop_type == 'land':
        return jsonify({'error': '토지는 전월세 실거래가 데이터를 제공하지 않습니다.'}), 400

    if prop_type not in API_ENDPOINTS[api_category]:
        return jsonify({'error': '해당 부동산 종류에 대한 API가 없습니다.'}), 400

    api_url = API_ENDPOINTS[api_category][prop_type]
    months_to_fetch = generate_month_list(start_month, end_month)
    
    if len(months_to_fetch) > 36:
        return jsonify({'error': 'API 트래픽 과부하를 방지하기 위해 조회 기간은 최대 3년(36개월)까지만 가능합니다.'}), 400

    districts = [lawd_cd]
    if len(lawd_cd) == 2:
        districts = SIDO_MAJOR_DISTRICTS.get(lawd_cd, [])
        if not districts:
            return jsonify({'error': '선택하신 시/도는 아직 데이터 조회 매핑이 준비되지 않았습니다.'}), 400

    fetch_tasks = []
    for d_cd in districts:
        for deal_ymd in months_to_fetch:
            fetch_tasks.append((d_cd, deal_ymd))

    transactions = {}
    
    with ThreadPoolExecutor(max_workers=20) as executor:
        results_futures = []
        for d_cd, deal_ymd in fetch_tasks:
            future = executor.submit(
                fetch_month_deals, 
                api_url, d_cd, deal_ymd, prop_type, scope, dong_name, api_category, trade_type
            )
            results_futures.append(future)
            
        for future in results_futures:
            deals = future.result()
            for deal in deals:
                key = f"{deal['name']}_{deal['area']}"
                if key not in transactions:
                    transactions[key] = {
                        'name': deal['name'],
                        'area': deal['area'],
                        'dong': deal['dong'],
                        'jibun': deal['jibun'],
                        'build_year': deal.get('build_year'),
                        'deals': []
                    }
                elif not transactions[key].get('build_year') and deal.get('build_year'):
                    transactions[key]['build_year'] = deal.get('build_year')
                transactions[key]['deals'].append(deal)

    results = []
    for key, data in transactions.items():
        deals = data['deals']
        
        # 중복 계약 필터링 (같은 날 같은 금액 제외)
        unique_deals = {}
        for d in deals:
            d_key = f"{d['date']}_{d['price']}"
            unique_deals[d_key] = d
        deals = list(unique_deals.values())
        
        # 다른 날짜에 체결된 거래가 2건 이상 있어야 비교 가능
        date_groups = {}
        for d in deals:
            if d['date'] not in date_groups:
                date_groups[d['date']] = []
            date_groups[d['date']].append(d['price'])
            
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
                'latest_date': latest_date,
                'latest_price': latest_price,
                'previous_date': latest_date,
                'previous_price': latest_price,
                'diff': 0
            })

    soaring = sorted([r for r in results if r['diff'] > 0], key=lambda x: x['diff'], reverse=True)[:50]
    plunging = sorted([r for r in results if r['diff'] < 0], key=lambda x: x['diff'])[:50]
    items = sorted(results, key=lambda x: x['latest_price'], reverse=True)[:1000]

    return jsonify({
        'soaring': soaring,
        'plunging': plunging,
        'items': items
    })

@app.route('/api/building-info', methods=['GET'])
def get_building_info():
    lawd_cd = request.args.get('lawd_cd', '')
    dong = request.args.get('dong', '')
    jibun = request.args.get('jibun', '')
    name = request.args.get('name', '')
    prop_type = request.args.get('prop_type', 'apt')
    trade_type = request.args.get('trade_type', 'sale')
    start_month = request.args.get('start_month')
    end_month = request.args.get('end_month')
    building_dong = request.args.get('building_dong', '')

    if not lawd_cd:
        lawd_cd = '11650'

    from building_service import get_building_info_from_gov
    data = get_building_info_from_gov(
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
    return jsonify(data)

@app.route('/api/complex-history', methods=['GET'])
def get_complex_history():
    dong = request.args.get('dong', '')
    name = request.args.get('name', '')
    jibun = request.args.get('jibun', '')
    lawd_cd = request.args.get('lawd_cd', '11650')
    prop_type = request.args.get('prop_type', 'apt')
    trade_type = request.args.get('trade_type', 'sale')
    start_month = request.args.get('start_month')
    end_month = request.args.get('end_month')
    building_dong = request.args.get('building_dong', '')

    from building_service import get_building_info_from_gov
    real_data = get_building_info_from_gov(
        lawd_cd=lawd_cd or '11650',
        dong=dong,
        jibun=jibun,
        name=name,
        prop_type=prop_type,
        trade_type=trade_type,
        start_month=start_month,
        end_month=end_month,
        building_dong=building_dong
    )
    if real_data.get('has_real_deals'):
        return jsonify({
            'dong': real_data['dong'],
            'name': real_data['name'],
            'build_year': real_data['build_year'],
            'history': real_data['history'],
            'recent_transactions': real_data['recent_transactions'],
            'pyeongs': real_data['pyeongs'],
            'matched_dong_pyeong': real_data.get('matched_dong_pyeong'),
            'is_real_data': True
        })

    from main import generate_mock_complex_data
    history, recent_transactions, build_year = generate_mock_complex_data(dong, name)
    return jsonify({
        'dong': dong,
        'name': name,
        'build_year': build_year,
        'history': [h.model_dump() for h in history],
        'recent_transactions': [t.model_dump() for t in recent_transactions],
        'is_real_data': False
    })

if __name__ == '__main__':
    app.run(port=5001, debug=True)

