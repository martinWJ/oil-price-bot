import requests
from bs4 import BeautifulSoup
import logging
import re
import json

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_oil_price():
    try:
        # 從中油歷史油價網頁抓取資料
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        logger.info(f"開始抓取油價資料，URL: {url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8'
        logger.info(f"網頁回應狀態碼: {response.status_code}")
        
        # 儲存網頁內容以供檢查
        with open('response.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        logger.info("已儲存網頁內容到 response.html")
        
        # 使用正則表達式找到油價資料
        series_pattern = r'var\s+series\s*=\s*(\[.*?\]);'
        series_match = re.search(series_pattern, response.text, re.DOTALL)
        
        if not series_match:
            logger.error("找不到油價資料")
            return "無法取得油價資訊"
            
        try:
            series_data = json.loads(series_match.group(1))
            logger.info(f"成功解析油價資料: {series_data}")
            
            # 取得最新一筆資料
            latest_data = {
                '92無鉛汽油': series_data[0]['data'][0],
                '95無鉛汽油': series_data[1]['data'][0],
                '98無鉛汽油': series_data[2]['data'][0],
                '超級柴油': series_data[3]['data'][0]
            }
            
            # 組合回覆訊息
            message = "中油最新油價資訊:\n"
            message += f"92無鉛汽油: {latest_data['92無鉛汽油']} 元/公升\n"
            message += f"95無鉛汽油: {latest_data['95無鉛汽油']} 元/公升\n"
            message += f"98無鉛汽油: {latest_data['98無鉛汽油']} 元/公升\n"
            message += f"超級柴油: {latest_data['超級柴油']} 元/公升"
            
            logger.info(f"成功取得油價資訊: {message}")
            return message
            
        except json.JSONDecodeError as e:
            logger.error(f"解析油價資料時發生錯誤: {str(e)}")
            return "解析油價資料時發生錯誤，請稍後再試"
        
    except Exception as e:
        logger.error(f"抓取油價時發生錯誤: {str(e)}")
        return "抓取油價時發生錯誤，請稍後再試"

if __name__ == "__main__":
    result = get_oil_price()
    print("\n最終結果:")
    print(result) 