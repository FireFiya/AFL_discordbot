import discord
from discord.ext import commands, tasks
from discord.ui import View, Button, Select
import json
import os
import io
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, time, timezone, timedelta
import calendar
from PIL import Image, ImageDraw, ImageFont
from dotenv import load_dotenv

load_dotenv()


def setup_logging():
    """設定日誌：同時輸出到終端機與 logs/bot.log（自動輪替）"""
    # 讓 Windows 終端機也能正常顯示中文（StreamHandler 預設寫到 stderr）
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass
    os.makedirs('logs', exist_ok=True)
    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if root.handlers:  # 避免重複載入時加到重複的 handler
        return logging.getLogger('leavebot')

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    root.addHandler(console)

    file_handler = RotatingFileHandler(
        'logs/bot.log', maxBytes=1_000_000, backupCount=5, encoding='utf-8'
    )
    file_handler.setFormatter(fmt)
    root.addHandler(file_handler)

    return logging.getLogger('leavebot')


log = setup_logging()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 擁有者 ID（雙保險）：即使 bot 掛在開發者 Team 底下也一定認得你
_owner_env = os.getenv('OWNER_ID')
OWNER_ID = int(_owner_env) if _owner_env and _owner_env.isdigit() else None


async def _is_owner(user) -> bool:
    """是否為機器人擁有者（.env 的 OWNER_ID 或 Discord 應用擁有者）"""
    if OWNER_ID is not None and user.id == OWNER_ID:
        return True
    try:
        return await bot.is_owner(user)
    except Exception:
        return False


def owner_only():
    """指令檢查：只有擁有者能用"""
    async def predicate(ctx):
        return await _is_owner(ctx.author)
    return commands.check(predicate)


def owner_or_manage_guild():
    """指令檢查：擁有者，或具『管理伺服器』權限者"""
    async def predicate(ctx):
        if await _is_owner(ctx.author):
            return True
        return bool(ctx.guild and ctx.author.guild_permissions.manage_guild)
    return commands.check(predicate)


DATA_DIR = 'data'
GLOBAL_CONFIG_FILE = 'data/config.json'   # 全域設定：授權的伺服器清單
# 每個伺服器的資料放在 data/<guild_id>/ 底下
LEAVES_NAME = 'leaves.json'          # 現用：今天與未來
ARCHIVE_NAME = 'leaves_archive.json'  # 封存：過去的歷史紀錄
RECURRING_NAME = 'recurring.json'    # 定期請假規則（每周X）
GUILD_CONFIG_NAME = 'config.json'    # 該伺服器設定（面板頻道、開關）

TW_TZ = timezone(timedelta(hours=8))    # 台灣時區 UTC+8

# Python 的 weekday()：週一=0 … 週日=6
WEEKDAY_NAMES = ['一', '二', '三', '四', '五', '六', '日']
# 選單顯示順序：日 → 六
WEEKDAY_UI_ORDER = [6, 0, 1, 2, 3, 4, 5]

def _guild_dir(guild_id):
    return os.path.join(DATA_DIR, str(guild_id))

def _guild_path(guild_id, name):
    return os.path.join(_guild_dir(guild_id), name)

def ensure_guild_files(guild_id):
    """確保某伺服器的資料夾與各檔案存在"""
    d = _guild_dir(guild_id)
    os.makedirs(d, exist_ok=True)
    for name in (LEAVES_NAME, ARCHIVE_NAME, RECURRING_NAME):
        p = os.path.join(d, name)
        if not os.path.exists(p):
            with open(p, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)

def _load(path, default):
    if not os.path.exists(path):
        return default
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _save(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ---------- 全域設定（授權清單） ----------

def load_global_config():
    return _load(GLOBAL_CONFIG_FILE, {})

def save_global_config(cfg):
    _save(GLOBAL_CONFIG_FILE, cfg)

def get_authorized_guilds():
    return load_global_config().get('authorized_guilds', [])

def is_authorized(guild_id):
    return str(guild_id) in get_authorized_guilds()

def authorize_guild(guild_id):
    cfg = load_global_config()
    lst = cfg.setdefault('authorized_guilds', [])
    if str(guild_id) not in lst:
        lst.append(str(guild_id))
        save_global_config(cfg)
        return True
    return False

def deauthorize_guild(guild_id):
    cfg = load_global_config()
    lst = cfg.get('authorized_guilds', [])
    if str(guild_id) in lst:
        lst.remove(str(guild_id))
        save_global_config(cfg)
        return True
    return False

# ---------- 每伺服器設定（面板頻道、開關） ----------

def load_guild_config(guild_id):
    return _load(_guild_path(guild_id, GUILD_CONFIG_NAME), {})

def save_guild_config(guild_id, cfg):
    _save(_guild_path(guild_id, GUILD_CONFIG_NAME), cfg)

def get_panel_channel_id(guild_id):
    return load_guild_config(guild_id).get('panel_channel_id')

def set_panel_channel_id(guild_id, channel_id):
    cfg = load_guild_config(guild_id)
    cfg['panel_channel_id'] = channel_id
    save_guild_config(guild_id, cfg)

def is_enabled(guild_id):
    """該伺服器是否啟用（預設啟用）"""
    return load_guild_config(guild_id).get('enabled', True)

def set_enabled(guild_id, enabled):
    cfg = load_guild_config(guild_id)
    cfg['enabled'] = enabled
    save_guild_config(guild_id, cfg)

def is_active(guild_id):
    """已授權且未暫停，才會實際運作"""
    return is_authorized(guild_id) and is_enabled(guild_id)

# ---------- 請假資料（每伺服器） ----------

def load_leaves(guild_id):
    """現用資料（今天與未來），請假申請與重複檢查都以此為準"""
    return _load(_guild_path(guild_id, LEAVES_NAME), {})

def save_leaves(guild_id, data):
    _save(_guild_path(guild_id, LEAVES_NAME), data)

def load_archive(guild_id):
    return _load(_guild_path(guild_id, ARCHIVE_NAME), {})

def get_all_leaves(guild_id):
    """現用 + 封存 合併，供月曆顯示歷史用（兩者日期不重疊）"""
    merged = load_archive(guild_id)
    merged.update(load_leaves(guild_id))
    return merged

def add_leave(guild_id, user_id, username, date_str):
    leaves = load_leaves(guild_id)
    if date_str not in leaves:
        leaves[date_str] = []
    # 防止重複請假
    for entry in leaves[date_str]:
        if entry['user_id'] == user_id:
            return False
    leaves[date_str].append({'user_id': user_id, 'username': username})
    save_leaves(guild_id, leaves)
    return True

def remove_leave(guild_id, user_id, date_str):
    """取消使用者在某天的請假（只動現用資料、且只能取消今天起的），回傳是否成功"""
    if datetime.strptime(date_str, "%Y-%m-%d").date() < datetime.now().date():
        return False  # 不允許取消過去的請假
    leaves = load_leaves(guild_id)
    if date_str not in leaves:
        return False
    new_list = [e for e in leaves[date_str] if e['user_id'] != user_id]
    if len(new_list) == len(leaves[date_str]):
        return False
    if new_list:
        leaves[date_str] = new_list
    else:
        del leaves[date_str]
    save_leaves(guild_id, leaves)
    return True

def get_user_leaves(guild_id, user_id):
    """回傳使用者今天起（含今天）的請假日期（已排序）"""
    leaves = load_leaves(guild_id)
    today = datetime.now().date()
    return sorted(
        d for d in leaves
        if datetime.strptime(d, "%Y-%m-%d").date() >= today
        and any(e['user_id'] == user_id for e in leaves[d])
    )

# ---------- 定期請假（每周X，每伺服器） ----------

def load_recurring(guild_id):
    return _load(_guild_path(guild_id, RECURRING_NAME), {})

def save_recurring(guild_id, data):
    _save(_guild_path(guild_id, RECURRING_NAME), data)

def get_user_weekdays(guild_id, user_id):
    """回傳使用者已設定的定期星期幾（Python weekday，已排序）"""
    entry = load_recurring(guild_id).get(str(user_id))
    return sorted(entry['weekdays']) if entry else []

def add_user_weekday(guild_id, user_id, username, weekday):
    """新增一條定期規則，回傳是否新增成功（已存在則 False）"""
    data = load_recurring(guild_id)
    key = str(user_id)
    entry = data.setdefault(key, {'username': username, 'weekdays': []})
    entry['username'] = username  # 名稱可能改過，順便更新
    if weekday in entry['weekdays']:
        return False
    entry['weekdays'].append(weekday)
    save_recurring(guild_id, data)
    return True

def remove_user_weekday(guild_id, user_id, weekday):
    """移除一條定期規則，回傳是否移除成功"""
    data = load_recurring(guild_id)
    key = str(user_id)
    entry = data.get(key)
    if not entry or weekday not in entry['weekdays']:
        return False
    entry['weekdays'].remove(weekday)
    if not entry['weekdays']:
        del data[key]
    save_recurring(guild_id, data)
    return True

def _month_days_of_weekday(year, month, weekday, from_today=True):
    """回傳某月中所有符合星期幾的日期字串；from_today=True 時略過已過去的日子"""
    today = datetime.now().date()
    result = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        d = datetime(year, month, day).date()
        if d.weekday() != weekday:
            continue
        if from_today and d < today:
            continue
        result.append(d.strftime("%Y-%m-%d"))
    return result

def generate_recurring_leaves(guild_id, user_id, username, weekday, year, month):
    """把某月（今天起）符合星期幾的日子請起來，回傳實際新增的天數（重複的會被跳過）"""
    count = 0
    for date_str in _month_days_of_weekday(year, month, weekday):
        if add_leave(guild_id, user_id, username, date_str):
            count += 1
    return count

def remove_recurring_leaves(guild_id, user_id, weekday, year, month):
    """刪除某月（今天起）符合星期幾的請假，回傳實際刪除的天數"""
    count = 0
    for date_str in _month_days_of_weekday(year, month, weekday):
        if remove_leave(guild_id, user_id, date_str):
            count += 1
    return count

def count_user_recurring_leaves(guild_id, user_id, weekday, year, month):
    """使用者在某月（今天起）該星期幾實際已請的天數"""
    leaves = load_leaves(guild_id)
    return sum(
        1 for date_str in _month_days_of_weekday(year, month, weekday)
        if any(e['user_id'] == user_id for e in leaves.get(date_str, []))
    )

def generate_all_recurring_for_month(guild_id, year, month):
    """為所有有定期規則的人產生該月的假，回傳（人數, 總天數）"""
    data = load_recurring(guild_id)
    users = 0
    total = 0
    for key, entry in data.items():
        added = 0
        for wd in entry['weekdays']:
            added += generate_recurring_leaves(guild_id, int(key), entry['username'], wd, year, month)
        if added:
            users += 1
            total += added
    return users, total


def archive_past_leaves(guild_id):
    """將已過去的請假（當天不搬，隔天才搬）從現用搬到封存檔，回傳搬移的天數"""
    leaves = load_leaves(guild_id)
    today = datetime.now().date()
    past = [
        d for d in leaves
        if datetime.strptime(d, "%Y-%m-%d").date() < today
    ]
    if not past:
        return 0
    archive = load_archive(guild_id)
    for d in past:
        archive[d] = leaves.pop(d)
    save_leaves(guild_id, leaves)
    _save(_guild_path(guild_id, ARCHIVE_NAME), archive)
    return len(past)

FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fonts')

def _resolve_font_path():
    """自動尋找可用的中文字型，跨平台（部署到 Linux 也能運作）"""
    # 1) 專案 fonts/ 內附帶的任何字型檔（隨專案一起部署最方便）
    if os.path.isdir(FONTS_DIR):
        for name in sorted(os.listdir(FONTS_DIR)):
            if name.lower().endswith(('.ttc', '.otf', '.ttf')):
                return os.path.join(FONTS_DIR, name)
    # 2) 常見系統字型位置（Linux 的 Noto、Windows 的微軟正黑體）
    for path in (
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc',
        'C:/Windows/Fonts/msjh.ttc',
    ):
        if os.path.exists(path):
            return path
    return None

FONT_PATH = _resolve_font_path()
if FONT_PATH is None:
    log.warning("找不到中文字型，月曆圖將無法產生；請放一份字型檔到 fonts/ 資料夾")
else:
    log.info(f"使用字型：{FONT_PATH}")

def generate_calendar_image(guild_id, year, month):
    """產生當月月曆圖，每格顯示當天請假人數（不寫名字），回傳 BytesIO"""
    leaves = get_all_leaves(guild_id)

    cell_w, cell_h = 130, 90
    header_h = 70
    weekday_h = 44
    cols = 7

    cal = calendar.Calendar(firstweekday=6)  # 週日為一週的開始
    weeks = cal.monthdayscalendar(year, month)
    rows = len(weeks)

    width = cell_w * cols
    height = header_h + weekday_h + cell_h * rows

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    title_font = ImageFont.truetype(FONT_PATH, 34)
    wd_font = ImageFont.truetype(FONT_PATH, 22)
    day_font = ImageFont.truetype(FONT_PATH, 24)
    cnt_font = ImageFont.truetype(FONT_PATH, 22)

    # 標題
    draw.text((width / 2, header_h / 2), f"{year} 年 {month} 月",
              font=title_font, fill="black", anchor="mm")

    # 星期列
    weekdays = ["日", "一", "二", "三", "四", "五", "六"]
    for i, wd in enumerate(weekdays):
        x = i * cell_w + cell_w / 2
        y = header_h + weekday_h / 2
        draw.text((x, y), wd, font=wd_font,
                  fill="#d9534f" if i in (0, 6) else "black", anchor="mm")

    today = datetime.now().date()
    for r, week in enumerate(weeks):
        for c, day in enumerate(week):
            x0 = c * cell_w
            y0 = header_h + weekday_h + r * cell_h
            x1, y1 = x0 + cell_w, y0 + cell_h

            if day != 0 and datetime(year, month, day).date() == today:
                draw.rectangle([x0, y0, x1, y1], fill="#fff3cd")
            draw.rectangle([x0, y0, x1, y1], outline="#cccccc", width=1)

            if day == 0:
                continue

            date_str = f"{year}-{month:02d}-{day:02d}"
            count = len(leaves.get(date_str, []))

            draw.text((x0 + 8, y0 + 6), str(day), font=day_font, fill="black")
            draw.text((x0 + cell_w / 2, y0 + cell_h * 0.62), f"{count}人",
                      font=cnt_font, fill="#d9534f" if count > 0 else "#aaaaaa",
                      anchor="mm")

    buf = io.BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


class CalendarView(View):
    """日曆選擇檢視 - 年/月/上下半月/日期選擇，另有「定時請假」模式選星期幾"""
    def __init__(self, user_id: int, guild_id: int):
        super().__init__()
        self.user_id = user_id
        self.guild_id = guild_id
        now = datetime.now()
        self.year = now.year
        self.month = now.month
        self.is_second_half = False
        self.recurring_mode = False  # True 時改為選「每周X」
        self.setup_selects()

    def setup_selects(self):
        self.clear_items()

        if self.recurring_mode:
            # 定時模式：年、月兩個選單合併成一個「星期幾」選單，日期選單隱藏
            weekday_options = [
                discord.SelectOption(
                    label=f"每周{WEEKDAY_NAMES[wd]}",
                    value=str(wd),
                    description=f"本月（{self.month}月）今天起所有週{WEEKDAY_NAMES[wd]}都請假"
                )
                for wd in WEEKDAY_UI_ORDER
            ]
            weekday_select = discord.ui.Select(
                placeholder="選擇要定期請假的星期幾...",
                options=weekday_options,
                custom_id=f"weekday_select_{self.user_id}",
                row=0
            )
            weekday_select.callback = self.weekday_selected
            self.add_item(weekday_select)
        else:
            year_options = [
                discord.SelectOption(label=str(y), value=str(y), default=(y == self.year))
                for y in range(self.year, self.year + 25)
            ]
            year_select = discord.ui.Select(
                placeholder="選擇年份...",
                options=year_options,
                custom_id=f"year_select_{self.user_id}",
                row=0
            )
            year_select.callback = self.year_changed
            self.add_item(year_select)

            month_options = [
                discord.SelectOption(label=f"{m}月", value=str(m), default=(m == self.month))
                for m in range(1, 13)
            ]
            month_select = discord.ui.Select(
                placeholder="選擇月份...",
                options=month_options,
                custom_id=f"month_select_{self.user_id}",
                row=1
            )
            month_select.callback = self.month_changed
            self.add_item(month_select)

        max_day = calendar.monthrange(self.year, self.month)[1]
        mid_day = max_day // 2
        normal = not self.recurring_mode

        first_half = Button(
            label=f"上半月 (1-{mid_day}日)",
            style=discord.ButtonStyle.primary if (normal and not self.is_second_half) else discord.ButtonStyle.secondary,
            custom_id=f"first_half_{self.user_id}",
            row=2
        )
        first_half.callback = self.show_first_half
        self.add_item(first_half)

        second_half = Button(
            label=f"下半月 ({mid_day + 1}-{max_day}日)",
            style=discord.ButtonStyle.primary if (normal and self.is_second_half) else discord.ButtonStyle.secondary,
            custom_id=f"second_half_{self.user_id}",
            row=2
        )
        second_half.callback = self.show_second_half
        self.add_item(second_half)

        recurring = Button(
            label="定時請假",
            emoji="🔁",
            style=discord.ButtonStyle.primary if self.recurring_mode else discord.ButtonStyle.secondary,
            custom_id=f"recurring_{self.user_id}",
            row=2
        )
        recurring.callback = self.show_recurring
        self.add_item(recurring)

        if not self.recurring_mode:
            date_options = self.get_date_options()
            if date_options:
                date_select = discord.ui.Select(
                    placeholder="選擇日期...",
                    options=date_options,
                    custom_id=f"date_select_{self.user_id}",
                    row=3
                )
                date_select.callback = self.date_selected
                self.add_item(date_select)

    def get_date_options(self):
        max_day = calendar.monthrange(self.year, self.month)[1]
        mid_day = max_day // 2

        if self.is_second_half:
            start_day, end_day = mid_day + 1, max_day
        else:
            start_day, end_day = 1, mid_day

        today = datetime.now().date()
        options = []
        for day in range(start_day, end_day + 1):
            date_obj = datetime(self.year, self.month, day)
            if date_obj.date() < today:
                continue
            day_name = ['一', '二', '三', '四', '五', '六', '日'][date_obj.weekday()]
            options.append(discord.SelectOption(
                label=f"{day:2d}日 ({day_name})",
                value=f"{self.year}-{self.month:02d}-{day:02d}"
            ))
        return options

    async def year_changed(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        self.year = int(interaction.data['values'][0])
        self.setup_selects()
        await interaction.response.edit_message(view=self)

    async def month_changed(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        self.month = int(interaction.data['values'][0])
        self.is_second_half = False
        self.setup_selects()
        await interaction.response.edit_message(view=self)

    async def show_first_half(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        self.is_second_half = False
        self.recurring_mode = False  # 回到一般模式
        self.setup_selects()
        await interaction.response.edit_message(view=self)

    async def show_second_half(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        self.is_second_half = True
        self.recurring_mode = False  # 回到一般模式
        self.setup_selects()
        await interaction.response.edit_message(view=self)

    async def show_recurring(self, interaction: discord.Interaction):
        """切換到定時請假模式：只選星期幾，套用當月"""
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        now = datetime.now()
        # 定時請假一律套用「今天所在的月份」
        self.year, self.month = now.year, now.month
        self.recurring_mode = True
        self.setup_selects()
        await interaction.response.edit_message(view=self)

    async def weekday_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        weekday = int(interaction.data['values'][0])
        name = WEEKDAY_NAMES[weekday]
        now = datetime.now()

        is_new = add_user_weekday(self.guild_id, interaction.user.id, interaction.user.name, weekday)
        added = generate_recurring_leaves(
            self.guild_id, interaction.user.id, interaction.user.name, weekday, now.year, now.month
        )

        if is_new:
            title = f"🔁 已設定定期請假：每周{name}"
        else:
            title = f"🔁 每周{name} 已在你的定期請假中"

        if added:
            desc = f"本月（{now.month}月）已為你排入 **{added}** 天的週{name}請假。"
        else:
            desc = f"本月（{now.month}月）已無新的週{name}可排入（可能都請過了或已過去）。"
        desc += "\n\n每月 1 號會自動排入下個月的定期請假。"

        embed = discord.Embed(title=title, description=desc, color=discord.Color.blue())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        log.info(
            f"定期請假設定：{interaction.user}（{interaction.user.id}）每周{name}，"
            f"本月排入 {added} 天"
        )

    async def date_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        date_str = interaction.data['values'][0]
        if datetime.strptime(date_str, "%Y-%m-%d").date() < datetime.now().date():
            await interaction.response.send_message("❌ 不能申請過去的日期", ephemeral=True)
            return
        success = add_leave(self.guild_id, interaction.user.id, interaction.user.name, date_str)
        if not success:
            await interaction.response.send_message(
                f"⚠️ 你已經申請過 {date_str} 的請假了",
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            f"✅ 已記錄請假日期：{date_str}\n使用者：{interaction.user.name}",
            ephemeral=True
        )
        log.info(f"請假申請：{interaction.user}（{interaction.user.id}）→ {date_str}")

        # 當天臨時請假 → 發出公開提醒讓大家注意
        if datetime.strptime(date_str, "%Y-%m-%d").date() == datetime.now().date():
            embed = discord.Embed(
                title="⚠️ 有人臨時請假喔",
                description=f"**{interaction.user.name}** 申請了今天（{date_str}）的請假，請大家注意！",
                color=discord.Color.red()
            )
            await interaction.channel.send(embed=embed)


class LeaveCalendarView(View):
    """請假月曆檢視 - 顯示當月人數圖，可換月並查詢某天誰請假"""
    def __init__(self, guild_id: int, year: int, month: int):
        super().__init__(timeout=300)
        self.guild_id = guild_id
        self.year = year
        self.month = month
        self.build_day_select()

    def shift_month(self, delta: int):
        m = self.month + delta
        y = self.year
        if m < 1:
            m, y = 12, y - 1
        elif m > 12:
            m, y = 1, y + 1
        self.year, self.month = y, m

    def build_day_select(self):
        """重建「查看某天誰請假」的下拉選單，只列出當月有人請假的日期"""
        for item in list(self.children):
            if isinstance(item, Select):
                self.remove_item(item)

        leaves = get_all_leaves(self.guild_id)
        options = []
        max_day = calendar.monthrange(self.year, self.month)[1]
        for day in range(1, max_day + 1):
            date_str = f"{self.year}-{self.month:02d}-{day:02d}"
            cnt = len(leaves.get(date_str, []))
            if cnt > 0:
                options.append(discord.SelectOption(
                    label=f"{self.month}月{day}日（{cnt}人）",
                    value=date_str
                ))

        if options:
            sel = Select(placeholder="選擇日期查看誰請假...", options=options[:25], row=1)
            sel.callback = self.day_selected
            self.add_item(sel)

    def make_embed_and_file(self):
        buf = generate_calendar_image(self.guild_id, self.year, self.month)
        file = discord.File(buf, filename="calendar.png")
        embed = discord.Embed(title="📋 請假月曆", color=discord.Color.orange())
        embed.set_image(url="attachment://calendar.png")
        embed.set_footer(text="格子數字為當天請假人數；下方選單可查看是誰")
        return embed, file

    async def refresh(self, interaction: discord.Interaction):
        self.build_day_select()
        embed, file = self.make_embed_and_file()
        await interaction.response.edit_message(embed=embed, attachments=[file], view=self)

    @discord.ui.button(label="上月", style=discord.ButtonStyle.secondary, emoji="◀", row=0)
    async def prev_month(self, interaction: discord.Interaction, button: Button):
        self.shift_month(-1)
        await self.refresh(interaction)

    @discord.ui.button(label="下月", style=discord.ButtonStyle.secondary, emoji="▶", row=0)
    async def next_month(self, interaction: discord.Interaction, button: Button):
        self.shift_month(1)
        await self.refresh(interaction)

    async def day_selected(self, interaction: discord.Interaction):
        date_str = interaction.data['values'][0]
        leaves = get_all_leaves(self.guild_id)
        names = [u['username'] for u in leaves.get(date_str, [])]
        if names:
            desc = "\n".join(f"• {n}" for n in names)
            embed = discord.Embed(
                title=f"📅 {date_str} 的請假名單（{len(names)}人）",
                description=desc,
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title=f"📅 {date_str}",
                description="這天目前沒有人請假",
                color=discord.Color.blue()
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class RecurringCancelConfirmView(View):
    """停止定期請假的確認：一律停止規則，只問本月已請的假要不要一起刪掉"""
    def __init__(self, user_id: int, guild_id: int, weekday: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self.weekday = weekday

    async def _do_cancel(self, interaction: discord.Interaction, delete_leaves: bool):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        name = WEEKDAY_NAMES[self.weekday]
        now = datetime.now()

        remove_user_weekday(self.guild_id, self.user_id, self.weekday)  # 一律停止定期

        if delete_leaves:
            removed = remove_recurring_leaves(self.guild_id, self.user_id, self.weekday, now.year, now.month)
            tail = f"本月（{now.month}月）已請的 **{removed}** 天週{name}也一併刪除。"
        else:
            kept = count_user_recurring_leaves(self.guild_id, self.user_id, self.weekday, now.year, now.month)
            tail = f"本月（{now.month}月）已請的 **{kept}** 天週{name}保留不變。"

        log.info(
            f"停止定期請假：{interaction.user}（{interaction.user.id}）每周{name}，"
            f"delete_leaves={delete_leaves}"
        )
        embed = discord.Embed(
            title=f"✅ 已停止每周{name}的定期請假",
            description=f"下個月起不會再自動排入。\n{tail}",
            color=discord.Color.green()
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)

    @discord.ui.button(label="停止定期 ＋ 刪除當月假", style=discord.ButtonStyle.danger, row=0)
    async def stop_and_delete(self, interaction: discord.Interaction, button: Button):
        await self._do_cancel(interaction, delete_leaves=True)

    @discord.ui.button(label="停止定期 ＋ 保留當月假", style=discord.ButtonStyle.primary, row=0)
    async def stop_and_keep(self, interaction: discord.Interaction, button: Button):
        await self._do_cancel(interaction, delete_leaves=False)

    @discord.ui.button(label="返回", style=discord.ButtonStyle.secondary, row=1)
    async def go_back(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        view = CancelLeaveView(self.user_id, self.guild_id)
        await interaction.response.edit_message(
            content="請選擇要取消的請假：", embed=None, view=view
        )


class CancelLeaveView(View):
    """取消請假檢視 - 定期請假（每周X）置頂，其餘為一般日期"""
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self.build_select()

    def build_select(self):
        for item in list(self.children):
            if isinstance(item, Select):
                self.remove_item(item)

        options = []
        # 定期請假置頂，優先級最高
        for wd in get_user_weekdays(self.guild_id, self.user_id):
            options.append(discord.SelectOption(
                label=f"每周{WEEKDAY_NAMES[wd]}（定期請假）",
                value=f"recurring:{wd}",
                emoji="🔁",
                description="取消本月的每周定期請假"
            ))
        # 其餘名額給一般日期（選單上限 25）
        for d in get_user_leaves(self.guild_id, self.user_id)[:25 - len(options)]:
            options.append(discord.SelectOption(label=d, value=f"date:{d}"))

        if options:
            sel = Select(placeholder="選擇要取消的請假...", options=options)
            sel.callback = self.cancel_selected
            self.add_item(sel)

    async def cancel_selected(self, interaction: discord.Interaction):
        value = interaction.data['values'][0]

        # 定期請假 → 先跳確認
        if value.startswith("recurring:"):
            weekday = int(value.split(":", 1)[1])
            name = WEEKDAY_NAMES[weekday]
            now = datetime.now()
            pending = count_user_recurring_leaves(self.guild_id, self.user_id, weekday, now.year, now.month)
            embed = discord.Embed(
                title=f"🔁 停止定期請假：每周{name}",
                description=(
                    f"將停止每周{name}的定期請假，下個月起不再自動排入。\n\n"
                    f"你本月（{now.month}月）今天起還有 **{pending}** 天已請好的週{name}，"
                    "要一起刪除嗎？\n\n"
                    "• **刪除當月假** → 連本月已請的一起清掉\n"
                    "• **保留當月假** → 本月已請的照常，只是之後不再自動排入"
                ),
                color=discord.Color.orange()
            )
            await interaction.response.edit_message(
                content=None, embed=embed,
                view=RecurringCancelConfirmView(self.user_id, self.guild_id, weekday)
            )
            return

        # 一般日期
        date_str = value.split(":", 1)[1]
        ok = remove_leave(self.guild_id, self.user_id, date_str)
        self.build_select()
        remaining = get_user_leaves(self.guild_id, self.user_id)
        if ok:
            log.info(f"取消請假：{interaction.user}（{interaction.user.id}）→ {date_str}")
            content = f"✅ 已取消 {date_str} 的請假"
        else:
            content = "⚠️ 找不到該請假紀錄（可能已被取消）"
        if not remaining:
            content += "\n你目前已沒有其他請假。"
        await interaction.response.edit_message(content=content, view=self)

        # 取消的是「今天」的請假 → 發出公開提醒
        if ok and datetime.strptime(date_str, "%Y-%m-%d").date() == datetime.now().date():
            n = len(load_leaves(self.guild_id).get(date_str, []))
            if n > 0:
                tail = f"還有 {n} 人於今日請假"
                color = discord.Color.gold()
            else:
                tail = "今天無人請假"
                color = discord.Color.green()
            embed = discord.Embed(
                title="📢 有人取消請假",
                description=f"**{interaction.user.name}** 取消了今天（{date_str}）的請假，{tail}",
                color=color
            )
            await interaction.channel.send(embed=embed)


async def _panel_guard(interaction: discord.Interaction) -> bool:
    """面板互動守衛：未授權或已暫停就擋下，回傳 True 代表可繼續"""
    gid = interaction.guild_id
    if gid is None or not is_authorized(gid):
        await interaction.response.send_message(
            "❌ 這個伺服器尚未取得使用授權，請聯繫機器人擁有者。", ephemeral=True
        )
        return False
    if not is_enabled(gid):
        await interaction.response.send_message(
            "⏸️ 機器人在這個伺服器目前為暫停狀態。", ephemeral=True
        )
        return False
    return True


class PersistentPanelView(View):
    """持久面板 - 機器人重啟後依然有效"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="請假申請", style=discord.ButtonStyle.primary, custom_id="panel_leave", emoji="📅")
    async def leave_button(self, interaction: discord.Interaction, _button: Button):
        if not await _panel_guard(interaction):
            return
        calendar_view = CalendarView(interaction.user.id, interaction.guild_id)
        embed = discord.Embed(
            title="📅 請假日曆",
            description="請選擇要請假的日期",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=calendar_view, ephemeral=True)

    @discord.ui.button(label="查看請假", style=discord.ButtonStyle.secondary, custom_id="panel_view", emoji="📋")
    async def view_button(self, interaction: discord.Interaction, button: Button):
        if not await _panel_guard(interaction):
            return
        now = datetime.now()
        view = LeaveCalendarView(interaction.guild_id, now.year, now.month)
        embed, file = view.make_embed_and_file()
        await interaction.response.send_message(embed=embed, view=view, file=file, ephemeral=True)

    @discord.ui.button(label="取消請假", style=discord.ButtonStyle.danger, custom_id="panel_cancel", emoji="✖️")
    async def cancel_button(self, interaction: discord.Interaction, button: Button):
        if not await _panel_guard(interaction):
            return
        gid = interaction.guild_id
        dates = get_user_leaves(gid, interaction.user.id)
        weekdays = get_user_weekdays(gid, interaction.user.id)
        if not dates and not weekdays:
            await interaction.response.send_message("📭 你目前沒有可取消的請假", ephemeral=True)
            return
        view = CancelLeaveView(interaction.user.id, gid)
        await interaction.response.send_message(
            "請選擇要取消的請假：", view=view, ephemeral=True
        )


def _active_guild_ids():
    """已授權且啟用的伺服器 ID 清單（字串）"""
    return [gid for gid in get_authorized_guilds() if is_enabled(int(gid))]


def _get_panel_channel(guild_id):
    ch_id = get_panel_channel_id(guild_id)
    return bot.get_channel(ch_id) if ch_id else None


@tasks.loop(time=time(hour=0, minute=5, tzinfo=TW_TZ))
async def daily_archive():
    """每天（台灣時間）凌晨 00:05 把過去的請假搬到封存檔（每個授權伺服器）"""
    for gid in _active_guild_ids():
        count = archive_past_leaves(int(gid))
        if count:
            log.info(f"[{gid}] 已封存 {count} 天過期的請假資料")


@tasks.loop(time=time(hour=9, minute=0, tzinfo=TW_TZ))
async def daily_reminder():
    """每天（台灣時間）早上 9:00：1 號先產生定期假，再提醒今天誰請假（每個授權伺服器）"""
    now = datetime.now(TW_TZ)
    today = now.strftime("%Y-%m-%d")

    for gid in _active_guild_ids():
        guild_id = int(gid)
        # 每月 1 號：先產生本月定期假（順序很重要，1 號剛好是定期日時也會被提醒到）
        if now.day == 1:
            await _generate_monthly_recurring(guild_id, now.year, now.month)

        channel = _get_panel_channel(guild_id)
        if channel is None:
            log.warning(f"[{gid}] 找不到面板頻道，無法發送今日請假提醒")
            continue

        today_list = load_leaves(guild_id).get(today, [])
        if today_list:
            names = '、'.join(u['username'] for u in today_list)
            embed = discord.Embed(
                title="📢 今日請假提醒",
                description=f"今天（{today}）請假的有：\n{names}",
                color=discord.Color.red()
            )
        else:
            embed = discord.Embed(
                title="📢 今日請假提醒",
                description=f"今天（{today}）無人請假，有團練 🎶",
                color=discord.Color.green()
            )
        await channel.send(embed=embed)
        log.info(f"[{gid}] 已發送今日請假提醒（{today}，{len(today_list)} 人）")


async def _generate_monthly_recurring(guild_id, year, month):
    """為某伺服器所有人產生該月定期假，並在頻道發一則總結（不 @ 任何人）"""
    users, total = generate_all_recurring_for_month(guild_id, year, month)
    if not total:
        return
    log.info(f"[{guild_id}] 每月定期請假已產生：{year}-{month:02d}，{users} 人共 {total} 天")

    channel = _get_panel_channel(guild_id)
    if channel is None:
        return
    embed = discord.Embed(
        title="📅 本月定期請假已設定完成",
        description=(
            f"已為 **{users}** 位成員排入本月（{month}月）的定期請假，共 **{total}** 天。\n"
            "可點擊面板的「查看請假」查看月曆。"
        ),
        color=discord.Color.blue()
    )
    await channel.send(embed=embed)


def migrate_legacy_data():
    """把舊的全域資料（data/leaves.json 等）搬進面板頻道所屬的伺服器資料夾"""
    legacy_config = os.path.join(DATA_DIR, 'config.json')
    legacy_leaves = os.path.join(DATA_DIR, 'leaves.json')
    # 判斷是否為舊格式：config.json 內含 panel_channel_id（新格式是 authorized_guilds）
    if not os.path.exists(legacy_leaves):
        return
    old_cfg = _load(legacy_config, {})
    if 'panel_channel_id' not in old_cfg:
        return  # 已是新格式或無舊設定，不處理

    ch_id = old_cfg.get('panel_channel_id')
    channel = bot.get_channel(ch_id) if ch_id else None
    if channel is None or channel.guild is None:
        log.warning("舊資料遷移：無法從面板頻道判斷所屬伺服器，暫不遷移（資料保留原處）")
        return

    guild_id = channel.guild.id
    ensure_guild_files(guild_id)
    # 搬移三個資料檔
    for name in (LEAVES_NAME, ARCHIVE_NAME, RECURRING_NAME):
        src = os.path.join(DATA_DIR, name)
        if os.path.exists(src):
            data = _load(src, {})
            _save(_guild_path(guild_id, name), data)
            os.remove(src)
    # 建立該伺服器設定
    set_panel_channel_id(guild_id, ch_id)
    set_enabled(guild_id, True)
    # 把舊全域 config（panel_channel_id）就地覆寫成新格式（authorized_guilds）
    # 注意：舊 config 與新全域 config 是同一個檔（data/config.json），不能刪除
    save_global_config({'authorized_guilds': [str(guild_id)]})
    log.info(f"舊資料已遷移到伺服器 {channel.guild.name}（{guild_id}）並自動授權")


@bot.event
async def on_ready():
    log.info(f'{bot.user} 已連接到 Discord')
    migrate_legacy_data()
    bot.add_view(PersistentPanelView())
    log.info("持久面板已註冊")
    # 啟動時先封存一次，之後每天定時封存
    for gid in _active_guild_ids():
        archive_past_leaves(int(gid))
    if not daily_archive.is_running():
        daily_archive.start()
    if not daily_reminder.is_running():
        daily_reminder.start()
    log.info(f"已授權伺服器：{get_authorized_guilds()}；每日任務已啟動")


@bot.event
async def on_command_error(ctx, error):
    """統一的指令錯誤處理"""
    if isinstance(error, commands.CommandNotFound):
        pass  # 打錯指令名就安靜忽略，不洗 log
    elif isinstance(error, (commands.CheckFailure, commands.MissingPermissions)):
        # 權限不足（含自訂的 owner_only / owner_or_manage_guild）
        await ctx.send("❌ 你沒有權限使用此指令", delete_after=10)
    else:
        log.error(f"指令錯誤（{ctx.command}）：{error}")


class StatusView(View):
    """狀態卡片下方的暫停/恢復按鈕（僅本人可操作）"""
    def __init__(self, user_id: int, guild_id: int):
        super().__init__(timeout=120)
        self.user_id = user_id
        self.guild_id = guild_id
        self._refresh_button()

    def _refresh_button(self):
        self.clear_items()
        enabled = is_enabled(self.guild_id)
        btn = Button(
            label="暫停機器人" if enabled else "恢復機器人",
            emoji="⏸️" if enabled else "▶️",
            style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
        )
        btn.callback = self.toggle
        self.add_item(btn)

    async def toggle(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        new_state = not is_enabled(self.guild_id)
        set_enabled(self.guild_id, new_state)
        log.info(f"[{self.guild_id}] {interaction.user} 將機器人切換為 {'啟用' if new_state else '暫停'}")
        self._refresh_button()
        await interaction.response.edit_message(
            embed=_build_status_embed(interaction.guild), view=self
        )


def _build_status_embed(guild):
    gid = guild.id
    enabled = is_enabled(gid)
    ch_id = get_panel_channel_id(gid)
    leaves = load_leaves(gid)
    recurring = load_recurring(gid)
    leave_days = len(leaves)
    leave_people = sum(len(v) for v in leaves.values())

    embed = discord.Embed(
        title="🤖 機器人狀態",
        color=discord.Color.green() if enabled else discord.Color.light_grey()
    )
    embed.add_field(name="伺服器", value=guild.name, inline=False)
    embed.add_field(name="狀態", value="✅ 運作中" if enabled else "⏸️ 已暫停", inline=True)
    embed.add_field(
        name="面板頻道",
        value=f"<#{ch_id}>" if ch_id else "尚未設定",
        inline=True
    )
    embed.add_field(name="現用請假", value=f"{leave_days} 天 / {leave_people} 人次", inline=True)
    embed.add_field(name="定期請假", value=f"{len(recurring)} 人", inline=True)
    embed.set_footer(text="下方按鈕可暫停 / 恢復本伺服器的機器人")
    return embed


@bot.command(name='授權')
@owner_only()
async def authorize_cmd(ctx):
    """授權目前伺服器使用機器人（僅機器人擁有者）"""
    if ctx.guild is None:
        await ctx.send("請在伺服器內使用此指令")
        return
    added = authorize_guild(ctx.guild.id)
    ensure_guild_files(ctx.guild.id)
    if added:
        log.info(f"擁有者授權伺服器：{ctx.guild.name}（{ctx.guild.id}）")
        await ctx.send(f"✅ 已授權「{ctx.guild.name}」使用機器人，請用 `!設置面板` 開始設定")
    else:
        await ctx.send("ℹ️ 這個伺服器已經授權過了")


@bot.command(name='取消授權')
@owner_only()
async def deauthorize_cmd(ctx):
    """取消目前伺服器的使用授權（僅機器人擁有者）"""
    if ctx.guild is None:
        return
    if deauthorize_guild(ctx.guild.id):
        log.info(f"擁有者取消授權伺服器：{ctx.guild.name}（{ctx.guild.id}）")
        await ctx.send(f"✅ 已取消「{ctx.guild.name}」的授權，機器人在此伺服器將停止運作")
    else:
        await ctx.send("ℹ️ 這個伺服器本來就沒有授權")


@bot.command(name='狀態')
@owner_or_manage_guild()
async def status_cmd(ctx):
    """顯示機器人狀態並可暫停/恢復（需管理伺服器權限，僅本人可見）"""
    if ctx.guild is None:
        return
    if not is_authorized(ctx.guild.id):
        await ctx.send("❌ 這個伺服器尚未取得使用授權，請聯繫機器人擁有者", delete_after=10)
        return
    view = StatusView(ctx.author.id, ctx.guild.id)
    await ctx.send(embed=_build_status_embed(ctx.guild), view=view, ephemeral=True)


@bot.command(name='設置面板')
async def setup_panel(ctx):
    """發送請假面板：管理員可指定頻道；一般人只能在管理員指定的頻道張貼"""
    if ctx.guild is None:
        return
    guild_id = ctx.guild.id
    if not is_authorized(guild_id):
        await ctx.send("❌ 這個伺服器尚未取得使用授權，請聯繫機器人擁有者", delete_after=10)
        return

    is_admin = await _is_owner(ctx.author) or ctx.author.guild_permissions.manage_guild
    designated = get_panel_channel_id(guild_id)

    if is_admin:
        # 管理員「起個頭 / 更改頻道」：把當前頻道設為指定頻道
        set_panel_channel_id(guild_id, ctx.channel.id)
        log.info(f"[{guild_id}] 面板設置＋指定頻道更新：{ctx.author} 於 {ctx.channel}（{ctx.channel.id}）")
    else:
        # 一般人只能在管理員指定的頻道張貼面板
        if designated is None:
            await ctx.send("⚠️ 尚未由管理員指定面板頻道，請先請管理員執行 !設置面板", delete_after=10)
            return
        if ctx.channel.id != designated:
            await ctx.send("❌ 只能在管理員指定的頻道設置面板", delete_after=10)
            return
        log.info(f"[{guild_id}] 面板已張貼（指定頻道）：{ctx.author} 於 {ctx.channel}")

    embed = discord.Embed(
        title="🏢 請假系統",
        description="使用下方按鈕申請請假、查看記錄或取消自己的請假",
        color=discord.Color.green()
    )
    embed.set_footer(text="每日請假提醒會發送到此頻道")
    await ctx.send(embed=embed, view=PersistentPanelView())


@bot.command(name='清空請假')
@owner_or_manage_guild()
async def clear_leaves(ctx):
    """清空目前（今天與未來）的請假記錄，歷史封存保留（需管理伺服器權限）"""
    if ctx.guild is None:
        return
    if not is_authorized(ctx.guild.id):
        await ctx.send("❌ 這個伺服器尚未取得使用授權", delete_after=10)
        return
    save_leaves(ctx.guild.id, {})
    log.info(f"[{ctx.guild.id}] 清空請假：{ctx.author}（{ctx.author.id}）")
    await ctx.send("✅ 已清空目前（今天與未來）的請假記錄\n（過去的歷史封存仍保留）")


# 運行bot
if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        log.error("未找到有效的 DISCORD_TOKEN，請確保 .env 檔案中有 DISCORD_TOKEN=你的token")
        exit(1)
    log.info(f"Token 已載入，長度: {len(token)}")
    # log_handler=None：不讓 discord.py 另外加 handler，統一由我們的設定輸出
    bot.run(token, log_handler=None)
