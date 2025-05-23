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
from flask import Flask, request, abort, send_from_directory
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

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')

# 設定 LINE Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

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
        # 從中油歷史油價網頁抓取資料
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        logger.info(f"開始抓取油價趨勢資料，URL: {url}")
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers)
        response.encoding = 'utf-8'
        response.raise_for_status() # 檢查 HTTP 請求是否成功
        
        # 使用正則表達式找到油價資料和日期資料
        series_pattern = r'var\s+series\s*=\s*(\[.*?\]);'
        categories_pattern = r'var\s+categories\s*=\s*(\[.*?\]);'
        
        series_match = re.search(series_pattern, response.text, re.DOTALL)
        categories_match = re.search(categories_pattern, response.text, re.DOTALL)
        
        if not series_match or not categories_match:
            logger.error("找不到油價或日期資料")
            return "無法取得油價趨勢資訊"
            
        try:
            series_data = json.loads(series_match.group(1))
            categories_data = json.loads(categories_match.group(1))
            
            if not series_data or not categories_data or len(series_data[0]['data']) != len(categories_data):
                 logger.error("油價或日期資料格式不符或長度不一致")
                 return "油價趨勢資料格式不符，請稍後再試"
                 
            # 使用 matplotlib 繪製趨勢圖
            plt.figure(figsize=(10, 6))
            
            for oil_type_data in series_data:
                oil_type = oil_type_data['name']
                prices = oil_type_data['data']
                plt.plot(categories_data, prices, marker='o', label=oil_type)
                
            plt.xlabel('日期')
            plt.ylabel('價格 (新台幣元/公升)')
            plt.title('中油油價趨勢')
            plt.xticks(rotation=45)
            plt.legend()
            plt.tight_layout()
            
            # 將圖表儲存到一個 BytesIO 物件中 (in-memory)
            from io import BytesIO
            buffer = BytesIO()
            plt.savefig(buffer, format='png')
            buffer.seek(0) # 將指標移回檔案開頭
            
            plt.close() # 關閉圖形以釋放記憶體
            
            # 將圖表儲存到靜態檔案目錄
            image_filename = f'oil_price_trend_{datetime.now().strftime("%Y%m%d%H%M%S")}.png'
            image_path = os.path.join(app.static_folder, image_filename)
            
            # 確保靜態檔案目錄存在
            if not os.path.exists(app.static_folder):
                os.makedirs(app.static_folder)
                
            plt.savefig(image_path)
            logger.info(f"油價趨勢圖表已儲存至 {image_path}")
            
            # 返回圖片檔案名稱，以便後續生成 URL
            return image_filename
            
        except json.JSONDecodeError as e:
            logger.error(f"解析油價或日期資料時發生錯誤: {str(e)}")
            return "Error: 解析油價趨勢資料時發生錯誤，請稍後再試"
        
    except requests.exceptions.RequestException as e:
        logger.error(f"抓取網頁時發生錯誤: {str(e)}")
        return "Error: 抓取油價趨勢時發生網路錯誤，請稍後再試"
    except Exception as e:
        logger.error(f"生成油價趨勢圖表時發生錯誤: {str(e)}")
        return f"Error: 生成油價趨勢圖表時發生錯誤: {str(e)}"

@app.route("/", methods=['GET'])
def index():
    return "油價查詢機器人服務正常運作中"

@app.route("/health", methods=['GET'])
def health():
    return "OK", 200

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

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

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    logger.info(f"收到使用者訊息: {event.message.text}")
    try:
        if event.message.text in ['油價', '查詢油價', '查油價']:
            logger.info("開始獲取油價資訊")
            oil_price_info = get_oil_price()
            logger.info(f"獲取到的油價資訊: {oil_price_info}")
            
            logger.info("準備回覆訊息")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=oil_price_info)
            )
            logger.info("訊息已回覆")
        elif event.message.text in ['油價趨勢', '查詢油價趨勢', '查趨勢']:
            logger.info("開始獲取油價趨勢資訊")
            
            image_filename = get_oil_price_trend()
            
            if image_filename.startswith("Error:"):
                # 如果 get_oil_price_trend 返回錯誤訊息
                reply_message = image_filename.replace("Error: ", "")
                logger.info(f"獲取油價趨勢失敗，回覆文字訊息: {reply_message}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=reply_message)
                )
            else:
                # 如果成功生成圖片，回覆圖片訊息
                # 在 Render 上，你需要設定靜態檔案服務的 URL
                # 這裡先使用一個佔位符 URL
                # TODO: 替換為實際的靜態檔案 URL 前綴
                base_url = os.getenv('RENDER_STATIC_URL', 'YOUR_RENDER_STATIC_URL_HERE') 
                image_url = f'{base_url}/static/{image_filename}'
                
                logger.info(f"準備回覆油價趨勢圖表: {image_url}")
                line_bot_api.reply_message(
                    event.reply_token,
                    ImageSendMessage(original_content_url=image_url, preview_image_url=image_url)
                )
                logger.info("油價趨勢圖表訊息已回覆")
            
        else:
            logger.info(f"收到未處理的訊息: {event.message.text}")
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
