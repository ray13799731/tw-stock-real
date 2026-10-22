# -------------------------------------------------------------------------
# 1. 修復：上市行情漲跌符號解析 (徹底剝除 HTML 標籤)
# -------------------------------------------------------------------------
def fetch_all_quotes():
    stocks = {}
    print("正在請求證交所 (TWSE) 上市收盤行情...")
    try:
        url_twse = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999"
        res = requests.get(url_twse, headers=HEADERS, timeout=25)
        if res.status_code == 200:
            data = res.json()
            rows = data.get('data9')
            if not rows and 'tables' in data:
                for t in data['tables']:
                    if '每日收盤行情' in t.get('title', ''):
                        rows = t.get('data', [])
                        break
            if rows:
                for row in rows:
                    code = str(row[0]).strip()
                    name = str(row[1]).strip()
                    if len(code) != 4 or not code.isdigit():
                        continue
                    vol_shares = clean_number(row[2])
                    price = clean_number(row[8])
                    raw_diff = clean_number(row[9]) if len(row) > 9 else 0.0
                    
                    # 徹底剝除 HTML 標籤並轉小寫判定
                    sign_raw = str(row[7]).lower()
                    sign_clean = re.sub(r'<[^>]+>', '', sign_raw).strip()
                    
                    if '-' in sign_clean or 'green' in sign_raw:
                        diff = -abs(raw_diff)
                    elif '+' in sign_clean or 'red' in sign_raw:
                        diff = abs(raw_diff)
                    elif raw_diff > 0:
                        diff = abs(raw_diff)
                    else:
                        diff = 0.0

                    pre_close = price - diff
                    change_rate = round((diff / pre_close) * 100, 2) if pre_close > 0 and diff != 0 else 0.0

                    stocks[code] = {
                        'code': code, 'name': name, 'market': '上市',
                        'price': price, 'change': round(diff, 2), 'changeRate': change_rate,
                        'yesterdayVol': int(vol_shares // 1000)
                    }
                print(f"成功取得 {len(stocks)} 檔上市股票。")
    except Exception as e:
        print(f"上市行情抓取異常: {e}")

    print("正在請求櫃買中心 (TPEx) 上櫃收盤行情...")
    try:
        url_tpex = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes"
        res = requests.get(url_tpex, headers=HEADERS, timeout=20)
        if res.status_code == 200:
            for item in res.json():
                code = str(item.get("SecuritiesCompanyCode", item.get("Code", ""))).strip()
                name = str(item.get("CompanyName", item.get("Name", ""))).strip()
                if len(code) != 4 or not code.isdigit():
                    continue
                price = clean_number(item.get("Close", 0))
                diff = clean_number(item.get("Change", 0))
                vol_shares = clean_number(item.get("TradingShares", 0))
                pre_close = price - diff
                change_rate = round((diff / pre_close) * 100, 2) if pre_close > 0 and diff != 0 else 0.0

                stocks[code] = {
                    'code': code, 'name': name, 'market': '上櫃',
                    'price': price, 'change': round(diff, 2), 'changeRate': change_rate,
                    'yesterdayVol': int(vol_shares // 1000)
                }
    except Exception as e:
        print(f"上櫃行情抓取異常: {e}")

    # 官方產業代碼中文名稱對照表
    INDUSTRY_CODE_MAP = {
        "01": "水泥", "02": "食品", "03": "塑膠", "04": "紡織",
        "05": "電機機械", "06": "電器電纜", "07": "化學生技", "08": "玻璃陶瓷",
        "09": "造紙", "10": "鋼鐵", "11": "橡膠", "12": "汽車",
        "13": "電子", "14": "建材營造", "15": "航運", "16": "觀光餐旅",
        "17": "金融保險", "18": "貿易百貨", "19": "綜合", "20": "其他",
        "21": "化學", "22": "生技醫療", "23": "油電燃氣", "24": "半導體",
        "25": "電腦周邊", "26": "光電", "27": "通信網路", "28": "電子零組件",
        "29": "電子通路", "30": "資訊服務", "31": "其他電子", "32": "文化創意",
        "33": "農業科技", "34": "電子商務", "35": "綠能環保", "36": "數位雲端",
        "37": "運動休閒", "38": "居家生活"
    }

    industry_dict = {}
    for url in ["https://openapi.twse.com.tw/v1/opendata/t187ap03_L", "https://openapi.twse.com.tw/v1/opendata/t187ap03_O"]:
        try:
            r = requests.get(url, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                for row in r.json():
                    c_code = str(row.get("公司代號", row.get("出表代號", ""))).strip()
                    ind_val = str(row.get("產業別", "")).strip()
                    if ind_val:
                        ind_key = ind_val.zfill(2) if ind_val.isdigit() else ind_val
                        ind_name = INDUSTRY_CODE_MAP.get(ind_key, ind_val.replace("業", ""))
                        industry_dict[c_code] = ind_name
        except Exception:
            pass

    for c, item in stocks.items():
        item['industry'] = industry_dict.get(c, "其他")

    return stocks

# -------------------------------------------------------------------------
# 2. 修復：三大法人日報欄位別名容錯 (確保上櫃法人買賣超成功計入)
# -------------------------------------------------------------------------
def fetch_today_institutional_chips():
    chips_dict = {}
    print("正在抓取證交所三大法人買賣超日報 (T86)...")
    try:
        url = "https://www.twse.com.tw/rwd/zh/fund/T86?response=json&selectType=ALLBUT0999"
        res = requests.get(url, headers=HEADERS, timeout=25)
        if res.status_code == 200:
            data = res.json()
            rows = data.get('data', [])
            for r in rows:
                code = str(r[0]).strip()
                if len(code) != 4 or not code.isdigit():
                    continue
                foreign_net_shares = clean_number(r[4]) if len(r) > 4 else 0
                trust_net_shares = clean_number(r[10]) if len(r) > 10 else 0
                chips_dict[code] = {
                    "foreignNet": int(foreign_net_shares // 1000),
                    "trustNet": int(trust_net_shares // 1000)
                }
    except Exception as e:
        print(f"上市三大法人抓取異常: {e}")

    print("正在抓取櫃買中心三大法人買賣超日報...")
    try:
        url_tpex_inst = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_institutional_investors"
        res = requests.get(url_tpex_inst, headers=HEADERS, timeout=20)
        if res.status_code == 200:
            for item in res.json():
                code = str(item.get("SecuritiesCompanyCode", item.get("Code", ""))).strip()
                if len(code) != 4 or not code.isdigit():
                    continue
                
                # 兼容多種可能的中英文欄位名稱
                foreign_shares = clean_number(
                    item.get("ForeignInvestorsNetBuySell", 
                    item.get("ForeignNetBuySell", 
                    item.get("外資及陸資買賣超股數", 0)))
                )
                trust_shares = clean_number(
                    item.get("InvestmentTrustNetBuySell", 
                    item.get("TrustNetBuySell", 
                    item.get("投信買賣超股數", 0)))
                )
                
                chips_dict[code] = {
                    "foreignNet": int(foreign_shares // 1000),
                    "trustNet": int(trust_shares // 1000)
                }
    except Exception as e:
        print(f"上櫃三大法人抓取異常: {e}")

    return chips_dict
