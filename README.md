# Discord 請假機器人

這是一個用於Discord伺服器的請假管理機器人。

## 功能

- **!請假** - 顯示請假菜單，點擊按鈕可選擇請假日期
- **!查看請假** - 查看所有請假記錄
- **!清空請假** - 清空所有請假記錄（僅管理員）

## 安裝步驟

1. **安裝依賴**
```bash
pip install -r requirements.txt
```

2. **設定Discord Token**
   - 在專案根目錄建立 `.env` 檔案
   - 新增以下內容：
```
DISCORD_TOKEN=你的discord_bot_token
```

3. **運行機器人**
```bash
python main.py
```

## Discord Bot 設定

1. 造訪 [Discord Developer Portal](https://discord.com/developers/applications)
2. 建立新應用
3. 在 "Bot" 選項卡中建立bot
4. 複製Token並貼上到 `.env` 檔案中
5. 在 "OAuth2" > "URL Generator" 中選擇權限：
   - `bot`
   - `send_messages`
   - `use_slash_commands`
   - `embed_links`
   - `read_message_history`
6. 使用生成的URL邀請bot加入你的伺服器

## 使用方法

### 請假申請
1. 在Discord中輸入 `!請假`
2. 點擊 "請假申請" 按鈕
3. 在日曆中選擇要請假的日期
4. 點擊日期按鈕確認請假

### 查看請假記錄
輸入 `!查看請假` 查看所有請假申請

### 清空請假記錄
輸入 `!清空請假` 清空所有請假記錄（需要管理員權限）

## 數據儲存

所有請假數據保存在 `data/leaves.json` 檔案中

## 專案結構

```
AFL_discordbot/
├── main.py                 # 主程式
├── requirements.txt        # 依賴列表
├── .env                    # 環境變數（包含Discord Token）
├── .env.example           # 環境變數示例
├── README.md              # 說明文檔
└── data/
    └── leaves.json        # 請假數據檔案
```

## 授權

MIT License
