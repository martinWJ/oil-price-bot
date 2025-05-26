"""
LINE Bot 油價小幫手 V1.0.0

功能：
1. 查詢本周油價資訊
2. 顯示油價趨勢圖表
3. 支援 92、95、98 無鉛汽油和超級柴油價格查詢

版本規劃：
V1 - 基礎查詢功能（當前版本）
V2 - 歷史查詢功能
V3 - 自動推播功能
V4 - 預測分析功能

作者：martinWJ
"""

import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import json
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO
# import base64 # 不再需要 base64

# Import ImageKit SDK
from imagekitio import ImageKit

import matplotlib
matplotlib.rc('font', family='Microsoft JhengHei')
matplotlib.rc('axes', unicode_minus=False)

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

app = Flask(__name__)

# 設定 LINE Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# Imgur 相關配置 (移除)
# IMGUR_CLIENT_ID = os.getenv('IMGUR_CLIENT_ID')

# ImageKit.io 相關配置
IMAGEKIT_PUBLIC_KEY = os.getenv('IMAGEKIT_PUBLIC_KEY')
IMAGEKIT_PRIVATE_KEY = os.getenv('IMAGEKIT_PRIVATE_KEY')
IMAGEKIT_URL_ENDPOINT = os.getenv('IMAGEKIT_URL_ENDPOINT')

# 初始化 ImageKit
imagekit = ImageKit(public_key=IMAGEKIT_PUBLIC_KEY, private_key=IMAGEKIT_PRIVATE_KEY, url_endpoint=IMAGEKIT_URL_ENDPOINT)

def get_current_week_dates():
    today = datetime.now()
    # 計算本周的開始（週一）和結束（週日）
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week.strftime('%m/%d'), end_of_week.strftime('%m/%d')

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
            
            # 取得本周日期範圍
            start_date, end_date = get_current_week_dates()
            
            # 組合回覆訊息
            message = f"本周{start_date}~{end_date}中油最新油價資訊:\n"
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

def get_oil_price_trend():
    try:
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        logger.info(f"開始抓取油價趨勢資料，URL: {url}")
        chrome_options = Options()
        chrome_options.add_argument('--headless')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36')
        chromedriver_path = os.path.join(os.path.dirname(__file__), 'chromedriver.exe')
        logger.info(f"ChromeDriver 路徑: {chromedriver_path}")
        service = Service(executable_path=chromedriver_path)
        driver = webdriver.Chrome(service=service, options=chrome_options)
        logger.info("已初始化 Chrome WebDriver")
        try:
            driver.get(url)
            logger.info("已開啟網頁")
            wait = WebDriverWait(driver, 10)
            table = wait.until(EC.presence_of_element_located((By.ID, 'tbHistoryPrice')))
            logger.info("表格已載入")
            time.sleep(2)
            html = driver.page_source
            soup = BeautifulSoup(html, 'html.parser')
            table = soup.find('table', {'id': 'tbHistoryPrice'})
            if not table:
                logger.error("找不到油價資料表格")
                return None
            tbody = table.find('tbody')
            if not tbody:
                logger.error("找不到 tbody")
                return None
            rows = tbody.find_all('tr')
            logger.info(f"找到 {len(rows)} 列資料")
            dates, prices_92, prices_95, prices_98, prices_diesel = [], [], [], [], []
            for i, row in enumerate(rows):
                cols = row.find_all('td')
                if len(cols) >= 5:
                    try:
                        date = cols[0].text.strip()
                        price_92 = float(cols[1].text.strip())
                        price_95 = float(cols[2].text.strip())
                        price_98 = float(cols[3].text.strip())
                        price_diesel = float(cols[4].text.strip())
                        dates.append(date)
                        prices_92.append(price_92)
                        prices_95.append(price_95)
                        prices_98.append(price_98)
                        prices_diesel.append(price_diesel)
                    except Exception as e:
                        logger.error(f"解析第 {i+1} 列資料時發生錯誤: {e}")
            if not dates:
                logger.error("無法解析油價資料")
                return None
            # 反轉資料順序，讓X軸最左側為最舊日期
            dates = dates[::-1]
            prices_92 = prices_92[::-1]
            prices_95 = prices_95[::-1]
            prices_98 = prices_98[::-1]
            prices_diesel = prices_diesel[::-1]
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
            buffer = BytesIO()
            plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
            buffer.seek(0)
            plt.close()
            logger.info("油價趨勢圖表已生成到記憶體")
            return buffer
        finally:
            driver.quit()
            logger.info("已關閉 Chrome WebDriver")
    except Exception as e:
        logger.error(f"生成油價趨勢圖表時發生錯誤: {str(e)}")
        return None

def upload_image_to_imagekit(image_buffer):
    """將圖片上傳到 ImageKit.io 並返回圖片 URL"""
    if not IMAGEKIT_PUBLIC_KEY or not IMAGEKIT_PRIVATE_KEY or not IMAGEKIT_URL_ENDPOINT:
        logger.error("ImageKit.io 環境變數未設定")
        return None

    try:
        # 檢查 image_buffer 是否為 BytesIO 物件
        if not isinstance(image_buffer, BytesIO):
            logger.error(f"image_buffer 類型錯誤: {type(image_buffer)}")
            return None

        # 檢查 image_buffer 是否有內容
        if image_buffer.getbuffer().nbytes == 0:
            logger.error("image_buffer 是空的")
            return None

        # 生成檔案名稱
        file_name = f'oil_price_trend_{datetime.now().strftime("%Y%m%d%H%M%S")}.png'
        logger.info(f"準備上傳檔案: {file_name}")

        # ImageKit.io SDK 上傳檔案
        response = imagekit.upload_file(
            file=image_buffer,
            file_name=file_name,
            options={
                "response_fields": ["url"],
                "use_unique_file_name": True
            }
        )

        logger.info(f"ImageKit.io 回應: {response}")

        if response and response.get('success'):
            image_url = response.get('url')
            logger.info(f"圖片成功上傳到 ImageKit.io: {image_url}")
            return image_url
        else:
            error_message = response.get('error', '未知錯誤') if response else '無回應'
            logger.error(f"圖片上傳到 ImageKit.io 失敗: {error_message}")
            return None

    except Exception as e:
        logger.error(f"上傳圖片到 ImageKit.io 時發生錯誤: {str(e)}")
        return None

@app.route("/", methods=['GET'])
def index():
    return "油價查詢機器人服務正常運作中"

@app.route("/health", methods=['GET'])
def health():
    return "OK", 200

@app.route("/webhook", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    logger.info("收到 LINE 訊息")
    logger.info(f"Request body: {body}")
    
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature. Please check your channel access token/channel secret.")
        abort(400)
    except Exception as e:
        logger.error(f"處理訊息時發生錯誤: {str(e)}")
        abort(500)
    return 'OK', 200

def handle_oil_price_query(event):
    logger.info("開始獲取油價資訊")
    oil_price_info = get_oil_price()
    logger.info(f"獲取到的油價資訊: {oil_price_info}")

    logger.info("準備回覆訊息")
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=oil_price_info)
    )
    logger.info("訊息已回覆")

def handle_oil_trend_query(event):
    logger.info("開始獲取油價趨勢資訊並生成圖表")

    result = get_oil_price_trend()

    if isinstance(result, str) and result.startswith("Error:"):
        # 如果 get_oil_price_trend 返回錯誤訊息
        reply_message = result.replace("Error: ", "")
        logger.info(f"獲取油價趨勢失敗，回覆文字訊息: {reply_message}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_message)
        )
    elif isinstance(result, BytesIO):
        # 如果成功生成圖片緩衝區，則上傳到 ImageKit.io
        logger.info("準備上傳油價趨勢圖表到 ImageKit.io")
        image_url = upload_image_to_imagekit(result)

        if image_url:
            # 如果成功上傳並取得 URL，回覆圖片訊息
            logger.info(f"準備回覆油價趨勢圖表 (ImageKit.io URL): {image_url}")
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(original_content_url=image_url, preview_image_url=image_url)
            )
            logger.info("油價趨勢圖表訊息已回覆")
        else:
            # 如果上傳失敗
            logger.error("上傳油價趨勢圖表到 ImageKit.io 失敗")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="無法上傳油價趨勢圖表，請稍後再試")
            )
    else:
        # 如果生成圖表失敗 (但沒有返回錯誤字串)
        logger.error(f"生成油價趨勢圖表失敗，返回類型: {type(result)}")
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="生成油價趨勢圖表失敗，請稍後再試")
        )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    logger.info(f"收到使用者訊息: {event.message.text}")
    try:
        user_message_text = event.message.text

        # 處理文字訊息
        if user_message_text == "查油價":
            handle_oil_price_query(event)
        elif user_message_text == "查趨勢":
            handle_oil_trend_query(event)
        elif user_message_text == "查歷史":
            handle_oil_history_query(event)
        elif user_message_text == "查說明":
            handle_help_query(event)
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="請輸入「查油價」、「查趨勢」、「查歷史」或「查說明」")
            )

    except Exception as e:
        logger.error(f"處理訊息時發生錯誤: {str(e)}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="處理訊息時發生錯誤，請稍後再試")
            )
        except Exception as reply_error:
            logger.error(f"回覆錯誤訊息時發生錯誤: {str(reply_error)}")

if __name__ == "__main__":
    port = int(os.getenv('PORT', 5000))
    logger.info(f"服務啟動於 port {port}")
    app.run(host='0.0.0.0', port=port)
