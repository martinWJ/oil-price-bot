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
from imagekitio import ImageKit
import matplotlib
import base64
import tempfile
matplotlib.use('Agg')  # 使用 Agg 後端

# 設定 logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 設定字體
plt.rcParams['font.family'] = ['DejaVu Sans', 'Arial Unicode MS', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

# 初始化 Flask 應用程式
app = Flask(__name__)

# 設定 LINE Channel Access Token 和 Channel Secret
line_bot_api = LineBotApi(os.getenv('LINE_CHANNEL_ACCESS_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_CHANNEL_SECRET'))

# 檢查環境變數
logger.info("檢查環境變數...")
if not os.getenv('LINE_CHANNEL_ACCESS_TOKEN'):
    logger.error("LINE_CHANNEL_ACCESS_TOKEN 未設置")
if not os.getenv('LINE_CHANNEL_SECRET'):
    logger.error("LINE_CHANNEL_SECRET 未設置")
if not os.getenv('IMAGEKIT_PUBLIC_KEY'):
    logger.error("IMAGEKIT_PUBLIC_KEY 未設置")
if not os.getenv('IMAGEKIT_PRIVATE_KEY'):
    logger.error("IMAGEKIT_PRIVATE_KEY 未設置")
if not os.getenv('IMAGEKIT_URL_ENDPOINT'):
    logger.error("IMAGEKIT_URL_ENDPOINT 未設置")

# ImageKit.io 相關配置
IMAGEKIT_PUBLIC_KEY = os.getenv('IMAGEKIT_PUBLIC_KEY')
IMAGEKIT_PRIVATE_KEY = os.getenv('IMAGEKIT_PRIVATE_KEY')
IMAGEKIT_URL_ENDPOINT = os.getenv('IMAGEKIT_URL_ENDPOINT')

# 初始化 ImageKit
imagekit = ImageKit(
    private_key=os.getenv('IMAGEKIT_PRIVATE_KEY'),
    public_key=os.getenv('IMAGEKIT_PUBLIC_KEY'),
    url_endpoint=os.getenv('IMAGEKIT_URL_ENDPOINT')
)

def get_current_oil_price():
    try:
        url = 'https://www.cpc.com.tw/'
        logger.info(f"開始抓取當前油價，URL: {url}")
        
        # 設定 headers 模擬瀏覽器
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 尋找包含油價資訊的文字
        price_text = None
        for text in soup.find_all(string=re.compile(r'92無鉛汽油每公升|95無鉛汽油每公升|98無鉛汽油每公升|超級柴油每公升')):
            if '每公升' in text:
                price_text = text
                break
        
        if not price_text:
            logger.error("找不到油價資訊")
            return None
            
        # 使用正則表達式提取油價資訊
        price_pattern = r'(92無鉛汽油|95無鉛汽油|98無鉛汽油|超級柴油)每公升(\d+\.\d+)元'
        matches = re.findall(price_pattern, price_text)
        
        if not matches:
            logger.error("無法解析油價資訊")
            return None
            
        # 計算本週日期範圍
        today = datetime.now()
        # 找到最近的週日
        days_since_sunday = today.weekday() + 1
        start_date = today - timedelta(days=days_since_sunday)
        end_date = start_date + timedelta(days=6)
        
        # 格式化日期
        date_range = f"{start_date.strftime('%m/%d')}~{end_date.strftime('%m/%d')}"
        
        # 格式化回覆訊息
        message = f"本周{date_range}中油最新油價資訊:\n"
        for name, price in matches:
            # 移除「汽油」字樣
            name = name.replace('汽油', '')
            message += f"{name}: {price} 元/公升\n"
        
        return message
    except Exception as e:
        logger.error(f"抓取當前油價時發生錯誤: {str(e)}")
        return None

def get_oil_price_trend():
    try:
        url = 'https://www.cpc.com.tw/historyprice.aspx?n=2890'
        logger.info(f"開始抓取油價趨勢資料，URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        html = response.text
        
        match = re.search(r'var\s+priceData\s*=\s*(\[.*?\]);', html, re.DOTALL)
        if not match:
            match = re.search(r'var\s+[a-zA-Z0-9_]+\s*=\s*(\[.*?\]);', html, re.DOTALL)
            if not match:
                logger.error("找不到油價資料")
                return None
                
        price_data_str = match.group(1)
        logger.info(f"找到的資料字串: {price_data_str[:100]}...")
        
        try:
            price_data_str = price_data_str.replace("'", '"')
            price_data = json.loads(price_data_str)
        except json.JSONDecodeError as e:
            logger.error(f"解析油價資料時發生錯誤: {e}")
            return None
        
        if not price_data:
            logger.error("油價資料為空")
            return None
        
        dates = []
        prices_92 = []
        prices_95 = []
        prices_98 = []
        prices_diesel = []
        
        for item in price_data:
            if isinstance(item, dict) and 'data' in item:
                if '92' in item.get('label', ''):
                    prices_92 = [float(x) for x in item['data']]
                elif '95' in item.get('label', ''):
                    prices_95 = [float(x) for x in item['data']]
                elif '98' in item.get('label', ''):
                    prices_98 = [float(x) for x in item['data']]
                elif '柴油' in item.get('label', ''):
                    prices_diesel = [float(x) for x in item['data']]
        
        if not all([prices_92, prices_95, prices_98, prices_diesel]):
            logger.error("無法取得完整的油價資料")
            return None

        # 嘗試從網頁內容中提取日期標籤
        date_labels = []
        num_data_points = len(prices_92) # 根據價格數據點數量來驗證找到的日期列表長度

        # 嘗試尋找所有可能的 JavaScript 字串陣列
        js_string_array_pattern = r'var\s+([a-zA-Z0-9_]+)\s*=\s*(\[(?:['"].*?['"](?:\s*,\s*['"].*?['"])*)?\]);';
        js_arrays = re.findall(js_string_array_pattern, html)
        
        found_dates = False
        for var_name, array_str in js_arrays:
            try:
                # 嘗試解析為 JSON 列表
                # 將單引號替換為雙引號以便 json.loads 解析
                array_str = array_str.replace("'", '"')
                data_list = json.loads(array_str)
                
                # 檢查列表中的元素是否都是字串
                if data_list and all(isinstance(item, str) for item in data_list):
                     logger.info(f"找到可能的字串陣列變數 '{var_name}': {data_list}")

                     # 檢查列表長度是否與數據點數量一致，並且字串包含 '/' (日期格式的常見分隔符)
                     if len(data_list) == num_data_points and all('/' in s for s in data_list):
                        logger.info(f"找到可能的日期標籤變數 '{var_name}', 嘗試解析日期")
                        
                        # 嘗試解析並格式化日期
                        formatted_dates = []
                        for date_str in data_list:
                            try:
                                # 嘗試解析 'YYYY/MM/DD' 或 'YYY/MM/DD' 格式
                                parts = date_str.split('/')
                                if len(parts[0]) <= 3: # 可能是民國紀年
                                    year, month, day = map(int, parts)
                                    # 將民國紀年轉換為西元紀年
                                    western_year = year + 1911
                                    datetime_obj = datetime(western_year, month, day)
                                else:
                                    # 假設是西元紀年 'YYYY/MM/DD'
                                    datetime_obj = datetime.strptime(date_str, '%Y/%m/%d')
                                    
                                # 格式化為 'MM/DD'
                                formatted_dates.append(datetime_obj.strftime('%m/%d'))
                            except (ValueError, IndexError) as e:
                                # 如果解析或轉換失敗，保留原始字串並記錄錯誤
                                logger.warning(f"無法解析或轉換日期字串 '{date_str}': {str(e)}")
                                formatted_dates.append(date_str) # 保留原始字串
                                
                        # 如果成功解析的日期數量與數據點數量一致，則認為找到正確的日期標籤
                        if len(formatted_dates) == num_data_points:
                            date_labels = formatted_dates
                            found_dates = True
                            logger.info("成功提取、解析並格式化日期標籤")
                            break # 找到正確的日期後就停止搜索
                            
            except Exception as e:
                # 解析 JSON 或其他錯誤
                logger.warning(f"解析 JavaScript 變數 '{var_name}' 時發生錯誤: {str(e)}")
                
        if not found_dates:
            logger.warning("無法從網頁內容中提取日期標籤，使用數字標籤")
            # 如果沒有找到符合的日期列表，回退使用數字作為標籤
            date_labels = list(range(1, num_data_points + 1))

        # 確保日期標籤數量與價格數據數量一致 (儘管上面已經檢查過一次，這裡再檢查一次作為保險)
        if len(date_labels) != num_data_points:
            logger.error(f"日期標籤數量與價格數據數量最終不一致: 標籤={len(date_labels)}, 價格={num_data_points}")
            # 如果數量不一致，回退使用數字作為標籤
            date_labels = list(range(1, num_data_points + 1))

        plt.figure(figsize=(10, 6))
        # 使用提取或生成的日期標籤作為 X 軸數據
        plt.plot(date_labels, prices_92, marker='o', label='92 Unleaded')
        plt.plot(date_labels, prices_95, marker='o', label='95 Unleaded')
        plt.plot(date_labels, prices_98, marker='o', label='98 Unleaded')
        plt.plot(date_labels, prices_diesel, marker='o', label='Super Diesel')
        
        # 在每個點上添加價格標籤
        for i, date in enumerate(date_labels):
             plt.text(date, prices_92[i], f"{prices_92[i]:.1f}", ha='center', va='bottom', fontsize=10)
             plt.text(date, prices_95[i], f"{prices_95[i]:.1f}", ha='center', va='bottom', fontsize=10)
             plt.text(date, prices_98[i], f"{prices_98[i]:.1f}", ha='center', va='bottom', fontsize=10)
             plt.text(date, prices_diesel[i], f"{prices_diesel[i]:.1f}", ha='center', va='bottom', fontsize=10)
            
        plt.xlabel('Date')
        plt.ylabel('Price (NTD/L)')
        plt.title('CPC Oil Price Trend')
        
        # 設置 X 軸刻度和標籤，確保所有標籤都顯示且旋轉
        # 我們已經使用日期字串作為 plot 的 x 值，matplotlib 會嘗試將其作為類別數據處理
        # 如果需要更精確的控制刻度位置，可以使用數字索引作為 plot 的 x 值，然後在 xticks 中設置標籤
        # 這裡我們假設直接使用日期字串作為 x 值，matplotlib 可以正確處理
        plt.xticks(rotation=45)
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        
        buffer = BytesIO()
        plt.savefig(buffer, format='png', dpi=300, bbox_inches='tight')
        buffer.seek(0)
        plt.close()
        
        logger.info("Oil price trend chart generated in memory")
        return buffer
    except Exception as e:
        logger.error(f"生成油價趨勢圖表時發生錯誤: {str(e)}")
        return None

@app.route("/webhook", methods=['POST'])
def callback():
    # 取得 X-Line-Signature header 值
    signature = request.headers['X-Line-Signature']
    logger.info(f"收到 webhook 請求，signature: {signature}")

    # 取得請求內容
    body = request.get_data(as_text=True)
    logger.info("Request body: " + body)
    
    try:
        handler.handle(body, signature)
        logger.info("成功處理 webhook 請求")
    except InvalidSignatureError:
        logger.error("無效的簽名")
        abort(400)
    except Exception as e:
        logger.error(f"處理 webhook 請求時發生錯誤: {str(e)}")
        abort(500)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    text = event.message.text
    logger.info(f"收到訊息: {text}")
    logger.info(f"訊息來源: {event.source.user_id}")
    
    try:
        if text in ["趨勢", "油價趨勢"]:
            logger.info("開始處理趨勢請求")
            try:
                buffer = get_oil_price_trend()
                if buffer:
                    logger.info("成功取得油價趨勢圖")
                    try:
                        # 將圖片保存到臨時檔案
                        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_file:
                            temp_file.write(buffer.getvalue())
                            temp_file_path = temp_file.name
                        
                        try:
                            # 讀取檔案內容為 bytes
                            with open(temp_file_path, 'rb') as file:
                                file_bytes = file.read()
                            
                            # 上傳到 ImageKit
                            try:
                                # 將圖片轉換為 base64
                                base64_image = base64.b64encode(file_bytes).decode('utf-8')
                                
                                # 使用 requests 直接調用 ImageKit API
                                from urllib.parse import urljoin
                                
                                upload_url = "https://upload.imagekit.io/api/v1/files/upload"
                                private_key = os.getenv('IMAGEKIT_PRIVATE_KEY')
                                auth_string = f"{private_key}:"
                                auth_b64 = base64.b64encode(auth_string.encode()).decode()
                                
                                headers = {
                                    "Authorization": f"Basic {auth_b64}"
                                }
                                
                                data = {
                                    "file": base64_image,
                                    "fileName": f"oil_price_trend_{datetime.now().strftime('%Y%m%d%H%M%S')}.png",
                                    "useUniqueFileName": "true",
                                    "tags": ["oil_price", "trend"],
                                    "responseFields": ["url"]
                                }
                                
                                response = requests.post(upload_url, headers=headers, data=data)
                                response.raise_for_status()
                                upload_result = response.json()
                                
                                logger.info(f"ImageKit upload response: {upload_result}")
                                
                                if upload_result and 'url' in upload_result:
                                    image_url = upload_result['url']
                                    logger.info(f"Successfully uploaded image to ImageKit: {image_url}")
                                    
                                    # 回傳圖片
                                    line_bot_api.reply_message(
                                        event.reply_token,
                                        ImageSendMessage(
                                            original_content_url=image_url,
                                            preview_image_url=image_url
                                        )
                                    )
                                    logger.info("Oil price trend chart sent")
                                else:
                                    raise ValueError("No URL in upload result")
                                    
                            except Exception as e:
                                logger.error(f"Error uploading image: {str(e)}")
                                logger.error(f"Error type: {type(e)}")
                                # 如果上傳失敗，直接使用本地檔案
                                try:
                                    # 回傳圖片
                                    line_bot_api.reply_message(
                                        event.reply_token,
                                        TextSendMessage(text="Sorry, unable to upload the image. Please try again later.")
                                    )
                                except Exception as direct_error:
                                    logger.error(f"Error sending error message: {str(direct_error)}")
                        finally:
                            # 清理臨時檔案
                            try:
                                os.unlink(temp_file_path)
                            except Exception as cleanup_error:
                                logger.error(f"Error cleaning up temporary file: {str(cleanup_error)}")
                    except Exception as e:
                        logger.error(f"Error processing image: {str(e)}")
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextSendMessage(text="Sorry, failed to process the image. Please try again later.")
                        )
                else:
                    logger.error("無法取得油價趨勢資料")
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="Sorry, unable to get oil price trend data. Please try again later.")
                    )
            except Exception as e:
                logger.error(f"Error processing trend request: {str(e)}")
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="Sorry, system is temporarily unable to process your request. Please try again later.")
                )
        elif text == "油價":
            logger.info("收到油價指令")
            price_info = get_current_oil_price()
            if price_info:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=price_info)
                )
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="Sorry, unable to get current oil price. Please try again later.")
                )
        else:
            logger.info(f"收到未知指令: {text}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="Hello! I am an oil price query bot\n\nPlease enter the following commands:\n• 油價：Query current oil price\n• 趨勢：View oil price trend chart")
            )
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        try:
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="Sorry, system error occurred. Please try again later.")
            )
        except Exception as reply_error:
            logger.error(f"Error sending error message: {str(reply_error)}")

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port) 