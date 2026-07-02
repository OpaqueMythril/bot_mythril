import httpx
import base64
import re
from typing import Union

from nonebot import on_message, logger, get_driver
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="赛博锐评",
    description="识别图片并给出傲娇评价",
    usage="引用图片或发图时带上关键词：评价/分析/看图/这是啥"
)

# ================= 配置读取（从 .env 动态加载，杜绝硬编码）=================
config = get_driver().config
SILICONFLOW_API_KEY = str(getattr(config, "ai_api_key", "")).strip().strip('"').strip("'")
SILICONFLOW_BASE_URL = str(getattr(config, "ai_base_url", "https://api.siliconflow.cn/v1")).strip().strip('"').strip("'")
MODEL_ID = str(getattr(config, "ai_vision_model", "Qwen/Qwen3-VL-32B-Instruct")).strip().strip('"').strip("'")

if not SILICONFLOW_API_KEY:
    logger.error("[赛博锐评] 未配置 AI_API_KEY，图片评价功能将不可用！请在 .env 中设置 AI_API_KEY")


# ================= 触发规则 =================
async def check_is_eval(event: MessageEvent) -> bool:
    """同时满足【关键词】+【消息或引用中有图】才触发"""
    content = event.get_plaintext().strip()
    keywords = ["评价", "分析", "看图", "这是啥"]

    has_keyword = any(k in content for k in keywords)
    if not has_keyword:
        return False

    has_image = any(seg.type == "image" for seg in event.message)
    if not has_image and event.reply:
        has_image = any(seg.type == "image" for seg in event.reply.message)

    return has_keyword and has_image


analyze_matcher = on_message(rule=Rule(check_is_eval), priority=5, block=True)


@analyze_matcher.handle()
async def handle_eval(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    if not SILICONFLOW_API_KEY:
        await analyze_matcher.finish("艾玛，本喵的视觉神经还没接上，API Key 没配置好喵！")

    # 提取图片 URL
    img_url = ""
    for seg in event.message:
        if seg.type == "image":
            img_url = seg.data["url"]
            break

    if not img_url and event.reply:
        for seg in event.reply.message:
            if seg.type == "image":
                img_url = seg.data["url"]
                break

    if not img_url:
        return

    await analyze_matcher.send("👁️ 本喵正在接入视觉神经，别急...")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 下载图片并转 base64
            img_resp = await client.get(img_url)
            if img_resp.status_code != 200:
                await analyze_matcher.finish("艾玛，图片被赛博黑洞吞了，抓不到！")

            base64_img = base64.b64encode(img_resp.content).decode("utf-8")

            api_url = f"{SILICONFLOW_BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
                "Content-Type": "application/json"
            }

            persona = """你现在是智能马桶Bot（火斑喵）。性格：傲娇、毒舌但可爱、口嫌体正直。
口头禅：特呵呵呵、艾玛、喵。
任务：请精准描述图片内容，并给出你极具个性、傲娇且带有温度的评价。
注意：严禁使用 Markdown 符号（如 ***），回复纯文本即可。"""

            payload = {
                "model": MODEL_ID,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": persona},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}
                            }
                        ]
                    }
                ],
                "max_tokens": 512,
                "temperature": 0.7
            }

            response = await client.post(api_url, json=payload, headers=headers, timeout=60)

            if response.status_code == 200:
                final_text = response.json()["choices"][0]["message"]["content"]
                final_text = re.sub(r"\*+", "", final_text).strip()
                await analyze_matcher.finish(f"👁️ 本喵看法如下：\n\n{final_text}")
            else:
                logger.error(f"[赛博锐评] API 返回 {response.status_code}: {response.text}")
                await analyze_matcher.finish(f"艾玛，眼睛看累了（错误码 {response.status_code}）")

    except FinishedException:
        raise
    except httpx.TimeoutException:
        await analyze_matcher.finish("艾玛，图片太大，本喵眼睛看花了（超时）！")
    except Exception as e:
        logger.error(f"[赛博锐评] 视觉分析出错: {str(e)}")
        await analyze_matcher.finish(f"本喵眼疾发作：{str(e)}")
