import re
import io
from pathlib import Path
from typing import Optional
from PIL import Image
from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="奶龙字母拼图",
    description="将输入字母拼接成横向奶龙风格拼图，最多 20 个字符",
    usage="/nai [字母] 或 #nai [字母] 或 .nai [字母]"
)

IMG_DIR = Path(__file__).parent.parent / "data" / "Nailoong"
MAX_LENGTH = 20


def load_letter_image(letter: str) -> Optional[Image.Image]:
    path = IMG_DIR / f"{letter}.png"
    if not path.exists():
        logger.error(f"[Nailoong] 图片不存在: {path}")
        return None
    try:
        return Image.open(path).convert("RGBA")
    except Exception as e:
        logger.error(f"[Nailoong] 加载图片失败 {path}: {e}")
        return None


def stitch_letters(letters: str) -> Optional[bytes]:
    images = []
    for ch in letters:
        img = load_letter_image(ch)
        if img is None:
            for loaded in images:
                loaded.close()
            return None
        images.append(img)

    if not images:
        return None

    heights = [img.height for img in images]
    if len(set(heights)) > 1:
        target_h = max(heights)
        resized = []
        for img in images:
            if img.height != target_h:
                ratio = target_h / img.height
                new_w = int(img.width * ratio)
                resized.append(img.resize((new_w, target_h), Image.LANCZOS))
            else:
                resized.append(img)
        for img in images:
            img.close()
        images = resized

    total_w = sum(img.width for img in images)
    max_h = max(img.height for img in images)

    canvas = Image.new("RGBA", (total_w, max_h), (0, 0, 0, 0))

    x_offset = 0
    for img in images:
        y_offset = (max_h - img.height) // 2
        canvas.paste(img, (x_offset, y_offset), img)
        x_offset += img.width

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")

    for img in images:
        img.close()
    canvas.close()

    buf.seek(0)
    return buf.getvalue()


nailong_cmd = on_command("nai", priority=5, block=True)


@nailong_cmd.handle()
async def handle_nailong(args: Message = CommandArg()):
    raw = args.extract_plain_text().strip()

    if not raw:
        await nailong_cmd.finish(
            "🐾 艾玛，你得给本喵几个字母啊！用法: /nai ABC (最多20个字母)"
        )

    if len(raw) > MAX_LENGTH:
        await nailong_cmd.finish(
            f"🐾 字符太长了喵！本喵的爪子最多只能帮你拼 {MAX_LENGTH} 个字母！"
        )

    letters = re.sub(r"[^a-zA-Z]", "", raw).upper()

    if not letters:
        await nailong_cmd.finish(
            "🐾 艾玛，你得输入英文字母才行喵！中文、数字和符号本喵拼不出来！"
        )

    if not IMG_DIR.exists():
        logger.error(f"[Nailoong] 图片目录不存在: {IMG_DIR}")
        await nailong_cmd.finish("🐾 艾玛，奶龙图库找不到了！快去检查 data/Nailoong/ 目录！")

    await nailong_cmd.send(f"🐾 火斑喵正在拼奶龙 {len(letters)} 个字母: {letters} ...")

    try:
        image_bytes = stitch_letters(letters)
        if image_bytes is None:
            await nailong_cmd.finish("🐾 艾玛，拼图的时候奶龙图片坏掉了！可能是缺了某个字母的图！")

        await nailong_cmd.finish(MessageSegment.image(image_bytes))

    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"[Nailoong] 拼接异常: {type(e).__name__}: {e}")
        await nailong_cmd.finish(f"🐾 本喵爪子打滑了！拼接失败: {e}")
