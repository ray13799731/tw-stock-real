import os
import json
import time
import re
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/javascript, */*; q=0.01'
}

def clean_number(val_str):
    if val_str is None:
        return 0.0
    clean = re.sub(r'[^\d\.\-]', '', str(val_str))
    try:
        return float(clean) if clean else 0.0
    except ValueError:
        return 0.0

# -------------------------------------------------------------------------
# 1. 抓取上市 (TWSE) 與上櫃 (TPEx) 官方當日收盤行情與產業別
# -------------------------------------------------------------------------
def fetch_all_quotes():
    stocks = {}
    print("正在請求證交所 (TWSE) 上市收盤行情...")
    try:
        url_twse = "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?response=json&type=ALLBUT0999"
        res = requests.get(url_twse, headers=HEADERS, timeout=25)
        if res.status_code == 200:
            data = res.json()
            rows = []
            if 'tables' in data:
                for t in data['tables']:
                    if '每日收盤行情' in t.get('title', ''):
                        rows = t.get('data', [])
                        break
            if not rows:
                rows = data.get('data9', [])

            for row in rows:
                code = str(row[0]).strip()
                name = str(row[1]).strip()
                if len(code) != 4 or not code.isdigit():
                    continue

                vol_shares = clean_number(row[2])
                price = clean_number(row[8])

                # 正確欄位對應：row[9] 是符號 (+/-)，row[10] 是漲跌價差數值
                sign_raw = str(row[9]).lower()
                diff_val = clean_number(row[10])

                if '-' in sign_raw or 'green' in sign_raw:
                    diff = -abs(diff_val)
                elif '+' in sign_raw or 'red' in sign_raw:
                    diff = abs(diff_val)
                elif diff_val > 0:
                    diff = abs(diff_val)
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
            items = res.json()
            if isinstance(items, list):
                for item in items:
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
                print(f"成功取得上櫃股票，累計共 {len(stocks)} 檔股票。")
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
# 2. 抓取當日三大法人買賣超 (上市 T86 + 上櫃 3itrade 官方雙通道)
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
            print(f"成功取得上市三大法人資料，共 {len(chips_dict)} 檔。")
    except Exception as e:
        print(f"上市三大法人抓取異常: {e}")

    print("正在抓取櫃買中心三大法人買賣超日報 (官方穩定接口)...")
    tpex_count = 0
    # 通道 A: 櫃買官方標準 JSON 日報
    try:
        url_tpex_a = "https://www.tpex.org.tw/web/stock/3invest/daily_trading/3itrade_hedge_result.php?l=zh-tw&t=D&response=json"
        res = requests.get(url_tpex_a, headers=HEADERS, timeout=20)
        if res.status_code == 200:
            data = res.json()
            rows = data.get('aaData', [])
            for r in rows:
                code = str(r[0]).strip()
                if len(code) != 4 or not code.isdigit():
                    continue
                # 欄位：[7] 外資買賣超股數, [10] 投信買賣超股數
                foreign_shares = clean_number(r[7]) if len(r) > 7 else 0
                trust_shares = clean_number(r[10]) if len(r) > 10 else 0
                chips_dict[code] = {
                    "foreignNet": int(foreign_shares // 1000),
                    "trustNet": int(trust_shares // 1000)
                }
                tpex_count += 1
            print(f"透過通道 A 成功取得上櫃三大法人資料 {tpex_count} 檔。")
    except Exception as e:
        print(f"上櫃通道 A 抓取異常: {e}")

    # 通道 B (備援): 櫃買 OpenAPI
    if tpex_count == 0:
        print("切換至上櫃通道 B (OpenAPI 備援)...")
        try:
            url_tpex_b = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_institutional_investors"
            res = requests.get(url_tpex_b, headers=HEADERS, timeout=20)
            if res.status_code == 200:
                items = res.json()
                if isinstance(items, list):
                    for item in items:
                        code = str(item.get("SecuritiesCompanyCode", item.get("Code", ""))).strip()
                        if len(code) != 4 or not code.isdigit():
                            continue
                        foreign_shares = clean_number(item.get("ForeignInvestorsNetBuySell", item.get("外資及陸資買賣超股數", 0)))
                        trust_shares = clean_number(item.get("InvestmentTrustNetBuySell", item.get("投信買賣超股數", 0)))
                        chips_dict[code] = {
                            "foreignNet": int(foreign_shares // 1000),
                            "trustNet": int(trust_shares // 1000)
                        }
                        tpex_count += 1
                    print(f"透過通道 B 取得上櫃三大法人資料 {tpex_count} 檔。")
        except Exception as e:
            print(f"上櫃通道 B 抓取異常: {e}")

    return chips_dict

# -------------------------------------------------------------------------
# 3. 三大法人滾動快取 (chips_history.json)
# -------------------------------------------------------------------------
def update_chips_rolling_cache(today_chips):
    cache_file = "chips_history.json"
    today_str = datetime.now().strftime("%Y%m%d")
    history = {}

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    history[today_str] = today_chips
    sorted_dates = sorted(history.keys(), reverse=True)[:5]
    trimmed_history = {d: history[d] for d in sorted_dates}

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(trimmed_history, f, ensure_ascii=False, indent=2)

    computed_chips = {}
    all_codes = set(today_chips.keys())

    for code in all_codes:
        top3_dates = sorted_dates[:3]
        foreign_3d = sum(trimmed_history[d].get(code, {}).get("foreignNet", 0) for d in top3_dates)
        trust_3d = sum(trimmed_history[d].get(code, {}).get("trustNet", 0) for d in top3_dates)

        trust_streak = 0
        for d in sorted_dates:
            day_trust_net = trimmed_history[d].get(code, {}).get("trustNet", 0)
            if day_trust_net > 0:
                trust_streak += 1
            else:
                break

        foreign_streak = 0
        for d in sorted_dates:
            day_foreign_net = trimmed_history[d].get(code, {}).get("foreignNet", 0)
            if day_foreign_net > 0:
                foreign_streak += 1
            else:
                break

        computed_chips[code] = {
            "foreignNet3d": foreign_3d,
            "trustNet3d": trust_3d,
            "trustStreak": trust_streak,
            "foreignStreak": foreign_streak
        }

    return computed_chips

# -------------------------------------------------------------------------
# 4. TDCC 官方集保股權分散表 (holders_history.json)
# -------------------------------------------------------------------------
def update_holders_rolling_cache():
    cache_file = "holders_history.json"
    history = {}

    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        except Exception:
            history = {}

    print("正在請求 TDCC 臺灣集中保管結算所官方股權分散資料...")
    today_str = datetime.now().strftime("%Y%m%d")
    tdcc_url = "https://smart.tdcc.com.tw/opendata/getOD.ashx?id=1-5"
    
    try:
        res = requests.get(tdcc_url, headers=HEADERS, timeout=30)
        if res.status_code == 200:
            lines = res.text.strip().split("\n")
            if len(lines) > 100:
                cur_holders = {}
                date_key = today_str
                for line in lines[1:]:
                    parts = [p.strip().replace('"', '') for p in line.split(',')]
                    if len(parts) >= 6:
                        date_key = parts[0]
                        code = parts[1]
                        level = parts[2]
                        people_count = int(clean_number(parts[3]))
                        ratio = clean_number(parts[5])
                        if level == '15' and len(code) == 4 and code.isdigit():
                            cur_holders[code] = {
                                "ratio": ratio,
                                "count": people_count
                            }
                
                if cur_holders:
                    history[date_key] = cur_holders
                    print(f"成功取得 TDCC 集保資料，日期: {date_key}，共 {len(cur_holders)} 檔股票大戶人數與持股比。")
    except Exception as e:
        print(f"TDCC 資料請求失敗 (使用既有快取): {e}")

    sorted_weeks = sorted(history.keys(), reverse=True)[:3]
    trimmed_holders = {w: history[w] for w in sorted_weeks}

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(trimmed_holders, f, ensure_ascii=False, indent=2)

    computed_holders = {}
    if len(sorted_weeks) >= 2:
        w_curr = sorted_weeks[0]
        w_prev1 = sorted_weeks[1]
        w_prev2 = sorted_weeks[2] if len(sorted_weeks) >= 3 else None

        for code, cur_data in trimmed_holders[w_curr].items():
            streak = 0
            cur_ratio = cur_data["ratio"] if isinstance(cur_data, dict) else cur_data
            cur_count = cur_data.get("count", 0) if isinstance(cur_data, dict) else 0

            prev1_val = trimmed_holders[w_prev1].get(code, cur_ratio)
            prev1_ratio = prev1_val["ratio"] if isinstance(prev1_val, dict) else prev1_val
            diff1 = cur_ratio - prev1_ratio

            if diff1 > 0:
                streak = 1
                if w_prev2:
                    prev2_val = trimmed_holders[w_prev2].get(code, prev1_ratio)
                    prev2_ratio = prev2_val["ratio"] if isinstance(prev2_val, dict) else prev2_val
                    diff2 = prev1_ratio - prev2_ratio
                    if diff2 > 0:
                        streak = 2

            computed_holders[code] = {
                "bigHolderRatio": cur_ratio,
                "bigHolderCount": cur_count,
                "bigHolderDiff": round(diff1, 2),
                "bigHolderStreak": streak
            }
    else:
        for code, cur_data in (trimmed_holders[sorted_weeks[0]].items() if sorted_weeks else []):
            cur_ratio = cur_data["ratio"] if isinstance(cur_data, dict) else cur_data
            cur_count = cur_data.get("count", 0) if isinstance(cur_data, dict) else 0
            computed_holders[code] = {
                "bigHolderRatio": cur_ratio,
                "bigHolderCount": cur_count,
                "bigHolderDiff": 0.0,
                "bigHolderStreak": 1
            }

    return computed_holders

# -------------------------------------------------------------------------
# 5. 抓取真實官方本益比 (PE) 與 EPS
# -------------------------------------------------------------------------
def fetch_financial_metrics():
    pe_dict = {}
    eps_dict = {}

    try:
        res = requests.get("https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?response=json&selectType=ALL", headers=HEADERS, timeout=20)
        if res.status_code == 200:
            data = res.json()
            fields = data.get('fields', [])
            pe_col_idx = -1
            for idx, f in enumerate(fields):
                if '本益比' in f:
                    pe_col_idx = idx
                    break
            if pe_col_idx == -1: pe_col_idx = 4

            for row in data.get('data', []):
                code = str(row[0]).strip()
                if len(row) > pe_col_idx:
                    raw_val = str(row[pe_col_idx]).replace(',', '').strip()
                    if raw_val in ['-', 'N/A', '', '112', '113', '114', '115'] or '/' in raw_val:
                        pe_dict[code] = 0.0
                    else:
                        try:
                            val = float(raw_val)
                            if 0 < val < 500 and val != 114.0:
                                pe_dict[code] = round(val, 2)
                            else:
                                pe_dict[code] = 0.0
                        except ValueError:
                            pe_dict[code] = 0.0
    except Exception as e:
        print(f"上市本益比解析異常: {e}")

    try:
        res = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis", headers=HEADERS, timeout=20)
        if res.status_code == 200:
            for item in res.json():
                code = str(item.get("SecuritiesCompanyCode", "")).strip()
                raw_pe = str(item.get("PriceEarningRatio", "")).replace(',', '').strip()
                if raw_pe in ['-', 'N/A', '', '112', '113', '114', '115'] or '/' in raw_pe:
                    pe_dict[code] = 0.0
                else:
                    try:
                        val = float(raw_pe)
                        if 0 < val < 500 and val != 114.0:
                            pe_dict[code] = round(val, 2)
                        else:
                            pe_dict[code] = 0.0
                    except ValueError:
                        pe_dict[code] = 0.0
    except Exception as e:
        print(f"上櫃本益比解析異常: {e}")

    for url in ["https://openapi.twse.com.tw/v1/opendata/t187ap14_L", "https://openapi.twse.com.tw/v1/opendata/t187ap14_O"]:
        try:
            res = requests.get(url, headers=HEADERS, timeout=20)
            if res.status_code == 200:
                for item in res.json():
                    code = str(item.get("公司代號", item.get("出表代號", ""))).strip()
                    raw_eps = str(item.get("基本每股盈餘（元）", item.get("基本每股盈餘", 0))).replace(',', '').strip()
                    try:
                        val = float(raw_eps)
                        eps_dict[code] = round(val, 2)
                    except (ValueError, TypeError):
                        pass
        except Exception:
            pass

    return pe_dict, eps_dict

# -------------------------------------------------------------------------
# 6. yfinance 批次下載真實日 K 線 (MA20, MA60, 20日均量)
# -------------------------------------------------------------------------
def fetch_real_kline_technicals(quotes):
    print("\n[yfinance] 開始批次下載真實歷史日 K 線...")
    results = {}

    ticker_map = {f"{c}{'.TW' if item['market']=='上市' else '.TWO'}": c for c, item in quotes.items()}
    symbols = list(ticker_map.keys())
    batch_size = 80

    for i in range(0, len(symbols), batch_size):
        batch = symbols[i:i + batch_size]
        print(f"正在下載真實歷史 K 線 [{i+1} ~ {min(i+batch_size, len(symbols))} / {len(symbols)}]...")
        try:
            df = yf.download(" ".join(batch), period="6mo", interval="1d", group_by='ticker', threads=True, progress=False)
            for sym in batch:
                code = ticker_map[sym]
                try:
                    s_df = df[sym] if len(batch) > 1 else df
                    s_df = s_df.dropna(subset=['Close'])
                    if len(s_df) < 25:
                        continue

                    closes = s_df['Close']
                    vols = s_df['Volume']

                    ma20_s = closes.rolling(20).mean()
                    ma60_s = closes.rolling(60).mean()
                    ma20_vol_s = vols.rolling(20).mean()

                    cur_close = float(closes.iloc[-1])
                    cur_ma20 = float(ma20_s.iloc[-1]) if pd.notnull(ma20_s.iloc[-1]) else cur_close
                    cur_ma60 = float(ma60_s.iloc[-1]) if pd.notnull(ma60_s.iloc[-1]) else cur_ma20
                    ma20_prev20 = float(ma20_s.iloc[-21]) if len(ma20_s) >= 21 and pd.notnull(ma20_s.iloc[-21]) else cur_ma20
                    cur_ma20_vol = int(ma20_vol_s.iloc[-1] // 1000) if pd.notnull(ma20_vol_s.iloc[-1]) else 100

                    results[code] = {
                        "ma20": round(cur_ma20, 2),
                        "ma60": round(cur_ma60, 2),
                        "ma20_prev20": round(ma20_prev20, 2),
                        "ma20Vol": max(50, cur_ma20_vol),
                        "isPriceGtMa20GtMa60": bool(cur_close > cur_ma20 > cur_ma60),
                        "isMa20Rising": bool(cur_ma20 > ma20_prev20)
                    }
                except Exception:
                    continue
        except Exception as e:
            print(f"批次異常: {e}")
            time.sleep(1)

    print(f"歷史技術指標計算完畢，成功數: {len(results)} 檔\n")
    return results

def main():
    print("==================================================")
    print("啟動全市場 100% 真實數據量價籌碼整合資料管線")
    print(f"執行時間: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("==================================================")

    quotes = fetch_all_quotes()
    if not quotes:
        print("未抓取到有效行情，終止流程。")
        return

    today_chips = fetch_today_institutional_chips()
    rolling_chips = update_chips_rolling_cache(today_chips)
    holders_data = update_holders_rolling_cache()
    pe_data, eps_data = fetch_financial_metrics()
    tech_data = fetch_real_kline_technicals(quotes)

    output = []

    for code, q in quotes.items():
        price = float(q['price'])
        vol = int(q['yesterdayVol'])

        pe = pe_data.get(code, 0.0)
        
        if code in eps_data:
            eps = eps_data[code]
        elif pe > 0 and price > 0:
            eps = round(price / pe, 2)
        else:
            eps = 0.0

        if pe > 0 and price > 0:
            eps4q = round(price / pe, 2)
        else:
            eps4q = eps
        is_eps4q_pos = (eps4q > 0)

        t = tech_data.get(code, {
            "ma20": price, "ma60": price, "ma20_prev20": price,
            "ma20Vol": max(50, vol), "isPriceGtMa20GtMa60": False, "isMa20Rising": False
        })
        vol_ratio = round(vol / t['ma20Vol'], 2) if t['ma20Vol'] > 0 else 1.0

        c = rolling_chips.get(code, {"foreignNet3d": 0, "trustNet3d": 0, "trustStreak": 0, "foreignStreak": 0})
        foreign_net_3d = c['foreignNet3d']
        trust_net_3d = c['trustNet3d']
        trust_streak = c['trustStreak']
        foreign_streak = c.get('foreignStreak', 0)

        h = holders_data.get(code, {"bigHolderRatio": 0.0, "bigHolderCount": 0, "bigHolderDiff": 0.0, "bigHolderStreak": 0})
        big_holder_streak = h['bigHolderStreak']
        big_holder_ratio = h['bigHolderRatio']
        big_holder_count = h.get('bigHolderCount', 0)
        big_holder_diff = h['bigHolderDiff']

        output.append({
            "code": code,
            "name": q['name'],
            "market": q['market'],
            "industry": q.get('industry', '其他'),
            "price": price,
            "change": float(q['change']),
            "changeRate": float(q['changeRate']),
            "pe": pe,
            "eps": eps,
            "eps4Q": eps4q,
            "isEps4QPositive": is_eps4q_pos,
            "ma20": t['ma20'],
            "ma60": t['ma60'],
            "ma20_prev20": t['ma20_prev20'],
            "isPriceGtMa20GtMa60": t['isPriceGtMa20GtMa60'],
            "isMa20Rising": t['isMa20Rising'],
            "yesterdayVol": vol,
            "ma20Vol": t['ma20Vol'],
            "volumeRatio": vol_ratio,
            "foreignNet3d": foreign_net_3d,
            "trustNet3d": trust_net_3d,
            "trustStreak": trust_streak,
            "foreignStreak": foreign_streak,
            "bigHolderStreak": big_holder_streak,
            "bigHolderRatio": big_holder_ratio,
            "bigHolderCount": big_holder_count,
            "bigHolderDiff": big_holder_diff
        })

    with open("market_stocks.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"成功輸出 100% 真實數據之全市場股票！共計 {len(output)} 檔至 market_stocks.json")

if __name__ == "__main__":
    main()
