import httpx
import json
from io import BytesIO
from PIL import Image, ImageOps
from nonebot import on_command, get_driver, logger
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Message, MessageSegment, MessageEvent
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="绘图大师",
    description="AI 文字生图与本地图片黑白处理",
    usage="/画图 [描述] — AI 生成图片; /黑白 — 将图片转为黑白"
)

# ================= 配置读取（从 .env 动态加载，杜绝硬编码）=================
config = get_driver().config
SILICONFLOW_API_KEY = str(getattr(config, "ai_api_key", "")).strip().strip('"').strip("'")
SILICONFLOW_BASE_URL = str(getattr(config, "ai_base_url", "https://api.siliconflow.cn/v1")).strip().strip('"').strip("'")

if not SILICONFLOW_API_KEY:
    logger.error("[绘图大师] 未配置 AI_API_KEY，AI 生图功能将不可用！请在 .env 中设置 AI_API_KEY")

# ================= 功能 1: AI 文字生图 =================
draw_cmd = on_command("画图", aliases={"generate", "绘图"}, priority=5, block=True)

@draw_cmd.handle()
async def handle_draw(arg: Message = CommandArg()):
    prompt = arg.extract_plain_text().strip()
    if not prompt:
        await draw_cmd.finish("艾玛，你得告诉我画什么啊！笨蛋！")

    if not SILICONFLOW_API_KEY:
        await draw_cmd.finish("艾玛，本喵的 API 密钥还没配置好，画不了画！")

    await draw_cmd.send(f"本喵正在构思「{prompt}」，等我两秒...")

    api_url = f"{SILICONFLOW_BASE_URL}/images/generations"
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "Kwai-Kolors/Kolors",
        "prompt": prompt,
        "batch_size": 1
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(api_url, json=payload, headers=headers)

            if response.status_code == 200:
                data = response.json()
                image_url = data["images"][0]["url"]
                await draw_cmd.finish(MessageSegment.image(image_url))
            else:
                logger.error(f"[绘图大师] API 返回非 200: {response.status_code} — {response.text}")
                await draw_cmd.finish(f"艾玛，画崩了，错误码 {response.status_code}")

    except FinishedException:
        raise
    except httpx.TimeoutException:
        await draw_cmd.finish("艾玛，画布还没干就超时了，再试一次喵！")
    except Exception as e:
        logger.error(f"[绘图大师] AI 生图异常: {e}")
        await draw_cmd.finish(f"本喵画崩了，错误在这：{e}")


# ================= 功能 2: 本地图片黑白化 =================
gray_cmd = on_command("黑白", priority=5, block=True)

@gray_cmd.handle()
async def handle_gray(event: MessageEvent):
    img_url = ""
    # 优先从回复消息中提取图片
    if event.reply:
        for seg in event.reply.message:
            if seg.type == "image":
                img_url = seg.data["url"]
                break

    if not img_url:
        for seg in event.message:
            if seg.type == "image":
                img_url = seg.data["url"]
                break

    if not img_url:
        await gray_cmd.finish("艾玛，你得发张图或者回复一张图啊！( ` 皿´ )")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(img_url)
            if resp.status_code != 200:
                await gray_cmd.finish(f"艾玛，图片下载失败，状态码 {resp.status_code}")

            img = Image.open(BytesIO(resp.content))
            gray_img = ImageOps.grayscale(img)

            out_io = BytesIO()
            gray_img.save(out_io, format="JPEG")

            await gray_cmd.finish(MessageSegment.image(out_io.getvalue()))

    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"[绘图大师] 黑白化失败: {e}")
        await gray_cmd.finish(f"图片整容失败：{str(e)}")
