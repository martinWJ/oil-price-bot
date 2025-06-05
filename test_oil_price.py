import requests
from bs4 import BeautifulSoup
import logging
import re

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_oil_price():
    try:
        url = 'https://www.cpc.com.tw/'
        logger.info(f"開始抓取當前油價，URL: {url}")
        
        # 設定 headers 模擬瀏覽器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        
        # 將回應內容寫入檔案以便檢查
        with open('response.html', 'w', encoding='utf-8') as f:
            f.write(response.text)
        logger.info("已將回應內容寫入 response.html")
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 尋找所有表格
        tables = soup.find_all('table')
        logger.info(f"找到 {len(tables)} 個表格")
        
        # 尋找所有 div
        divs = soup.find_all('div')
        logger.info(f"找到 {len(divs)} 個 div")
        
        # 尋找包含油價相關文字的內容
        oil_price_texts = soup.find_all(string=re.compile(r'92無鉛|95無鉛|98無鉛|超級柴油'))
        logger.info(f"找到 {len(oil_price_texts)} 個包含油價相關文字的內容")
        
        # 輸出找到的油價相關文字
        for text in oil_price_texts:
            logger.info(f"找到油價相關文字: {text}")
            # 輸出父元素的 HTML
            logger.info(f"父元素 HTML: {text.parent}")
            
    except Exception as e:
        logger.error(f"測試時發生錯誤: {str(e)}")

if __name__ == "__main__":
    test_oil_price() 