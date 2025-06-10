# LINE Bot 油價小幫手

這是一個 LINE Bot 應用程式，用於查詢和追蹤台灣中油油價資訊。

## 功能版本規劃

### V1 - 基礎查詢功能
- [x] 查詢本周油價資訊

### V2 - 歷史查詢功能
- [x] 顯示近期的油價趨勢圖表 (參考中油官網設計，基於約 7 週資料)

### V3 - 自動推播功能
- [ ] 每週日自動發送下周油價預測
- [ ] 油價變動提醒（當價格變動超過特定幅度）
- [ ] 可自訂推播時間和頻率

### V4 - 預測分析功能
- [ ] 基於歷史數據預測下周油價
- [ ] 提供油價變動趨勢分析
- [ ] 顯示預測準確度統計

## 技術架構
- Python 3.9+
- Flask Web Framework
- LINE Messaging API
- BeautifulSoup4 (網頁爬蟲)
- Matplotlib (數據視覺化)
- Render (部署平台)

## 安裝與部署
1. 複製專案
2. 安裝依賴套件：`pip install -r requirements.txt`
3. 設定環境變數：
   - LINE_CHANNEL_ACCESS_TOKEN
   - LINE_CHANNEL_SECRET
4. 部署到 Render 平台

## 使用方式
1. 加入 LINE Bot 好友
2. 輸入「查油價」查看本周油價
3. 輸入「查油價趨勢」查看油價趨勢圖表

## 開發團隊
- 開發者：[MartinWJ]

## 授權條款
MIT License
