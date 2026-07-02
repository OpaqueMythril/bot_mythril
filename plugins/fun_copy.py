import random
import re
import asyncio
import json
from pathlib import Path
from typing import List, Optional
from nonebot import on_message, on_command, logger
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11.permission import GROUP_ADMIN, GROUP_OWNER
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Bot, Message, MessageEvent
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="神秘替换",
    description="支持随机魔改复读，或使用 /r 主动触发魔改，支持群内独立开关",
    usage="1. /r开关 [开启/关闭] (群主/管理/超管可用)\n2. 概率自动复读\n3. /r [内容] 主动魔改\n4. 引用消息回复 /r 强行魔改"
)

# ================= 配置区域 =================
TRIGGER_CHANCE = 0.05  # 自动触发概率
REPLACE_CHANCE = 0.30  # 替换概率

REPLACEMENT_POOL = [
    "🐾", "🔥", "🐱", "💢", "🍮", "喵", "特呵呵", "艾玛",
    "冉", "蛆", "娲", "🥥", "🫛", "彬",
    "biu", "爻", "脚", "刁", "爆", "耄",
    "逼", "批", "史", "耋", "绷", "尻", "炮", "步", "跳", "蛋", "焚", "。", "，", "？", "！"
]

BLACKLIST_WORDS = ["http", "CQ:", "api", "key"]

# 开关数据持久化路径 (存储在 nonebot 根目录下的 data 文件夹)
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CONFIG_FILE = DATA_DIR / "fun_copy_status.json"
# ===========================================

def load_status() -> dict:
    """加载各个群的开关状态"""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[神秘替换] 读取开关配置失败: {e}")
            return {}
    return {}

def save_status(status_dict: dict):
    """保存开关状态"""
    try:
        CONFIG_FILE.write_text(json.dumps(status_dict, ensure_ascii=False, indent=4), encoding="utf-8")
    except Exception as e:
        logger.error(f"[神秘替换] 保存开关配置失败: {e}")

def is_plugin_enabled(group_id: int) -> bool:
    """检查当前群是否开启了魔改功能，默认开启"""
    status = load_status()
    # 返回 True 代表开启，False 代表关闭。如果账本里没有，默认是开启的。
    return status.get(str(group_id), True)

def transformer(text: str) -> str:
    """魔改文字的核心逻辑"""
    if len(text) < 1:
        return ""
    
    chars = list(text)
    new_chars = []
    for char in chars:
        if random.random() < REPLACE_CHANCE and char.strip():
            new_chars.append(random.choice(REPLACEMENT_POOL))
        else:
            new_chars.append(char)
    
    magic_text = "".join(new_chars)
    magic_text = re.sub(r'\*+', '', magic_text)
    magic_text = re.sub(r'\n{2,}', '\n', magic_text)
    return magic_text.strip()


# --- 0. 控制中枢：一键开关指令 ---
# 权限：群主 OR 群管理 OR 超级管理员
switch_cmd = on_command(
    "r开关", 
    aliases={"魔改开关", "替换开关"}, 
    permission=GROUP_ADMIN | GROUP_OWNER | SUPERUSER, 
    priority=5, 
    block=True
)

@switch_cmd.handle()
async def handle_switch(event: GroupMessageEvent, args: Message = CommandArg()):
    arg_text = args.extract_plain_text().strip()
    group_id = str(event.group_id)
    status = load_status()

    if arg_text in ["开启", "开", "on", "enable"]:
        status[group_id] = True
        save_status(status)
        await switch_cmd.finish("🐾 啪嗒！本喵把这个群的天线拉开啦！")
        
    elif arg_text in ["关闭", "关", "off", "disable"]:
        status[group_id] = False
        save_status(status)
        await switch_cmd.finish("💢 哼！既然嫌本喵吵，那我就闭嘴了。")
        
    else:
        current = "开启" if status.get(group_id, True) else "关闭"
        await switch_cmd.finish(f"💡 当前群魔改状态为：【{current}】\n请使用 `/r开关 开启` 或 `/r开关 关闭` 来控制本喵！")


# --- 1. 手动触发：/r 指令 ---
manual_r = on_command("r", aliases={"魔改", "替换"}, priority=5, block=True)

@manual_r.handle()
async def handle_manual_r(bot: Bot, event: GroupMessageEvent, args: Message = CommandArg()):
    # 💡 优先检查当前群的开关状态
    if not is_plugin_enabled(event.group_id):
        return

    target_text = ""
    
    if event.reply:
        target_text = event.reply.message.extract_plain_text()
    elif args.extract_plain_text().strip():
        target_text = args.extract_plain_text().strip()
    
    if not target_text:
        await manual_r.finish("艾玛，你想让本喵改空气吗？快发点什么或者引用一条消息喵！( ` 皿´ )")

    result = transformer(target_text)
    
    if result == target_text:
        result += random.choice(REPLACEMENT_POOL)

    await manual_r.finish(result)


# --- 2. 自动触发：随机复读逻辑 ---
auto_copy = on_message(priority=99, block=False)

@auto_copy.handle()
async def handle_auto_copy(bot: Bot, event: GroupMessageEvent):
    # 💡 优先检查当前群的开关状态
    if not is_plugin_enabled(event.group_id):
        return

    msg = event.get_plaintext().strip()
    
    if msg.startswith(("/", "#", "问", "搜索")) or len(msg) < 3 or len(msg) > 50:
        return
    if str(event.user_id) == str(bot.self_id):
        return
    if any(word in msg for word in BLACKLIST_WORDS):
        return

    if random.random() < TRIGGER_CHANCE:
        magic_text = transformer(msg)
        if magic_text == msg:
            magic_text += "...喵？"
            
        await asyncio.sleep(random.uniform(0.5, 1.5))
        await auto_copy.finish(magic_text)