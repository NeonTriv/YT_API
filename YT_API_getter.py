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
JSONBIN_ID = os.getenv('JSONBIN_ID')
JSONBIN_KEY = os.getenv('JSONBIN_KEY')
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_ID}"

# --- 3. QUY TẮC MỐC SUBSCRIBER ---
def generate_subscriber_milestone_rules(max_power=10):
    rules = [(1, 100, 1)]

    # Từ 100 trở đi, các dải giữ nguyên pattern và chỉ scale thêm số 0.
    for power in range(2, max_power + 1):
        base = 10 ** power
        rules.append((base, 5 * base, 2 * (10 ** (power - 2))))
        rules.append((5 * base, 10 * base, 5 * (10 ** (power - 2))))

    last_base = 10 ** max_power
    rules.append((last_base, float("inf"), 2 * (10 ** (max_power - 2))))
    return rules


SUBSCRIBER_MILESTONE_RULES = generate_subscriber_milestone_rules()


def generate_view_milestones(max_power=10):
    milestones = []
    for power in range(3, max_power + 1):
        base = 10 ** power
        milestones.extend([base, 5 * base])
    return milestones


VIEW_MILESTONES = generate_view_milestones()


def get_crossed_subscriber_milestones(old_subs, current_subs):
    if current_subs <= old_subs:
        return []

    crossed = []
    start_global = old_subs + 1
    end_global = current_subs

    for band_start, band_end, step in SUBSCRIBER_MILESTONE_RULES:
        band_effective_end = end_global if band_end == float("inf") else min(end_global, band_end - 1)
        band_effective_start = max(start_global, band_start)

        if band_effective_start > band_effective_end:
            continue

        remainder = band_effective_start % step
        first_milestone = band_effective_start if remainder == 0 else band_effective_start + (step - remainder)

        if first_milestone <= band_effective_end:
            crossed.extend(range(first_milestone, band_effective_end + 1, step))

    return crossed


def get_crossed_view_milestones(old_views, current_views):
    return [m for m in VIEW_MILESTONES if old_views < m <= current_views]

def load_stats():
    """Tải dữ liệu từ đám mây JSONBin"""
    if not JSONBIN_ID or not JSONBIN_KEY:
        return {"subscriberCount": 0, "viewCount": 0, "videoCount": 0}

    headers = {'X-Master-Key': JSONBIN_KEY}
    try:
        req = requests.get(JSONBIN_URL, headers=headers)
        data = req.json()
        return data.get('record', {"subscriberCount": 0, "viewCount": 0, "videoCount": 0})
    except Exception as e:
        print(f"Lỗi đọc JSONBin: {e}")
        return {"subscriberCount": 0, "viewCount": 0, "videoCount": 0}


def save_stats(stats):
    """Lưu dữ liệu mới lên JSONBin"""
    if not JSONBIN_ID or not JSONBIN_KEY:
        return

    headers = {
        'Content-Type': 'application/json',
        'X-Master-Key': JSONBIN_KEY
    }
    try:
        requests.put(JSONBIN_URL, json=stats, headers=headers)
    except Exception as e:
        print(f"Lỗi lưu JSONBin: {e}")

# --- 4. LOGIC KIỂM TRA YOUTUBE ---
@tasks.loop(minutes=15)
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
            crossed_sub_milestones = get_crossed_subscriber_milestones(old_subs, current_subs)
            crossed_view_milestones = get_crossed_view_milestones(old_views, current_views)

            if (crossed_sub_milestones or crossed_view_milestones) and not channel:
                print("Không tìm thấy channel Discord để gửi chúc mừng. Chưa lưu stats để tránh mất mốc.")
                return

            # KIỂM TRA MỐC SUBSCRIBER
            for milestone in crossed_sub_milestones:
                if channel:
                    await channel.send(
                        f"🎉 **CHÚC MỪNG!** Kênh **{channel_name}** vừa đạt mốc **{milestone:,} Subs!**"
                    )
                    
            # KIỂM TRA MỐC LƯỢT XEM
            for milestone in crossed_view_milestones:
                if channel:
                    await channel.send(
                        f"🔥 **CHÁY QUÁ!** Kênh **{channel_name}** vừa cán mốc **{milestone:,} Views!**"
                    )
            
            save_stats({
                "subscriberCount": current_subs,
                "viewCount": current_views,
                "videoCount": int(stats.get("videoCount", 0))
            })
            print(f"Cập nhật: {current_subs} subs | {current_views} views")
            
    except Exception as e:
        print(f"Đã xảy ra lỗi khi gọi API: {e}")

# --- 5. LỆNH KIỂM TRA THỦ CÔNG ---
@bot.command(name="ytstats")
async def check_stats_manual(ctx):
    stats = load_stats()
    subs = stats.get('subscriberCount', 0)
    views = stats.get('viewCount', 0)
    
    msg = (f"📊 **BÁO CÁO TÌNH HÌNH KÊNH:**\n"
           f"👥 Subs: **{subs:,}** \n"
           f"👁️ Views: **{views:,}** \n"
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