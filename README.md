# 油價小幫手 LINE Bot

這是一個自動查詢台灣中油油價的 LINE Bot 專案。

## 功能特點

- 自動抓取中油官網最新油價資訊
- 支援查詢 92、95、98 無鉛汽油和超級柴油價格
- 提供油價調整資訊和調整日期
- 使用 LINE Messaging API 提供即時回應

## 技術架構

- Python 3.x
- Flask 框架
- LINE Messaging API
- BeautifulSoup4 網頁爬蟲
- Render 雲端部署

## 部署需求

- Python 3.x
- 相關套件請參考 `requirements.txt`
- LINE Channel Secret 和 Channel Access Token
- Render 帳號（用於部署）

## 使用方式

1. 將 Bot 加入為好友
2. 傳送「油價」或「查詢油價」即可獲得最新油價資訊

## 開發者

- martinWJ
