# Discord 請假機器人

一個用於 Discord 伺服器的請假管理機器人。員工透過**按鈕面板**申請、查看、取消請假，管理員一次設置面板後即可長期使用。

## 功能特色

- 🏢 **持久按鈕面板** — 設置一次即可，機器人重啟後仍有效，員工全程用按鈕操作，不需打指令
- 📅 **請假申請** — 階層式選單（年 → 月 → 上/下半月 → 日），自動擋掉過去的日期，並防止重複請假
- 📋 **月曆檢視** — 以圖片呈現當月每天的請假**人數**（不顯示姓名以保護隱私），可切換月份；下拉選單可查看某天「是誰」請假
- ✖️ **取消請假** — 員工可取消自己的請假
- 📢 **自動提醒**
  - 有人申請**當天**請假時，即時公開提醒大家
  - 有人取消**當天**請假時，公開提醒並更新今日請假人數
  - 每天早上（台灣時間 09:00）若今天有人請假，自動到面板頻道公告名單
- 🗄️ **歷史封存** — 過期的請假不會被刪除，而是搬到封存檔保存，月曆可往回查看歷史

## 指令

| 指令 | 說明 | 權限 |
|------|------|------|
| `!設置面板` | 在當前頻道發送請假面板，並記住此頻道作為每日提醒的發送地點 | 僅管理員 |
| `!清空請假` | 清空目前（今天與未來）的請假記錄，歷史封存保留 | 僅管理員 |

> 日常請假、查看、取消都透過面板上的按鈕完成，不需指令。

## 安裝步驟

1. **安裝依賴**
```bash
pip install -r requirements.txt
```

2. **設定 Discord Token**
   - 在專案根目錄建立 `.env` 檔案
   - 新增以下內容：
```
DISCORD_TOKEN=你的discord_bot_token
```

3. **運行機器人**
```bash
python main.py
```

4. **設置面板**
   - 在想放面板的頻道輸入 `!設置面板`（需管理員權限）
   - 之後所有人即可用面板上的按鈕操作

## Discord Bot 設定

1. 造訪 [Discord Developer Portal](https://discord.com/developers/applications)
2. 建立新應用，並在 "Bot" 分頁建立 bot
3. 複製 Token 貼到 `.env` 檔案
4. 在 "Bot" 分頁開啟 **Message Content Intent**（讀取訊息內容，指令前綴需要）
5. 在 "OAuth2" > "URL Generator" 選擇權限：
   - `bot`
   - `Send Messages`
   - `Embed Links`
   - `Attach Files`（月曆圖片需要）
   - `Read Message History`
6. 使用生成的 URL 邀請 bot 加入你的伺服器

## 使用方法

設置面板後，面板上有三個按鈕：

- **📅 請假申請** — 開啟日曆，依序選擇年 → 月 → 上/下半月 → 日期送出
- **📋 查看請假** — 顯示當月月曆圖（每格為當天人數），可按 ◀ 上月 / 下月 ▶ 切換，並用下拉選單查看某天有誰請假
- **✖️ 取消請假** — 列出你自己的請假，選一個即可取消

以上互動畫面皆為**僅本人可見**（ephemeral），不會洗版。

## 數據儲存

所有資料存放於 `data/` 資料夾，屬於機器人執行資料，請勿手動編輯：

| 檔案 | 用途 |
|------|------|
| `data/leaves.json` | 現用請假（今天與未來） |
| `data/leaves_archive.json` | 歷史封存（已過去的請假，每天凌晨自動搬入） |
| `data/config.json` | 設定，目前儲存面板所在的頻道 ID（供每日提醒使用） |

## 專案結構

```
AFL_discordbot/
├── main.py                  # 主程式
├── requirements.txt         # 依賴列表
├── .env                     # 環境變數（包含 Discord Token）
├── .env.example             # 環境變數示例
├── README.md                # 說明文檔
└── data/
    ├── leaves.json          # 現用請假資料
    ├── leaves_archive.json  # 歷史封存
    └── config.json          # 設定（面板頻道）
```

## 技術棧

- Python 3.13+
- [discord.py](https://github.com/Rapptz/discord.py) 2.4.0+
- [Pillow](https://python-pillow.org/) — 產生月曆圖片
- python-dotenv — 讀取 `.env`

> 月曆圖片使用微軟正黑體（`C:/Windows/Fonts/msjh.ttc`）。若部署到非 Windows 環境，需在 `main.py` 的 `FONT_PATH` 改為該系統上的中文字型路徑。

## 授權

MIT License
