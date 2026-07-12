import re
import json
import io
import httpx
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from nonebot import on_command, logger, get_driver
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, MessageSegment, Message
from nonebot.params import CommandArg
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="AI人性化润色",
    description="调用大模型去除文本中的 AI 痕迹，多维度评分表格+修改说明",
    usage="/humanize [文本] 或 回复消息 /humanize 或 发送文件后 /humanize"
)

SKILL_PATH = Path(__file__).parent / "SKILL.md"
FONT_PATH = str(Path(__file__).parent.parent.parent / "data" / "simhei.ttf")
MAX_CHARS = 10000

config = get_driver().config
API_KEY = str(getattr(config, "ai_api_key", "")).strip().strip('"').strip("'")
BASE_URL = str(getattr(config, "ai_base_url", "https://api.siliconflow.cn/v1")).strip().strip('"').strip("'")
MODEL = str(getattr(config, "ai_model", "deepseek-ai/DeepSeek-V3")).strip().strip('"').strip("'")

if not API_KEY:
    logger.error("[Humanize] AI_API_KEY 未配置!")


def load_skill() -> str:
    try:
        return SKILL_PATH.read_text(encoding="utf-8")
    except Exception as e:
        logger.error(f"[Humanize] 读取 SKILL.md 失败: {e}")
        return ""


def build_user_prompt(original_text: str) -> str:
    return (
        "请对以下文本进行人性化润色，去除 AI 痕迹。完成后严格按以下 JSON 格式输出，不要输出任何额外内容：\n\n"
        "{\n"
        '  "humanized_text": "润色后的完整文本",\n'
        '  "changes": "你做了哪些主要修改的简要说明",\n'
        '  "scores": {\n'
        '    "directness":   {"score": 9, "note": "开门见山，无冗长铺垫"},\n'
        '    "rhythm":       {"score": 9, "note": "句子长短变化自然，有叙述感"},\n'
        '    "trust":        {"score": 9, "note": "尊重读者认知，不过度解释"},\n'
        '    "authenticity": {"score": 10, "note": "带有个人情绪与人性化表达"},\n'
        '    "conciseness":  {"score": 8, "note": "少量冗余可删，但整体清晰"}\n'
        "  }\n"
        "}\n\n"
        "scores 每项 score 为 1-10 的整数，note 为简短说明。五个维度的满分合计 50 分。\n\n"
        f"待润色文本：\n{original_text}"
    )


async def call_llm(system_prompt: str, user_text: str) -> dict:
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": 0.75,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"},
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            f"{BASE_URL}/chat/completions", json=payload, headers=headers,
        )
        if resp.status_code != 200:
            logger.error(f"[Humanize] API HTTP {resp.status_code}: {resp.text[:300]}")
            return {}

        data = resp.json()
        raw = data["choices"][0]["message"]["content"].strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.error(f"[Humanize] JSON 解析失败: {raw[:300]}")
            return {
                "humanized_text": raw,
                "changes": "（模型未按 JSON 格式输出）",
                "scores": {},
            }


def generate_score_table(scores_dict: dict, char_count: int) -> bytes:
    dims = [
        ("directness",   "直接性"),
        ("rhythm",       "节奏"),
        ("trust",        "信任度"),
        ("authenticity", "真实性"),
        ("conciseness",  "精炼度"),
    ]

    try:
        font_hdr   = ImageFont.truetype(FONT_PATH, 20)
        font_row   = ImageFont.truetype(FONT_PATH, 16)
        font_sm    = ImageFont.truetype(FONT_PATH, 13)
        font_title = ImageFont.truetype(FONT_PATH, 22)
    except Exception:
        font_hdr = font_row = font_sm = font_title = ImageFont.load_default()

    row_h, hdr_h, title_h, footer_h = 28, 34, 38, 42
    total_w, pad_x = 620, 20
    col1_w, col2_w = 110, 50
    col1_x = pad_x
    col2_x = col1_x + col1_w
    col3_x = col2_x + col2_w

    n_rows = len(dims)
    total_h = title_h + hdr_h + n_rows * row_h + footer_h

    img = Image.new("RGBA", (total_w, total_h), (26, 27, 34, 255))
    draw = ImageDraw.Draw(img)

    # 标题栏
    draw.rectangle([0, 0, total_w, title_h], fill=(36, 38, 50, 255))
    draw.text((pad_x, 9), "📊 人性化润色质量评估", font=font_title, fill=(255, 255, 255, 255))

    # 表头
    hdr_y = title_h
    draw.rectangle([0, hdr_y, total_w, hdr_y + hdr_h], fill=(46, 48, 62, 255))
    draw.text((col1_x + 4, hdr_y + 7), "维度", font=font_hdr, fill=(200, 200, 215, 255))
    draw.text((col2_x + 4, hdr_y + 7), "得分", font=font_hdr, fill=(200, 200, 215, 255))
    draw.text((col3_x + 4, hdr_y + 7), "说明", font=font_hdr, fill=(200, 200, 215, 255))
    draw.line([(pad_x, hdr_y + hdr_h), (total_w - pad_x, hdr_y + hdr_h)],
              fill=(65, 66, 80, 255), width=1)

    total_score = 0
    for i, (key, label) in enumerate(dims):
        ry = hdr_y + hdr_h + i * row_h
        bg = (32, 34, 44, 255) if i % 2 == 0 else (38, 40, 52, 255)
        draw.rectangle([0, ry, total_w, ry + row_h], fill=bg)

        dim = scores_dict.get(key, {}) if isinstance(scores_dict, dict) else {}
        s = int(dim.get("score", 7)) if isinstance(dim, dict) else 7
        note = dim.get("note", "-") if isinstance(dim, dict) else "-"
        total_score += s

        sc = "#2ECC71" if s >= 9 else ("#F39C12" if s >= 7 else "#E74C3C")

        draw.text((col1_x + 4, ry + 5), f"**{label}**", font=font_row, fill=(230, 230, 240, 255))
        draw.text((col2_x + 8, ry + 5), str(s),          font=font_row, fill=sc)
        draw.text((col3_x + 4, ry + 5), note,            font=font_sm,  fill=(185, 185, 200, 255))

        if i < n_rows - 1:
            draw.line([(pad_x, ry + row_h), (total_w - pad_x, ry + row_h)],
                      fill=(55, 56, 70, 255), width=1)

    # 总分行
    total_y = hdr_y + hdr_h + n_rows * row_h
    draw.rectangle([0, total_y, total_w, total_y + row_h], fill=(50, 52, 70, 255))
    draw.text((col1_x + 4, total_y + 5), "**总分**",       font=font_row, fill=(255, 255, 255, 255))
    draw.text((col2_x + 8, total_y + 5), f"{total_score}/50", font=font_row, fill="#F1C40F")
    level = "优秀，已有效去除AI痕迹" if total_score >= 40 else "良好，尚有改进空间"
    draw.text((col3_x + 4, total_y + 5), level, font=font_sm, fill=(200, 200, 215, 255))

    # 页脚
    foot_y = total_y + row_h
    draw.rectangle([0, foot_y, total_w, total_h], fill=(36, 38, 50, 255))
    draw.text((pad_x, foot_y + 13), f"原文 {char_count} 字符", font=font_sm, fill=(130, 130, 145, 255))
    draw.text((total_w - pad_x - 180, foot_y + 13), "Powered by ✨ 火斑喵 AI",
              font=font_sm, fill=(130, 130, 145, 255))

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.getvalue()


async def extract_text(bot: Bot, event: MessageEvent, args: Message) -> str:
    direct = args.extract_plain_text().strip()
    if direct:
        return direct

    if event.reply:
        reply_msg = event.reply.message
        reply_text = reply_msg.extract_plain_text().strip()
        if reply_text:
            return reply_text
        for seg in reply_msg:
            if seg.type == "file":
                file_id = seg.data.get("file_id", "")
                if file_id:
                    t = await download_file(bot, file_id)
                    if t:
                        return t

    for seg in event.message:
        if seg.type == "file":
            file_id = seg.data.get("file_id", "")
            if file_id:
                t = await download_file(bot, file_id)
                if t:
                    return t
    return ""


async def download_file(bot: Bot, file_id: str) -> str:
    try:
        info = await bot.call_api("get_file", file_id=file_id)
        url = info.get("url", "")
        if not url:
            return ""
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return ""
            text = resp.text
            return text[:MAX_CHARS] if len(text) > MAX_CHARS else text
    except Exception as e:
        logger.error(f"[Humanize] 下载文件异常: {e}")
        return ""


humanize_cmd = on_command("humanize", priority=5, block=True)


@humanize_cmd.handle()
async def handle_humanize(bot: Bot, event: MessageEvent, args: Message = CommandArg()):
    if not API_KEY:
        await humanize_cmd.finish("🐾 艾玛，本喵的 AI 大脑还没接上！管理员还没配置 API_KEY 喵...")

    skill = load_skill()
    if not skill:
        await humanize_cmd.finish("🐾 艾玛，SKILL.md 提示词文件不见了！本喵的技能书被偷了！")

    text = await extract_text(bot, event, args)
    if not text:
        await humanize_cmd.finish(
            "🐾 艾玛，你想让我润色什么？\n"
            "用法:\n"
            "  /humanize 你的文本\n"
            "  回复一条消息 + /humanize\n"
            "  发送 .txt/.md 文件 + /humanize"
        )

    if len(text) > MAX_CHARS:
        await humanize_cmd.finish(
            f"🐾 呀！这个文件/文本太长了喵！本喵的脑容量（2C 2G）要炸了，"
            f"请节选核心段落再让我润色！（当前 {len(text)} 字符，上限 {MAX_CHARS}）"
        )

    await humanize_cmd.send("🐾 火斑喵正在调用赛博文采引擎，给你的文字注入灵魂...")

    try:
        result = await call_llm(skill, build_user_prompt(text))
    except FinishedException:
        raise
    except httpx.TimeoutException:
        await humanize_cmd.finish("🐾 艾玛，大模型超时了！网络是不是在摸鱼？等会儿再试喵...")
    except Exception as e:
        logger.error(f"[Humanize] LLM 异常: {type(e).__name__}: {e}")
        await humanize_cmd.finish(f"🐾 本喵的赛博大脑短路了: {type(e).__name__}，等会儿再试喵！")

    humanized = result.get("humanized_text", "")
    changes = result.get("changes", "")
    scores = result.get("scores", {})

    if not humanized:
        await humanize_cmd.finish("🐾 艾玛，大模型今天罢工了！可能是 API 抽风，等会儿再试喵...")

    # ---- 消息 1: 润色后文本 ----
    if len(humanized) > 1800:
        await humanize_cmd.send("📝 润色完成! 文本较长分段发送:")
        for i in range(0, len(humanized), 1800):
            await humanize_cmd.send(humanized[i:i + 1800])
    else:
        await humanize_cmd.send(f"📝 润色完成!\n\n{humanized}")

    # ---- 消息 2: 评分表格图 ----
    try:
        table_img = generate_score_table(scores, len(text))
        await humanize_cmd.send(MessageSegment.image(table_img))
    except Exception as e:
        logger.error(f"[Humanize] 生成表格图失败: {e}")
        total = sum(int(v.get("score", 0)) for v in scores.values()) if scores else 0
        await humanize_cmd.send(f"📊 评分: {total}/50")

    # ---- 消息 3: 修改说明 ----
    if changes:
        await humanize_cmd.send(f"🔍 修改说明:\n{changes}")
