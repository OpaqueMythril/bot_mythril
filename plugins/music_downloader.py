import os
import re
import httpx
import asyncio
from pathlib import Path
from nonebot import on_regex, logger, get_driver
from nonebot.adapters.onebot.v11 import GroupMessageEvent, MessageSegment, Bot
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="网易云音乐下载器",
    description="检测群内网易云音乐链接并自动解析发送 MP3 文件",
    usage="直接发送网易云音乐分享链接（支持短链和歌曲 ID）"
)

# ================= 配置区域 =================
config = get_driver().config

# 1. 唯一授权群号（从 .env 读取，杜绝硬编码）
AUTHORIZED_GROUP = int(getattr(config, "music_downloader_group", "0"))

# 2. 靠谱的第三方免费网易云解析 API（若失效可更换其他公开公益 API）
# 该 API 传入 id 即可返回包含歌曲播放链接的 JSON
NETEASE_API_URL = "https://api.uomg.com/api/rand.music"

# 3. 临时文件存放路径
DATA_DIR = Path(__file__).parent.parent / "data" / "music_tmp"
DATA_DIR.mkdir(parents=True, exist_ok=True)
# ===========================================

# 💡 正则表达式：匹配网易云音乐的各种链接形式（支持手机分享的 163cn.tv 短链，以及 song?id= 数字形式）
music_regex = r"(music\.163\.com/.*song\?id=(\d+))|(163cn\.tv/[a-zA-Z0-9]+)"
music_matcher = on_regex(music_regex, priority=5, block=True)


async def get_real_song_id(url: str) -> str:
    """如果收到的是短链，需要追踪重定向获取真实的歌曲 ID"""
    if "163cn.tv" in url:
        if not url.startswith("http"):
            url = "https://" + url
        try:
            async with httpx.AsyncClient(follow_redirects=False, timeout=5.0) as client:
                resp = await client.get(url)
                # 从重定向的 Location 头中抓取真实链接
                location = resp.headers.get("Location", "")
                match = re.search(r"id=(\d+)", location)
                if match:
                    return match.group(1)
        except Exception as e:
            logger.error(f"[音乐下载] 解析短链重定向失败: {e}")
    else:
        match = re.search(r"id=(\d+)", url)
        if match:
            return match.group(1)
    return ""


@music_matcher.handle()
async def handle_music_download(bot: Bot, event: GroupMessageEvent):
    # 💡 门禁：只在特定群聊生效
    if event.group_id != AUTHORIZED_GROUP:
        return

    raw_msg = event.get_plaintext().strip()

    # 1. 提取消息里的链接
    url_match = re.search(r"(https?://[^\s]+)", raw_msg)
    if not url_match:
        # 如果是纯文本卡片（有些高版本 QQ 协议端解析出来的格式），尝试直接捞匹配到的 ID
        # regex 的 groups 包含了正则捕获组
        matched_groups = event.get_log_string()  # 辅助兜底
        url_text = raw_msg
    else:
        url_text = url_match.group(1)

    await music_matcher.send("🐾 嗅到了网易云的味儿... 本喵正戴上耳机帮你偷轨，稍等喵！")

    # 2. 获取真实的歌曲 ID
    song_id = await get_real_song_id(url_text)
    if not song_id:
        # 兜底：如果直接从消息里能强行匹配出数字
        digits = re.findall(r"id=(\d+)", raw_msg)
        if digits:
            song_id = digits[0]
        else:
            await music_matcher.finish("❌ 艾玛，这链接伪装得太深，本喵抓不到歌曲 ID！")

    # 3. 请求 API 获取 MP3 真实下载直链
    mp3_url = ""
    song_name = f"music_{song_id}"
    try:
        params = {"sort": "热歌", "format": "json"}  # 某些公益 API 的特殊参数
        # 更好的策略：直接请求标准的第三方解析网易云接口
        # 这里使用一个更直接的解析接口：
        api_url = f"https://api.i-meto.com/meting/api?server=netease&type=url&id={song_id}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(api_url)
            if resp.status_code == 200:
                res_data = resp.json()
                # Meting API 返回的是一个列表，里面直接有 url
                if isinstance(res_data, list) and len(res_data) > 0:
                    mp3_url = res_data[0].get("url")
                    # 尝试拿歌名
                    song_name = res_data[0].get("name", song_name)
    except Exception as e:
        logger.error(f"[音乐下载] API 解析出错: {e}")

    # 💡 备用 API 路由兜底
    if not mp3_url:
        try:
            backup_url = f"https://api.uomg.com/api/rand.music?mid={song_id}&format=json"
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(backup_url)
                if resp.status_code == 200:
                    res_json = resp.json()
                    if res_json.get("code") == 1:
                        data_node = res_json.get("data", {})
                        mp3_url = data_node.get("url")
                        song_name = data_node.get("name", song_name)
        except Exception as e:
            logger.error(f"[音乐下载] 备用 API 解析也失败了: {e}")

    if not mp3_url:
        await music_matcher.finish("❌ 完蛋，各大赛博音乐库都拒绝了本喵的偷听请求，解析失败！")

    # 4. 异步流式下载 MP3 文件到磁盘（绝不占用大量内存）
    file_path = DATA_DIR / f"{song_name}.mp3"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with client.stream("GET", mp3_url) as response:
                if response.status_code != 200:
                    await music_matcher.finish(f"❌ 下载失败，源站不给数据，状态码: {response.status_code}")

                with open(file_path, "wb") as f:
                    async for chunk in response.iter_bytes(chunk_size=8192):
                        f.write(chunk)

        # 5. 发送语音或文件（这里使用 MessageSegment.record 发送语音卡片，或者用常规文件发送）
        # 群聊内最稳妥直接的办法是直接发语音，或者发文件。这里选择发语音段（Record）
        # 如果你想在 QQ 里直接能播放，MessageSegment.record 是最爽的
        await music_matcher.send(f"🎵 成功捕获《{song_name}》！这就唱歌给你听喵~")
        await music_matcher.finish(MessageSegment.record(file_path))

    except Exception as e:
        logger.error(f"[音乐下载] 下载或发送中途暴毙: {e}")
        await music_matcher.finish(f"❌ 赛博声道沙哑，发送失败了喵: {str(e)}")

    finally:
        # 💡 生产级运维：无论成功还是暴毙，绝对不能留着垃圾占领你 1.92GB 的小磁盘！
        if file_path.exists():
            try:
                os.remove(file_path)
                logger.info(f"[音乐下载] 临时文件 {file_path.name} 已自动物理抹除。")
            except Exception as delete_error:
                logger.error(f"[音乐下载] 清理临时文件失败: {delete_error}")