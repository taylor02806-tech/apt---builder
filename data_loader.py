import os
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

PROP_ENDPOINTS = {
    "apt": "https://apis.data.go.kr/1613000/RTMSDataSvcAptTradeDev/getRTMSDataSvcAptTradeDev",
    "officetel": "https://apis.data.go.kr/1613000/RTMSDataSvcOffiTrade/getRTMSDataSvcOffiTrade",
    "rowhouse": "https://apis.data.go.kr/1613000/RTMSDataSvcRHTrade/getRTMSDataSvcRHTrade",
    "singlehouse": "https://apis.data.go.kr/1613000/RTMSDataSvcSHTrade/getRTMSDataSvcSHTrade",
    "land": "https://apis.data.go.kr/1613000/RTMSDataSvcLandTrade/getRTMSDataSvcLandTrade"
}

def get_recent_6_months():
    today = datetime.today()
    return [(today - relativedelta(months=i)).strftime("%Y%m") for i in range(6)]

def get_month_range(start_month=None, end_month=None):
    if start_month and end_month:
        try:
            start = datetime.strptime(start_month, "%Y%m")
            end = datetime.strptime(end_month, "%Y%m")
            if start > end:
                start, end = end, start
            months = []
            curr = end
            while curr >= start:
                months.append(curr.strftime("%Y%m"))
                curr -= relativedelta(months=1)
            return months[:120]
        except Exception:
            pass
    return get_recent_6_months()

def fetch_single_month(prop_type, url, api_key, lawd_cd, ymd):
    items_data = []
    request_url = f"{url}?serviceKey={api_key}&pageNo=1&numOfRows=9999&LAWD_CD={lawd_cd}&DEAL_YMD={ymd}"
    try:
        response = requests.get(request_url, timeout=15)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        items = root.findall(".//item")
        
        for item in items:
            dong = (item.findtext("umdNm") or item.findtext("법정동") or "").strip()
            price_str = (item.findtext("dealAmount") or item.findtext("거래금액") or "").strip()
            day = (item.findtext("dealDay") or item.findtext("일") or "").strip()
            
            if prop_type == "officetel":
                name = (item.findtext("offiNm") or item.findtext("단지") or "오피스텔").strip()
                area_str = (item.findtext("excluUseAr") or item.findtext("전용면적") or "0").strip()
            elif prop_type == "rowhouse":
                name = (item.findtext("mhouseNm") or item.findtext("연립다세대") or "연립다세대").strip()
                area_str = (item.findtext("excluUseAr") or item.findtext("전용면적") or "0").strip()
            elif prop_type == "singlehouse":
                htype = (item.findtext("houseType") or item.findtext("주택유형") or "단독/다가구").strip()
                jibun = (item.findtext("jibun") or "").strip()
                name = f"{htype} {jibun}".strip()
                area_str = (item.findtext("totalFloorAr") or item.findtext("plottageAr") or item.findtext("연면적") or "0").strip()
            elif prop_type == "land":
                jimok = (item.findtext("jimok") or item.findtext("지목") or "토지").strip()
                jibun = (item.findtext("jibun") or "").strip()
                name = f"토지({jimok}) {jibun}".strip()
                area_str = (item.findtext("dealArea") or item.findtext("대지면적") or "0").strip()
            else:  # apt
                name = (item.findtext("aptNm") or item.findtext("아파트") or "").strip()
                area_str = (item.findtext("excluUseAr") or item.findtext("전용면적") or "0").strip()

            if not name or not price_str:
                continue
            
            price = int(price_str.replace(",", "").strip())
            dong = dong if dong else "알수없음"
            
            try:
                area = round(float(area_str), 2)
            except Exception:
                area = 0.0

            if day:
                day = day.strip()
                if '~' in day:
                    day = day.split('~')[0].zfill(2)
                else:
                    day = day.zfill(2)
            else:
                day = "01"
                
            build_year_str = (item.findtext('buildYear') or item.findtext('건축년도') or "").strip()
            build_year = int(build_year_str) if build_year_str.isdigit() else None
                
            deal_ymd = ymd + day
            
            items_data.append({
                "apt": name,
                "area": area,
                "price": price,
                "date": deal_ymd,
                "dong": dong,
                "build_year": build_year
            })
    except Exception:
        pass
    return items_data

def fetch_apt_data(lawd_cd, prop_type="apt", months=None):
    api_key = os.getenv("MOLIT_API_KEY")
    url = PROP_ENDPOINTS.get(prop_type, PROP_ENDPOINTS["apt"])
    
    if not months:
        months = get_recent_6_months()
    
    all_data = []

    if len(months) > 1:
        with ThreadPoolExecutor(max_workers=min(len(months), 10)) as executor:
            month_results = list(executor.map(lambda ymd: fetch_single_month(prop_type, url, api_key, lawd_cd, ymd), months))
            for res in month_results:
                all_data.extend(res)
    else:
        all_data.extend(fetch_single_month(prop_type, url, api_key, lawd_cd, months[0]))

    df = pd.DataFrame(all_data)
    print(f"✅ 총 수집된 거래 건수 ({prop_type} / {len(months)}개월 / {lawd_cd}): {len(df)}건")
    return df

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

def get_soaring_plunging(lawd_cd, prop_type="apt", scope="all", dong_name=None, start_month=None, end_month=None):
    months = get_month_range(start_month, end_month)
    
    if len(lawd_cd) == 2:
        districts = SIDO_MAJOR_DISTRICTS.get(lawd_cd, [lawd_cd + "110"])
        with ThreadPoolExecutor(max_workers=min(len(districts), 6)) as executor:
            dfs = list(executor.map(lambda d: fetch_apt_data(d, prop_type=prop_type, months=months), districts))
        df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    else:
        df = fetch_apt_data(lawd_cd, prop_type=prop_type, months=months)
    
    if df.empty:
        return {"soaring": [], "plunging": []}
    
    if scope == "dong" and dong_name:
        df = df[df['dong'] == dong_name]
        
    if df.empty:
        return {"soaring": [], "plunging": []}
        
    df['key'] = df['dong'] + " " + df['apt'] + " (" + df['area'].astype(str) + "㎡)"
    
    results = []
    
    for key, group in df.groupby('key'):
        if len(group) >= 2:
            group = group.sort_values(by='date', ascending=False).reset_index(drop=True)
            latest = group.iloc[0]
            
            previous = None
            for idx in range(1, len(group)):
                if group.iloc[idx]['date'] != latest['date']:
                    previous = group.iloc[idx]
                    break
                    
            if previous is not None:
                diff = latest['price'] - previous['price']
                results.append({
                    "name": f"{latest['dong']} {latest['apt']}",
                    "area": latest['area'],
                    "latest_price": int(latest['price']),
                    "previous_price": int(previous['price']),
                    "latest_date": latest['date'],
                    "previous_date": previous['date'],
                    "build_year": latest.get('build_year'),
                    "diff": int(diff)
                })
                
    if not results:
        return {"soaring": [], "plunging": []}
        
    results_df = pd.DataFrame(results)
    results_df = results_df.sort_values(by='diff')
    
    plunging = results_df.head(5).to_dict('records')
    soaring = results_df.tail(5).iloc[::-1].to_dict('records')
    
    return {
        "soaring": soaring,
        "plunging": plunging
    }
