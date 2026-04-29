import discord
from discord.ext import commands
from discord.ui import View, Button, Select
import json
import os
from datetime import datetime, timedelta
import calendar
from dotenv import load_dotenv

# 載入 .env 檔案
load_dotenv()

# 設置bot意圖
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# 數據檔案路徑
DATA_FILE = 'data/leaves.json'

def ensure_data_file():
    """確保數據檔案存在"""
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

def load_leaves():
    """載入請假數據"""
    ensure_data_file()
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_leaves(data):
    """保存請假數據"""
    ensure_data_file()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_leave(user_id, username, date_str):
    """新增請假記錄"""
    leaves = load_leaves()
    if date_str not in leaves:
        leaves[date_str] = []
    leaves[date_str].append({'user_id': user_id, 'username': username})
    save_leaves(leaves)

def get_leaves_on_date(date_str):
    """獲取某天的請假資訊"""
    leaves = load_leaves()
    return leaves.get(date_str, [])

class CalendarView(View):
    """日曆選擇檢視"""
    def __init__(self, user_id: int, year: int = None, month: int = None):
        super().__init__()
        self.user_id = user_id
        if year is None or month is None:
            now = datetime.now()
            self.year = now.year
            self.month = now.month
        else:
            self.year = year
            self.month = month
        
        self.setup_buttons()
    
    def setup_buttons(self):
        """設置日曆按鈕"""
        self.clear_items()
        
        # 第一行：前月、月份、後月
        prev_button = Button(label="◀ 上月", style=discord.ButtonStyle.primary)
        prev_button.callback = self.prev_month
        self.add_item(prev_button)
        
        month_button = Button(label=f"{self.year}年{self.month}月", style=discord.ButtonStyle.secondary, disabled=True)
        self.add_item(month_button)
        
        next_button = Button(label="下月 ▶", style=discord.ButtonStyle.primary)
        next_button.callback = self.next_month
        self.add_item(next_button)
        
        # 日期選擇菜單（限制 25 個選項）
        options = []
        cal = calendar.monthcalendar(self.year, self.month)
        
        for week in cal:
            for day in week:
                if day != 0:  # 只添加有效的日期
                    date_obj = datetime(self.year, self.month, day)
                    day_name = ['一', '二', '三', '四', '五', '六', '日'][date_obj.weekday()]
                    options.append(
                        discord.SelectOption(
                            label=f"{day:2d}日 ({day_name})",
                            value=f"{self.year}-{self.month:02d}-{day:02d}"
                        )
                    )
        
        # 限制選項數量不超過 25
        if options:
            select = discord.ui.Select(
                placeholder="選擇要請假的日期...",
                options=options[:25],  # 只取前 25 個
                custom_id=f"date_select_{self.user_id}"
            )
            select.callback = self.date_selected
            self.add_item(select)
    
    async def prev_month(self, interaction: discord.Interaction):
        """上一個月"""
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.defer()
                return
            
            if self.month == 1:
                self.month = 12
                self.year -= 1
            else:
                self.month -= 1
            
            self.setup_buttons()
            await interaction.response.edit_message(view=self)
        except Exception as e:
            print(f"❌ 前月錯誤：{e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except:
                pass
    
    async def next_month(self, interaction: discord.Interaction):
        """下一個月"""
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.defer()
                return
            
            if self.month == 12:
                self.month = 1
                self.year += 1
            else:
                self.month += 1
            
            self.setup_buttons()
            await interaction.response.edit_message(view=self)
        except Exception as e:
            print(f"❌ 後月錯誤：{e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.defer()
            except:
                pass
    
    async def date_selected(self, interaction: discord.Interaction):
        """選擇日期"""
        try:
            if interaction.user.id != self.user_id:
                await interaction.response.defer()
                return
            
            date_str = interaction.data['values'][0]
            
            # 保存請假記錄
            add_leave(interaction.user.id, interaction.user.name, date_str)
            
            # 立即響應交互
            await interaction.response.send_message(
                f"✅ 已記錄請假日期：{date_str}\n使用者：{interaction.user.name}",
                ephemeral=True
            )
        except Exception as e:
            print(f"❌ 日期選擇錯誤：{e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ 發生錯誤：{e}", ephemeral=True)
            except:
                pass

class LeaveButtonView(View):
    """請假主菜單檢視"""
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id
    
    @discord.ui.button(label="請假申請", style=discord.ButtonStyle.blurple)
    async def leave_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """請假申請按鈕"""
        # 檢查是否是正確的使用者
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        
        try:
            print(f"📌 用戶 {interaction.user.name} 點擊了請假申請按鈕")
            
            # 顯示日曆
            calendar_view = CalendarView(interaction.user.id)
            embed = discord.Embed(
                title="📅 請假日曆",
                description="請選擇要請假的日期",
                color=discord.Color.blue()
            )
            embed.set_footer(text="只有你能看到這個訊息")
            
            print(f"📌 準備發送日曆訊息給 {interaction.user.name}")
            
            # 使用 send_message 直接回應
            await interaction.response.send_message(
                embed=embed,
                view=calendar_view,
                ephemeral=True
            )
            
            print(f"✅ 日曆訊息已發送給 {interaction.user.name}")
        except Exception as e:
            print(f"❌ 錯誤：{type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ 發生錯誤：{e}", ephemeral=True)
            except Exception as e2:
                print(f"❌ 無法發送錯誤訊息：{e2}")

@bot.event
async def on_ready():
    """機器人已準備就緒"""
    print(f'{bot.user} 已連接到Discord')
    ensure_data_file()

@bot.command(name='請假')
async def leave_command(ctx):
    """請假命令 - 顯示請假菜單"""
    embed = discord.Embed(
        title="🏢 請假系統",
        description="你好",
        color=discord.Color.green()
    )
    embed.set_footer(text="點擊下方按鈕開始請假流程")
    
    view = LeaveButtonView(ctx.author.id)
    await ctx.send(embed=embed, view=view)

@bot.command(name='查看請假')
async def view_leaves(ctx):
    """查看請假資訊"""
    leaves = load_leaves()
    
    if not leaves:
        await ctx.send("📭 暫無請假記錄")
        return
    
    # 建立嵌入式訊息
    embed = discord.Embed(
        title="📋 請假記錄",
        description="顯示所有請假申請",
        color=discord.Color.orange()
    )
    
    # 按日期排序
    sorted_dates = sorted(leaves.keys())
    
    for date_str in sorted_dates:
        users = leaves[date_str]
        user_names = ', '.join([user['username'] for user in users])
        embed.add_field(
            name=date_str,
            value=user_names,
            inline=False
        )
    
    await ctx.send(embed=embed)

@bot.command(name='清空請假')
@commands.has_permissions(administrator=True)
async def clear_leaves(ctx):
    """清空所有請假記錄（僅管理員）"""
    save_leaves({})
    await ctx.send("✅ 已清空所有請假記錄")

# 運行bot
if __name__ == '__main__':
    # 從環境變數讀取token，或直接替換這裡
    token = os.getenv('DISCORD_TOKEN')
    
    # 調試：檢查 token 是否存在
    if not token:
        print("❌ 錯誤：未找到有效的 DISCORD_TOKEN")
        print("請確保 .env 檔案中有 DISCORD_TOKEN=你的token")
        exit(1)
    
    print(f"✅ Token 已載入，長度: {len(token)}")
    print(f"Token 前綴: {token[:20]}...")
    bot.run(token)
