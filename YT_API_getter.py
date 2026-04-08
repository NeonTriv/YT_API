import discord
from discord.ext import tasks, commands
import requests
import json
import os
from dotenv import load_dotenv
from keep_alive import keep_alive

# --- TẢI BIẾN MÔI TRƯỜNG TỪ FILE .env ---
load_dotenv()

# --- 1. CẤU HÌNH THÔNG TIN (ĐÃ GIẤU KÍN) ---
TOKEN = os.getenv('DISCORD_TOKEN')
YT_API_KEY = os.getenv('YOUTUBE_API_KEY')
CHANNEL_ID = os.getenv('CHANNEL_ID')
DISCORD_CHANNEL_ID = int(os.getenv('DISCORD_CHANNEL_ID', 0))

# --- 2. THIẾT LẬP BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "channel_stats.json"

MILESTONES = {
    "subscribers": [100, 500, 1000, 5000, 10000, 50000, 100000, 500000, 1000000],
    "views": [1000, 5000, 10000, 50000, 100000, 500000, 1000000, 5000000, 10000000]
}

# --- 3. THUẬT TOÁN TÍNH ĐIỂM ---
def calculate_points(amount):
    if amount <= 0: return 0
    points = 0
    previous_limit = 0
    base_limits = [1, 5, 10]
    base_multipliers = [1, 2, 5]
    power = 2 
    
    while amount > previous_limit:
        for i in range(len(base_limits)):
            current_limit = base_limits[i] * (10 ** power)
            current_multiplier = base_multipliers[i] * (10 ** (power - 2))
            
            if current_limit <= previous_limit:
                continue

            if amount > previous_limit:
                chunk = min(amount, current_limit) - previous_limit
                points += chunk * current_multiplier
                previous_limit = current_limit
            else:
                break
        power += 1 
    return int(points)

def load_stats():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {"subscriberCount": 0, "viewCount": 0, "videoCount": 0}

def save_stats(stats):
    with open(DATA_FILE, "w") as f:
        json.dump(stats, f)

# --- 4. LOGIC KIỂM TRA YOUTUBE ---
@tasks.loop(minutes=30)
async def check_channel_stats():
    print("Đang kiểm tra thông số kênh YouTube...")
    url = f"https://www.googleapis.com/youtube/v3/channels?part=statistics,snippet&id={CHANNEL_ID}&key={YT_API_KEY}"
    
    try:
        response = requests.get(url)
        data = response.json()
        
        if "items" in data and len(data["items"]) > 0:
            channel_data = data["items"][0]
            stats = channel_data["statistics"]
            snippet = channel_data["snippet"]
            
            current_subs = int(stats.get("subscriberCount", 0))
            current_views = int(stats.get("viewCount", 0))
            channel_name = snippet.get("title", "Kênh của bạn")
            
            saved_stats = load_stats()
            old_subs = saved_stats.get("subscriberCount", 0)
            old_views = saved_stats.get("viewCount", 0)
            
            channel = bot.get_channel(DISCORD_CHANNEL_ID)
            
            sub_points = calculate_points(current_subs)
            view_points = calculate_points(current_views)
            
            # KIỂM TRA MỐC SUBSCRIBER
            for milestone in sorted(MILESTONES["subscribers"], reverse=True):
                if old_subs < milestone and current_subs >= milestone:
                    if channel:
                        await channel.send(
                            f"🎉 **ĐỘT PHÁ!** Kênh **{channel_name}** vừa đạt mốc **{milestone:,} Subs!**\n"
                            f"✨ Tích lũy được tổng cộng: **{sub_points:,} Điểm Subs** 📈"
                        )
                    break 
                    
            # KIỂM TRA MỐC LƯỢT XEM
            for milestone in sorted(MILESTONES["views"], reverse=True):
                if old_views < milestone and current_views >= milestone:
                    if channel:
                        await channel.send(
                            f"🔥 **CHÁY QUÁ!** Kênh **{channel_name}** vừa cán mốc **{milestone:,} Views!**\n"
                            f"🌟 Tích lũy được tổng cộng: **{view_points:,} Điểm Views** 🚀"
                        )
                    break
            
            save_stats({
                "subscriberCount": current_subs,
                "viewCount": current_views,
                "videoCount": int(stats.get("videoCount", 0))
            })
            print(f"Cập nhật: {current_subs} subs ({sub_points} pts) | {current_views} views ({view_points} pts)")
            
    except Exception as e:
        print(f"Đã xảy ra lỗi khi gọi API: {e}")

# --- 5. LỆNH KIỂM TRA THỦ CÔNG ---
@bot.command(name="stats")
async def check_stats_manual(ctx):
    stats = load_stats()
    subs = stats.get('subscriberCount', 0)
    views = stats.get('viewCount', 0)
    
    sub_pts = calculate_points(subs)
    view_pts = calculate_points(views)
    
    msg = (f"📊 **BÁO CÁO TÌNH HÌNH KÊNH:**\n"
           f"👥 Subs: **{subs:,}** ➡️ Điểm: **{sub_pts:,} pts**\n"
           f"👁️ Views: **{views:,}** ➡️ Điểm: **{view_pts:,} pts**\n"
           f"🎬 Số video: **{stats.get('videoCount', 0)}**")
    await ctx.send(msg)

# --- 6. CHẠY BOT ---
@bot.event
async def on_ready():
    print(f'Bot {bot.user} đã kết nối và sẵn sàng!')
    if not check_channel_stats.is_running():
        check_channel_stats.start()

if __name__ == "__main__":
    if TOKEN is None:
        print("LỖI: Chưa tìm thấy TOKEN! Hãy kiểm tra lại file .env")
    else:
        keep_alive() # Bật web server chống ngủ đông
        bot.run(TOKEN)