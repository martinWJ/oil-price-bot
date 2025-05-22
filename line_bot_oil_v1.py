import os
import logging
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import re
import json

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# 設定 LINE Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

def get_current_week_dates():
    today = datetime.now()
    # 計算本周的開始（週日）和結束（週六）
    start_of_week = today - timedelta(days=today.weekday() + 1)
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
        
        # 使用正則表達式找到油價資料
        series_pattern = r'var\s+series\s*=\s*(\[.*?\]);'
        series_match = re.search(series_pattern, response.text, re.DOTALL)
        
        if not series_match:
            logger.error("找不到油價趨勢資料")
            return "無法取得油價趨勢資訊"
            
        try:
            series_data = json.loads(series_match.group(1))
            
            # 取得最近7天的油價資料
            trend_data = {
                '92無鉛汽油': series_data[0]['data'],
                '95無鉛汽油': series_data[1]['data'],
                '98無鉛汽油': series_data[2]['data'],
                '超級柴油': series_data[3]['data']
            }
            
            # 組合趨勢訊息
            message = "最近7天油價趨勢:\n"
            for oil_type, prices in trend_data.items():
                message += f"\n{oil_type}:\n"
                for i, price in enumerate(prices):
                    message += f"第{i+1}天: {price} 元/公升\n"
            
            logger.info("成功取得油價趨勢資訊")
            return message
            
        except json.JSONDecodeError as e:
            logger.error(f"解析油價趨勢資料時發生錯誤: {str(e)}")
            return "解析油價趨勢資料時發生錯誤，請稍後再試"
        
    except Exception as e:
        logger.error(f"抓取油價趨勢時發生錯誤: {str(e)}")
        return "抓取油價趨勢時發生錯誤，請稍後再試"

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
            trend_info = get_oil_price_trend()
            logger.info(f"獲取到的油價趨勢資訊: {trend_info}")
            
            logger.info("準備回覆趨勢訊息")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=trend_info)
            )
            logger.info("趨勢訊息已回覆")
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
