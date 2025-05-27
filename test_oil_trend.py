"""
測試油價趨勢圖表功能
"""

import os
import logging
import requests
from bs4 import BeautifulSoup
import matplotlib
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import time

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

matplotlib.rc('font', family='Microsoft JhengHei')
matplotlib.rc('axes', unicode_minus=False)

def get_oil_price_trend():
    try:
        # 從中油歷史油價網頁抓取資料
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        logger.info(f"開始抓取油價趨勢資料，URL: {url}")
        
        # 設定 Chrome 選項
        chrome_options = Options()
        chrome_options.add_argument('--headless')  # 無頭模式
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36')
        
        # 設定 ChromeDriver 路徑
        chromedriver_path = os.path.join(os.path.dirname(__file__), 'chromedriver.exe')
        logger.info(f"ChromeDriver 路徑: {chromedriver_path}")
        
        # 初始化 WebDriver
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("已初始化 Chrome WebDriver")
        
        try:
            # 開啟網頁
            driver.get(url)
            logger.info("已開啟網頁")
            
            # 等待表格載入
            wait = WebDriverWait(driver, 10)
            table = wait.until(EC.presence_of_element_located((By.ID, 'tbHistoryPrice')))
            logger.info("表格已載入")
            
            # 等待一下確保資料完全載入
            time.sleep(2)
            
            # 取得網頁內容
            html = driver.page_source
            
            # 儲存網頁內容以供檢查
            with open('oil_price_page_selenium.html', 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info("已儲存網頁內容到 oil_price_page_selenium.html")
            
            # 使用 BeautifulSoup 解析網頁
            soup = BeautifulSoup(html, 'html.parser')
            
            # 找到包含油價資料的表格
            table = soup.find('table', {'id': 'tbHistoryPrice'})
            if not table:
                logger.error("找不到油價資料表格")
                return None
                
            # 直接從 tbody 中獲取資料
            tbody = table.find('tbody')
            if not tbody:
                logger.error("找不到 tbody")
                return None
                
            rows = tbody.find_all('tr')
            logger.info(f"找到 {len(rows)} 列資料")
            
            dates = []
            prices_92 = []
            prices_95 = []
            prices_98 = []
            prices_diesel = []
            
            for i, row in enumerate(rows):
                cols = row.find_all('td')
                logger.info(f"第 {i+1} 列有 {len(cols)} 個欄位")
                
                if len(cols) >= 5:
                    try:
                        date = cols[0].text.strip()
                        price_92 = float(cols[1].text.strip())
                        price_95 = float(cols[2].text.strip())
                        price_98 = float(cols[3].text.strip())
                        price_diesel = float(cols[4].text.strip())
                        
                        logger.info(f"解析第 {i+1} 列資料: 日期={date}, 92={price_92}, 95={price_95}, 98={price_98}, 柴油={price_diesel}")
                        
                        dates.append(date)
                        prices_92.append(price_92)
                        prices_95.append(price_95)
                        prices_98.append(price_98)
                        prices_diesel.append(price_diesel)
                    except (ValueError, IndexError) as e:
                        logger.error(f"解析第 {i+1} 列資料時發生錯誤: {str(e)}")
                        logger.error(f"該列內容: {[col.text.strip() for col in cols]}")
                        continue
            
            if not dates:
                logger.error("無法解析油價資料")
                return None
                
            logger.info(f"成功解析油價資料，共 {len(dates)} 筆")
            logger.info(f"日期資料: {dates}")
            logger.info(f"92無鉛汽油價格: {prices_92}")
            
            # 反轉資料順序，讓X軸最左側為最舊日期
            dates = dates[::-1]
            prices_92 = prices_92[::-1]
            prices_95 = prices_95[::-1]
            prices_98 = prices_98[::-1]
            prices_diesel = prices_diesel[::-1]

            # 使用 matplotlib 繪製趨勢圖
            plt.figure(figsize=(10, 6))
            
            plt.plot(dates, prices_92, marker='o', label='92無鉛汽油')
            plt.plot(dates, prices_95, marker='o', label='95無鉛汽油')
            plt.plot(dates, prices_98, marker='o', label='98無鉛汽油')
            plt.plot(dates, prices_diesel, marker='o', label='超級柴油')
            
            # 在每個點上標註數值
            for x, y in zip(dates, prices_92):
                plt.text(x, y, f"{y}", ha='center', va='bottom', fontsize=10)
            for x, y in zip(dates, prices_95):
                plt.text(x, y, f"{y}", ha='center', va='bottom', fontsize=10)
            for x, y in zip(dates, prices_98):
                plt.text(x, y, f"{y}", ha='center', va='bottom', fontsize=10)
            for x, y in zip(dates, prices_diesel):
                plt.text(x, y, f"{y}", ha='center', va='bottom', fontsize=10)
            
            plt.xlabel('日期')
            plt.ylabel('價格 (新台幣元/公升)')
            plt.title('中油油價趨勢')
            plt.xticks(rotation=45)
            plt.legend()
            plt.grid(True)
            plt.tight_layout()
            
            # 將圖表儲存到檔案
            output_file = f'oil_price_trend_{datetime.now().strftime("%Y%m%d%H%M%S")}.png'
            plt.savefig(output_file, format='png', dpi=300, bbox_inches='tight')
            plt.close()
            
            logger.info(f"油價趨勢圖表已儲存到 {output_file}")
            return output_file
            
        finally:
            # 關閉瀏覽器
            driver.quit()
            logger.info("已關閉 Chrome WebDriver")
            
    except Exception as e:
        logger.error(f"生成油價趨勢圖表時發生錯誤: {str(e)}")
        return None

if __name__ == "__main__":
    result = get_oil_price_trend()
    if result:
        logger.info(f"測試成功，圖表已儲存為: {result}")
    else:
        logger.error("測試失敗") 