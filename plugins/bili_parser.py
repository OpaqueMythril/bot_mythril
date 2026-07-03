import re
import os
import json
import uuid
import random
import asyncio
import base64
import httpx
from pathlib import Path
from typing import Optional, Tuple, List, Any
from nonebot import on_message, logger, get_driver
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent, Message, MessageSegment
from nonebot.exception import FinishedException, ActionFailed
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="B站链接解析器 Ultimate HD",
    description="全通道B站链接捕获 → 高画质720P/1080P下载 → 时长熔断 → base64直传",
    usage="直接发送或分享 B站视频链接/小程序卡片/Ark分享卡片即可自动触发"
)

# ============================================================
#  配置读取
# ============================================================
config = get_driver().config
BILI_COOKIE = str(getattr(config, "bili_cookie", "")).strip().strip('"').strip("'")

# 高画质档位: 有 Cookie → qn=80 (1080P), 无 Cookie → qn=32 (480P)
VIDEO_QN = 80 if BILI_COOKIE else 32
VIDEO_QN_LABEL = "1080P" if BILI_COOKIE else "480P"

# 时长熔断线 (秒): 超过此值拒绝下载，仅发图文卡片
MAX_DURATION = 300

# ============================================================
#  正则
# ============================================================
SHORT_LINK_RE = re.compile(r"https?://b23\.tv/[a-zA-Z0-9]+", re.IGNORECASE)
BV_RE = re.compile(r"BV[a-zA-Z0-9]+")
FULL_URL_RE = re.compile(r"https?://(?:www\.)?bilibili\.com/video/(BV[a-zA-Z0-9]+)", re.IGNORECASE)

BILI_VIEW_API = "https://api.bilibili.com/x/web-interface/view"
BILI_PLAYURL_API = "https://api.bilibili.com/x/player/playurl"

TMP_DIR = Path("/tmp/mybot_video")
TMP_DIR.mkdir(parents=True, exist_ok=True)
os.chmod(str(TMP_DIR), 0o777)

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache", "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "Sec-Ch-Ua-Mobile": "?0", "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "same-site",
    "Connection": "keep-alive",
}

GUEST_COOKIE = "buvid3=infoc; b_nut=1; _uuid=infoc; buvid4=infoc; b_lsid=infoc; buvid_fp=infoc"

DOWNLOAD_HEADERS = {
    "User-Agent": BROWSER_HEADERS["User-Agent"],
    "Referer": "https://www.bilibili.com/",
    "Origin": "https://www.bilibili.com",
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "identity",
    "Sec-Fetch-Dest": "video", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Site": "cross-site",
}


def fmt_count(n: int) -> str:
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    return str(n)


def fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        m, s = divmod(seconds, 60)
        return f"{m}分{s}秒" if s else f"{m}分钟"
    else:
        h, r = divmod(seconds, 3600)
        m, s = divmod(r, 60)
        return f"{h}小时{m}分{s}秒" if s else f"{h}小时{m}分钟"


def truncate(text: str, limit: int = 60) -> str:
    if not text:
        return "（暂无简介）"
    cleaned = text.replace("\n", " ").replace("\r", " ")
    if len(cleaned) > limit:
        return cleaned[:limit] + "..."
    return cleaned


def _extract_strings_from_json(obj: Any, depth: int = 0) -> List[str]:
    results: List[str] = []
    if depth > 8:
        return results
    if isinstance(obj, str):
        results.append(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            results.extend(_extract_strings_from_json(v, depth + 1))
    elif isinstance(obj, list):
        for item in obj:
            results.extend(_extract_strings_from_json(item, depth + 1))
    return results


def extract_text_pool(event: MessageEvent) -> str:
    parts: List[str] = []

    plain = event.get_plaintext().strip()
    if plain:
        parts.append(plain)

    for seg in event.message:
        seg_type = seg.type
        seg_data = seg.data

        try:
            raw_dump = json.dumps(seg_data, ensure_ascii=False)
            if raw_dump and raw_dump != "{}":
                parts.append(raw_dump)
        except Exception:
            pass

        if seg_type in ("json", "ark"):
            raw_json = seg_data.get("data", "") or seg_data.get("text", "") or seg_data.get("content", "")
            if raw_json:
                parts.append(raw_json)
                try:
                    obj = json.loads(raw_json)
                    all_strings = _extract_strings_from_json(obj)
                    for s in all_strings:
                        if s and len(s) > 5:
                            parts.append(s)
                    meta = obj.get("meta", {}) if isinstance(obj, dict) else {}
                    if isinstance(meta, dict):
                        for key in ("jumpUrl", "url", "share_url", "qqdocurl",
                                     "detail_1", "detail", "desc", "title",
                                     "appUrl", "sourceUrl", "targetUrl", "actionUrl"):
                            val = meta.get(key, "")
                            if isinstance(val, str) and val:
                                parts.insert(0, val)
                    if isinstance(obj, dict):
                        for key in ("jumpUrl", "url", "share_url", "qqdocurl",
                                     "appUrl", "sourceUrl", "targetUrl", "actionUrl", "prompt"):
                            val = obj.get(key, "")
                            if isinstance(val, str) and val:
                                parts.insert(0, val)
                except (json.JSONDecodeError, TypeError):
                    pass

        elif seg_type == "xml":
            raw_xml = seg_data.get("data", "") or seg_data.get("text", "")
            if raw_xml:
                parts.append(raw_xml)

        elif seg_type == "image":
            summary = seg_data.get("summary", "")
            if summary:
                parts.append(summary)

    full_text = "\n".join(parts)
    if not full_text:
        full_text = str(event.message)
    return full_text


def extract_candidates(text: str) -> Tuple[Optional[str], Optional[str]]:
    m = FULL_URL_RE.search(text)
    if m:
        return (None, m.group(1))
    m = SHORT_LINK_RE.search(text)
    if m:
        return (m.group(0), None)
    m = BV_RE.search(text)
    if m:
        return (None, m.group(0))
    return (None, None)


async def resolve_short_url(short_url: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as c:
            r = await c.head(short_url, headers={
                "User-Agent": BROWSER_HEADERS["User-Agent"],
                "Accept": BROWSER_HEADERS["Accept"],
                "Accept-Language": BROWSER_HEADERS["Accept-Language"],
            })
            loc = r.headers.get("Location", "")
            if loc:
                bv = extract_bvid_from_url(loc)
                if bv:
                    return bv
            r2 = await c.get(short_url, headers={
                "User-Agent": BROWSER_HEADERS["User-Agent"],
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": BROWSER_HEADERS["Accept-Language"],
            })
            if r2.status_code == 200:
                bv = extract_bvid_from_url(str(r2.url))
                if bv:
                    return bv
                mm = BV_RE.search(r2.text)
                if mm:
                    return mm.group(0)
    except Exception as e:
        logger.error(f"[BiliParser] 短链异常: {e}")
    return None


def extract_bvid_from_url(url: str) -> Optional[str]:
    m = BV_RE.search(url)
    return m.group(0) if m else None


# ============================================================
#  B站 API — 视频详情 (含 duration 提取)
# ============================================================
async def fetch_video_info(bvid: str) -> Optional[dict]:
    h = dict(BROWSER_HEADERS)
    h["Cookie"] = BILI_COOKIE if BILI_COOKIE else GUEST_COOKIE
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(BILI_VIEW_API, params={"bvid": bvid}, headers=h)
            if r.status_code != 200:
                return None
            d = r.json()
            if d.get("code") != 0:
                return None
            return d["data"]
    except Exception:
        return None


async def fetch_video_download_url(bvid: str, cid: int) -> Optional[str]:
    h = dict(BROWSER_HEADERS)
    h["Cookie"] = BILI_COOKIE if BILI_COOKIE else GUEST_COOKIE
    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(BILI_PLAYURL_API, params={
                "bvid": bvid, "cid": cid,
                "qn": VIDEO_QN,
                "fnval": 1,           # 非 DASH 直链 (MP4/FLV)
                "fnver": 0,
                "fourk": 1 if BILI_COOKIE else 0,
                "platform": "html5",
                "high_quality": 1,
            }, headers=h)
            if r.status_code != 200:
                return None
            d = r.json()
            if d.get("code") != 0:
                logger.error(f"[BiliParser] playurl code={d.get('code')} msg={d.get('message')}")
                return None
            durl = d.get("data", {}).get("durl", [])
            if durl and durl[0].get("url"):
                return durl[0]["url"]
    except Exception:
        return None
    return None


async def download_flv(url: str, dest: Path) -> bool:
    try:
        async with httpx.AsyncClient(timeout=180.0, follow_redirects=True) as c:
            async with c.stream("GET", url, headers=dict(DOWNLOAD_HEADERS)) as r:
                if r.status_code not in (200, 206):
                    logger.error(f"[BiliParser] 下载 HTTP {r.status_code}")
                    return False
                with open(dest, "wb") as f:
                    async for chunk in r.aiter_bytes(65536):
                        f.write(chunk)
                size = dest.stat().st_size
                logger.info(f"[BiliParser] FLV 下载完成: {size} bytes ({size/1024/1024:.1f}MB)")
                return size > 0
    except Exception as e:
        logger.error(f"[BiliParser] 下载异常: {type(e).__name__}: {e}")
    return False


async def convert_to_mp4(flv_path: Path, mp4_path: Path) -> bool:
    cmd = [
        "ffmpeg", "-y",
        "-i", str(flv_path),
        "-c:v", "libx264", "-profile:v", "baseline", "-level", "3.0",
        "-pix_fmt", "yuv420p",
        "-vf", "scale='min(480,iw)':-2",
        "-r", "15",
        "-c:a", "aac", "-b:a", "64k", "-ar", "22050", "-ac", "1",
        "-movflags", "+faststart",
        "-preset", "ultrafast", "-crf", "30",
        "-maxrate", "300k", "-bufsize", "600k",
        str(mp4_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120.0)
        if proc.returncode == 0 and mp4_path.exists() and mp4_path.stat().st_size > 0:
            logger.info(f"[BiliParser] ffmpeg 转码成功: {mp4_path.stat().st_size / 1024 / 1024:.1f}MB")
            return True
        else:
            err = (stderr or b"").decode("utf-8", errors="replace")[-300:]
            logger.error(f"[BiliParser] ffmpeg 失败: {err}")
            return False
    except asyncio.TimeoutError:
        logger.error("[BiliParser] ffmpeg 超时")
        return False
    except Exception as e:
        logger.error(f"[BiliParser] ffmpeg 异常: {type(e).__name__}: {e}")
        return False


def safe_remove(path: str) -> None:
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def build_hud_card(info: dict, extra_note: str = "") -> Tuple[str, str]:
    title = info.get("title", "未知标题")
    cover_url = info.get("pic", "")
    up_name = info.get("owner", {}).get("name", "未知UP")
    stat = info.get("stat", {})
    vc = fmt_count(stat.get("view", 0))
    dc = fmt_count(stat.get("danmaku", 0))
    desc = truncate(info.get("desc", ""))
    duration = info.get("duration", 0)
    dur_str = fmt_duration(duration)

    card = (
        "[BILI_LINK_DETECTED]_\n"
        "────────────────────────────\n"
        f"标题: {title}\n"
        f"UP主: {up_name} | 播放: {vc} | 弹幕: {dc} | 时长: {dur_str}\n"
        f"简介: {desc}\n"
        "────────────────────────────"
    )
    if extra_note:
        card += f"\n{extra_note}"
    return card, cover_url


EASTER_EGGS = [
    "特呵呵呵，本喵帮你扒下来了，还不快谢谢我！(^з^)-☆",
    "艾玛，又是B站... 你这上班摸鱼也太明显了喵！( ´▽` )",
    "哼，本喵才不是特意帮你解析的，只是顺手罢了！🐾",
    "给你给你！看完记得给本喵喂小鱼干！(〃∇〃)",
    "火斑喵雷达已锁定！这个视频... 勉为其难帮你看看吧~",
    "连视频都给你转码扒来了，本喵简直是赛博海盗喵！🏴‍☠️",
    "高画质已就绪！群里直接点开看！特呵呵呵~",
]

LONG_VIDEO_EGGS = [
    "火斑喵才懒得帮你搬运整个硬盘，自己点链接去看喵！🐾",
    "艾玛，这视频也太长了，本喵的2C2G小身板可扛不住！( ` 皿´ )",
    "时长超标！本喵拒绝搬运这种庞然大物，图文情报拿好不谢~",
]


async def has_bili_content(event: MessageEvent) -> bool:
    text_pool = extract_text_pool(event)
    short_url, bvid = extract_candidates(text_pool)
    return short_url is not None or bvid is not None


bili_matcher = on_message(rule=Rule(has_bili_content), priority=5, block=True)


@bili_matcher.handle()
async def handle_bili_link(bot: Bot, event: MessageEvent):
    text_pool = extract_text_pool(event)
    short_url, bvid = extract_candidates(text_pool)

    logger.info(f"[BiliParser] 触发 short={short_url} bvid={bvid} qn={VIDEO_QN}({VIDEO_QN_LABEL})")
    await bili_matcher.send("🐾 火斑喵正在破译 B 站流媒体轨道...")

    if short_url and not bvid:
        bvid = await resolve_short_url(short_url)
        if not bvid:
            fb = BV_RE.search(text_pool)
            bvid = fb.group(0) if fb else None
            if not bvid:
                await bili_matcher.finish("艾玛，短链追踪失败了！")

    if not bvid:
        await bili_matcher.finish("艾玛，没找到 BV 号！")

    info = await fetch_video_info(bvid)
    if not info:
        await bili_matcher.finish(f"艾玛，B站把本喵拦下来了！BV [{bvid}] 可能不存在喵...")

    pages = info.get("pages", [])
    cid = pages[0].get("cid", 0) if pages else 0
    title = info.get("title", bvid)
    duration = info.get("duration", 0)

    # ================================================================
    #  时长熔断判定
    # ================================================================
    if duration > MAX_DURATION:
        logger.info(f"[BiliParser] ⏱️ 时长熔断: {duration}s > {MAX_DURATION}s, 仅发图文卡片")
        card_text, cover_url = build_hud_card(info)
        note = random.choice(LONG_VIDEO_EGGS)
        card_msg = Message()
        card_msg += MessageSegment.text(card_text + "\n")
        if cover_url:
            card_msg += MessageSegment.image(cover_url)
            card_msg += MessageSegment.text("\n")
        card_msg += MessageSegment.text(f"🐾 火斑喵提示：这只视频太长了（{fmt_duration(duration)}），本喵才懒得帮你搬运整个硬盘，自己点链接去看喵！")
        await bili_matcher.finish(card_msg)

    # ================================================================
    #  短视频: 高画质下载 + 发送
    # ================================================================
    flv_path = None
    mp4_path = None

    if cid:
        video_url = await fetch_video_download_url(bvid, cid)
        if video_url:
            uid = uuid.uuid4().hex[:8]
            flv_path = TMP_DIR / f"{bvid}_{uid}.flv"
            mp4_path = TMP_DIR / f"{bvid}_{uid}.mp4"

            logger.info(f"[BiliParser] ⬇️ 下载 {VIDEO_QN_LABEL} 视频, 时长={fmt_duration(duration)}")
            if await download_flv(video_url, flv_path):
                if not await convert_to_mp4(flv_path, mp4_path):
                    mp4_path = None
            else:
                flv_path = None
        else:
            logger.warning("[BiliParser] 未获取到视频下载直链")

    # --- HUD 卡片 ---
    card_text, cover_url = build_hud_card(info)
    egg = random.choice(EASTER_EGGS)
    card_msg = Message()
    card_msg += MessageSegment.text(card_text + "\n")
    if cover_url:
        card_msg += MessageSegment.image(cover_url)
        card_msg += MessageSegment.text("\n")
    card_msg += MessageSegment.text(egg)
    await bili_matcher.send(card_msg)

    # --- base64 视频直传 ---
    if mp4_path and mp4_path.exists():
        abs_path = str(mp4_path.absolute())
        mp4_size = mp4_path.stat().st_size
        logger.info(f"[BiliParser] base64 直传 {VIDEO_QN_LABEL}: {abs_path} ({mp4_size} bytes)")

        try:
            with open(abs_path, "rb") as f:
                video_bytes = f.read()
            b64_data = base64.b64encode(video_bytes).decode("ascii")
            await bot.send(
                event=event,
                message=Message(MessageSegment.video(file=f"base64://{b64_data}")),
            )
            logger.info(f"[BiliParser] {VIDEO_QN_LABEL} base64:// 视频已发送")
        except ActionFailed as e:
            logger.error(f"[BiliParser] base64 发送失败: {e}")
        except Exception as e:
            logger.error(f"[BiliParser] base64 异常: {type(e).__name__}: {e}")

        await asyncio.sleep(8)
        safe_remove(str(mp4_path))
        if flv_path and flv_path.exists():
            safe_remove(str(flv_path))
    else:
        if flv_path and flv_path.exists():
            safe_remove(str(flv_path))
