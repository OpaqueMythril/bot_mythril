import httpx
from io import BytesIO
from PIL import Image, ImageOps, ImageSequence
from typing import Union, List

from nonebot import on_command, logger
from nonebot.params import CommandArg
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent, MessageSegment
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="图片处理",
    description="对图片或者gif进行处理",
    usage="引用图片后回复镜像/左对称/右对称/上对称/下对称等"
)


# --- 插件定义 ---
img_edit_cmd = on_command("镜像", aliases={"左对称", "右对称", "上对称", "下对称"}, priority=5, block=True)

# 定义静态图片的对称处理核心函数，供复用
def transform_frame(img: Image.Image, mode: str) -> Image.Image:
    """
    对单个图像帧进行对称处理。
    """
    # 强制转为 RGBA，防止处理不规则图片或透明背景时报错
    img = img.convert("RGBA")
    w, h = img.size
    
    # 核心算法：对称拼接
    if mode == "left":
        part = img.crop((0, 0, w // 2, h))
        flipped = ImageOps.mirror(part)
        img.paste(flipped, (w // 2, 0))
    elif mode == "right":
        part = img.crop((w // 2, 0, w, h))
        flipped = ImageOps.mirror(part)
        img.paste(flipped, (0, 0))
    elif mode == "top":
        part = img.crop((0, 0, w, h // 2))
        flipped = ImageOps.flip(part)
        img.paste(flipped, (0, h // 2))
    elif mode == "bottom":
        part = img.crop((0, h // 2, w, h))
        flipped = ImageOps.flip(part)
        img.paste(flipped, (0, 0))
        
    return img

@img_edit_cmd.handle()
async def handle_image_edit(bot: Bot, event: MessageEvent):
    # 1. 确定处理模式
    cmd = event.get_plaintext().strip()
    mode = "left"
    if "左对称" in cmd: mode = "left"
    elif "右对称" in cmd: mode = "right"
    elif "上对称" in cmd: mode = "top"
    elif "下对称" in cmd: mode = "bottom"

    # 2. 提取图片 URL
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
        await img_edit_cmd.finish("艾玛，没图我看个毛线！笨蛋！")

    # 3. 开始干活
    await img_edit_cmd.send(f"👁️ 本喵正在开启时间停止，处理【{mode}】对称动图...")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(img_url, timeout=30) # 动图可能较大，超时设长点
            if resp.status_code != 200:
                await img_edit_cmd.finish("艾玛，图片下载失败了！")
            
            # 使用 Pillow 打开图片
            img_orig = Image.open(BytesIO(resp.content))
            out_io = BytesIO()

            # --- 核心改进：GIF vs 静态图片分类处理 ---
            
            # 💡 检查是否为动画 (GIF)
            if getattr(img_orig, "is_animated", False):
                logger.info("检测到 GIF 动画，开启逐帧处理模式...")
                
                # 获取原 GIF 的元数据
                duration = img_orig.info.get("duration", 100) # 帧间隔时间 (ms)
                loop = img_orig.info.get("loop", 0)         # 循环次数 (0为无限)
                
                processed_frames = []
                
                # 遍历 GIF 的每一帧
                # 艾玛，Pillow 的 Iterator 可以帮我们优雅地拆解时间线
                for frame in ImageSequence.Iterator(img_orig):
                    # 对这一帧应用对称变换
                    transformed = transform_frame(frame, mode)
                    
                    # GIF 必须重新转为 P 模式（调色板模式）才能保存
                    # 使用自适应调色板，尽可能还原色彩
                    p_frame = transformed.convert("P", palette=Image.Palette.ADAPTIVE)
                    processed_frames.append(p_frame)
                    
                # 将处理好的所有帧，重新拼装回 GIF
                if processed_frames:
                    processed_frames[0].save(
                        out_io,
                        save_all=True,  # 💡 关键：保存所有帧
                        append_images=processed_frames[1:],
                        format="GIF",
                        duration=duration,
                        loop=loop,
                        optimize=True # 开启优化，减小体积
                    )
                else:
                    await img_edit_cmd.finish("艾玛，GIF 拆解失败，里面居然是空的！")

            else:
                # 处理普通的静态图片 (JPG, PNG)
                logger.info("检测到静态图片，单帧处理。")
                img_final = transform_frame(img_orig, mode)
                # 静态图默认存为 PNG 防止画质损失
                img_final.save(out_io, format="PNG")

            # 4. 发送结果
            await img_edit_cmd.finish(MessageSegment.image(out_io.getvalue()))

    except FinishedException:
        raise
    except Exception as e:
        logger.error(f"图片鬼畜化出错: {str(e)}")
        await img_edit_cmd.finish(f"本喵切歪了，时空乱流了：{str(e)}")