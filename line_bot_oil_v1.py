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
        
        # 設定 Chrome 執行檔路徑
        chrome_path = '/usr/bin/google-chrome'
        if not os.path.exists(chrome_path):
            chrome_path = '/usr/bin/chromium-browser'
        if not os.path.exists(chrome_path):
            chrome_path = '/usr/bin/chromium'
        
        logger.info(f"使用 Chrome 執行檔路徑: {chrome_path}")
        
        # 初始化 undetected-chromedriver
        driver = uc.Chrome(
            options=options,
            driver_executable_path=chrome_path,
            version_main=114  # 指定 Chrome 版本
        )
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