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

import undetected_chromedriver as uc
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
        
        # 設定 Chrome 選項
        options = uc.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        
        # 初始化 undetected-chromedriver
        driver = uc.Chrome(options=options)
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
                "response_fields": ["is_private_file", "tags"],
                "tags": ["oil-price", "trend"]
            }
        )
        logger.info(f"圖片上傳成功: {response}")
        return response.url
    except Exception as e:
        logger.error(f"上傳圖片到 ImageKit.io 時發生錯誤: {str(e)}")
        return None

@app.route("/", methods=['GET'])
def index():
    return "油價小幫手 LINE Bot 服務正常運作中"

@app.route("/health", methods=['GET'])
def health():
    return "OK"

@app.route("/webhook", methods=['POST'])
def callback():
    # 取得 X-Line-Signature header 值
    signature = request.headers['X-Line-Signature']

    # 取得請求內容
    body = request.get_data(as_text=True)
    logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

def handle_oil_price_query(event):
    """處理油價查詢"""
    price_info = get_oil_price()
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=price_info)
    )

def handle_oil_trend_query(event):
    """處理油價趨勢查詢"""
    # 生成趨勢圖
    trend_image = get_oil_price_trend()
    if trend_image:
        # 上傳到 ImageKit.io
        image_url = upload_image_to_imagekit(trend_image)
        if image_url:
            # 回傳圖片訊息
            line_bot_api.reply_message(
                event.reply_token,
                ImageSendMessage(
                    original_content_url=image_url,
                    preview_image_url=image_url
                )
            )
        else:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="無法上傳趨勢圖，請稍後再試")
            )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="無法生成趨勢圖，請稍後再試")
        )

def handle_oil_history_query(event):
    """處理歷史油價查詢"""
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="歷史油價查詢功能開發中，敬請期待！")
    )

def handle_help_query(event):
    """處理幫助查詢"""
    help_text = "油價小幫手使用說明：\n\n"
    help_text += "1. 輸入「油價」或「查詢油價」：查詢本周最新油價\n"
    help_text += "2. 輸入「趨勢」或「油價趨勢」：查看油價趨勢圖\n"
    help_text += "3. 輸入「幫助」或「說明」：顯示此說明\n"
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=help_text)
    )

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """處理文字訊息"""
    text = event.message.text.lower()
    
    if text in ['油價', '查詢油價']:
        handle_oil_price_query(event)
    elif text in ['趨勢', '油價趨勢']:
        handle_oil_trend_query(event)
    elif text in ['歷史', '歷史油價']:
        handle_oil_history_query(event)
    elif text in ['幫助', '說明', 'help']:
        handle_help_query(event)
    else:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="請輸入「油價」、「趨勢」或「幫助」來使用本服務")
        ) 