import discord
from discord.ext import commands
from discord.ui import View, Button, Select
import json
import os
from datetime import datetime
import calendar
from dotenv import load_dotenv

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

DATA_FILE = 'data/leaves.json'

def ensure_data_file():
    if not os.path.exists('data'):
        os.makedirs('data')
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

def load_leaves():
    ensure_data_file()
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_leaves(data):
    ensure_data_file()
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def add_leave(user_id, username, date_str):
    leaves = load_leaves()
    if date_str not in leaves:
        leaves[date_str] = []
    # 防止重複請假
    for entry in leaves[date_str]:
        if entry['user_id'] == user_id:
            return False
    leaves[date_str].append({'user_id': user_id, 'username': username})
    save_leaves(leaves)
    return True


class CalendarView(View):
    """日曆選擇檢視 - 使用年、月、上/下半月、日期選擇"""
    def __init__(self, user_id: int):
        super().__init__()
        self.user_id = user_id
        now = datetime.now()
        self.year = now.year
        self.month = now.month
        self.is_second_half = False
        self.setup_selects()

    def setup_selects(self):
        self.clear_items()

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

        first_half = Button(
            label=f"上半月 (1-{mid_day}日)",
            style=discord.ButtonStyle.primary if not self.is_second_half else discord.ButtonStyle.secondary,
            custom_id=f"first_half_{self.user_id}",
            row=2
        )
        first_half.callback = self.show_first_half
        self.add_item(first_half)

        second_half = Button(
            label=f"下半月 ({mid_day + 1}-{max_day}日)",
            style=discord.ButtonStyle.primary if self.is_second_half else discord.ButtonStyle.secondary,
            custom_id=f"second_half_{self.user_id}",
            row=2
        )
        second_half.callback = self.show_second_half
        self.add_item(second_half)

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
        self.setup_selects()
        await interaction.response.edit_message(view=self)

    async def show_second_half(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        self.is_second_half = True
        self.setup_selects()
        await interaction.response.edit_message(view=self)

    async def date_selected(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.defer()
            return
        date_str = interaction.data['values'][0]
        if datetime.strptime(date_str, "%Y-%m-%d").date() < datetime.now().date():
            await interaction.response.send_message("❌ 不能申請過去的日期", ephemeral=True)
            return
        success = add_leave(interaction.user.id, interaction.user.name, date_str)
        if success:
            await interaction.response.send_message(
                f"✅ 已記錄請假日期：{date_str}\n使用者：{interaction.user.name}",
                ephemeral=True
            )
        else:
            await interaction.response.send_message(
                f"⚠️ 你已經申請過 {date_str} 的請假了",
                ephemeral=True
            )


class PersistentPanelView(View):
    """持久面板 - 機器人重啟後依然有效"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="請假申請", style=discord.ButtonStyle.primary, custom_id="panel_leave", emoji="📅")
    async def leave_button(self, interaction: discord.Interaction, _button: Button):
        calendar_view = CalendarView(interaction.user.id)
        embed = discord.Embed(
            title="📅 請假日曆",
            description="請選擇要請假的日期",
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, view=calendar_view, ephemeral=True)

    @discord.ui.button(label="查看請假", style=discord.ButtonStyle.secondary, custom_id="panel_view", emoji="📋")
    async def view_button(self, interaction: discord.Interaction, button: Button):
        leaves = load_leaves()
        if not leaves:
            await interaction.response.send_message("📭 暫無請假記錄", ephemeral=True)
            return

        embed = discord.Embed(
            title="📋 請假記錄",
            description="所有請假申請",
            color=discord.Color.orange()
        )
        for date_str in sorted(leaves.keys()):
            user_names = ', '.join([u['username'] for u in leaves[date_str]])
            embed.add_field(name=date_str, value=user_names, inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="清空請假", style=discord.ButtonStyle.danger, custom_id="panel_clear", emoji="🗑️")
    async def clear_button(self, interaction: discord.Interaction, button: Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ 只有管理員才能清空請假記錄", ephemeral=True)
            return
        save_leaves({})
        await interaction.response.send_message("✅ 已清空所有請假記錄", ephemeral=True)


@bot.event
async def on_ready():
    print(f'{bot.user} 已連接到Discord')
    ensure_data_file()
    bot.add_view(PersistentPanelView())
    print("✅ 持久面板已註冊")


@bot.command(name='設置面板')
@commands.has_permissions(administrator=True)
async def setup_panel(ctx):
    """在當前頻道發送持久請假面板（管理員）"""
    embed = discord.Embed(
        title="🏢 請假系統",
        description="使用下方按鈕申請請假、查看記錄或清空資料",
        color=discord.Color.green()
    )
    embed.set_footer(text="清空功能僅管理員可用")
    await ctx.send(embed=embed, view=PersistentPanelView())
    await ctx.message.delete()


# 運行bot
if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ 錯誤：未找到有效的 DISCORD_TOKEN")
        print("請確保 .env 檔案中有 DISCORD_TOKEN=你的token")
        exit(1)
    print(f"✅ Token 已載入，長度: {len(token)}")
    bot.run(token)
