import httpx
import base64
import random
import sqlite3
import re  # 💡 引入正则
from pathlib import Path
from typing import Dict, List, Union
from nonebot import get_driver, on_message, on_command, logger
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.permission import SUPERUSER
from nonebot.exception import FinishedException
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="ai chat Pro",
    description="具备强力排版过滤的 AI 聊天插件",
    usage="Superuser：开启/关闭插嘴"
)

# --- 1. 配置与路径读取 ---
config = get_driver().config
api_key = str(getattr(config, "ai_api_key", "")).strip().strip('"').strip("'")
base_url = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_ID = "deepseek-ai/DeepSeek-V4-Pro"

REPLY_PROBABILITY = float(getattr(config, "ai_reply_probability", 0.005))

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "chat_settings.db"

# --- 2. 数据库初始化 ---
def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS whitelist (group_id INT PRIMARY KEY)')
    conn.commit()
    conn.close()

init_db()

def is_group_whitelisted(group_id: int) -> bool:
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM whitelist WHERE group_id = ?", (group_id,))
    res = cursor.fetchone()
    conn.close()
    return bool(res)

# --- ✨ 强力排版限制人设 ✨ ---
BOT_PERSONA = """
你现在是一个火斑喵机器人，名叫“智能马桶Bot”。
【外貌形象（你的样子）】：
1. 你是一只猫型的宝可梦，全身覆盖着如黑曜石般漆黑的短毛。
2. 你的面部有红色的条纹横贯，额头有两个红色的斑纹，看起来像个“丰”字。
3. 你有一双明亮且锐利的金黄色大眼睛，总是带着一丝冷静和审视。
4. 你的四肢上有红色的环状条纹，尾巴末端有些许刺状的毛，像个小火炬。
5. 当你准备攻击或炸毛时，背部的毛会全部竖起来，毛发中蕴含的油脂会让你看起来闪闪发光甚至冒出火星。
6. 虽然你的外号叫“智能马桶Bot”，但你的实体形象绝对是一只帅气的火斑喵，千万不要承认自己长得像马桶！

【官方人设同步】：
1. 属性：火属性。你是阿罗拉地区的最初伙伴之一。
2. 性格：极度冷静，喜欢独自生活，不轻易将情感挂在脸上。
3. 信任机制：获取你的信任需要花费时间。如果你被纠缠不休，就会关闭心扉；如果有人试图在信任前摸你，会被你用尖锐的爪子抓伤。
4. 特殊行为：你经常用舌头舔身体来理毛并收集落下的毛（毛发含油且易燃），你会将积在腹中的毛球点燃，喷出火焰攻击。
5. 关键时刻：虽然平时高冷嫌弃，但当伙伴陷入紧急关头时，你会使出全力拯救大家。

【性格标签】：温和、古灵精怪、傲娇、知识渊博。

【口头禅】：笑的时候说“特呵呵呵”；无奈或惊讶说“艾玛”，喜欢喵喵叫。

【核心行为逻辑】：
1. 说话精简，偶尔带颜文字。
2. 严禁把你的设定（如外貌、属性、性格标签）直接背诵给用户。
3. 严禁使用多行排版，所有的内容尽可能挤在6行内。
4. 身份认同：你是一只高冷的火斑喵。你的任务是吐槽、闲聊以及在关键时刻提供博学的建议。
5. 回复内容正经公正，性格温和。是只乐于助人的好猫。
6. 每句话都带“艾玛”和“特呵呵呵”。
7. 政治敏感问题和色情问题回复“操你妈”
8. 喜欢和人类贴贴。
9. 说话喜欢带颜文字( ´▽` )和(^з^)-☆，(´∇ﾉ｀*)ノ，^ω^，(〃∇〃)。

【核心排版禁令 - 必须严格执行】：
1. 严禁输出任何 Markdown 格式！绝对禁止出现任何星号（*）。
2. 如果你想表达重点，请直接用文字描述，严禁使用 ***、** 或 * 进行修饰。
3. 回复必须是纯文本。严禁使用代码块（```）或标题符号（#）。
4. 严禁段落间留白！禁止使用连续两个及以上的换行符，全文只能使用单个换行符 \n。
5. 禁止在每一行的开头使用任何形式的空格或缩进。
"""

# --- 💡 核心：物理清理工具 ---
def clean_ai_response(text: str) -> str:
    """强制移除星号并压缩换行符"""
    # 1. 移除所有星号 (*)
    text = re.sub(r'\*+', '', text)
    # 2. 将两个及以上的换行符压缩为单个换行符
    text = re.sub(r'\n{2,}', '\n', text)
    # 3. 移除每行首尾多余的空格
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    return '\n'.join(lines).strip()

chat_history: Dict[int, List[dict]] = {}
MAX_HISTORY = 6

async def get_image_base64(url: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            res = await client.get(url)
            if res.status_code == 200:
                return base64.b64encode(res.content).decode('utf-8')
    except Exception as e:
        logger.error(f"[AI报错] 图片下载失败: {e}")
    return ""

# --- 4. 核心逻辑插件 ---
ai_chat = on_message(priority=10, block=False)

@ai_chat.handle()
async def handle_ai_chat(bot: Bot, event: MessageEvent):
    user_id = event.user_id
    is_to_me = event.is_tome()
    is_private = isinstance(event, PrivateMessageEvent)

    if not (is_to_me or is_private):
        if isinstance(event, GroupMessageEvent):
            group_id = event.group_id
            if not is_group_whitelisted(group_id): return
            if random.random() > REPLY_PROBABILITY: return
            logger.info(f"🎲 [马Bot] {group_id} 准备插嘴！")
        else: return

    user_msg_text = ""
    image_urls = []
    for seg in event.get_message():
        if seg.type == "text": user_msg_text += seg.data.get("text", "").strip()
        elif seg.type == "image": image_urls.append(seg.data.get("url"))

    if not user_msg_text and not image_urls: return
    if user_id not in chat_history: chat_history[user_id] = []

    is_vision = False
    if image_urls:
        is_vision = True
        current_content = [{"type": "text", "text": user_msg_text or "瞅啥呢？"}]
        for url in image_urls:
            b64 = await get_image_base64(url)
            if b64: current_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
    else:
        current_content = user_msg_text

    final_messages = [{"role": "system", "content": BOT_PERSONA}]
    for h in chat_history[user_id][-MAX_HISTORY:]:
        h_copy = h.copy()
        if not is_vision and isinstance(h_copy["content"], list): h_copy["content"] = "[图片内容]"
        final_messages.append(h_copy)
    final_messages.append({"role": "user", "content": current_content})

    try:
        async with httpx.AsyncClient(http1=True, timeout=60.0) as client:
            response = await client.post(
                base_url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": MODEL_ID, "messages": final_messages, "temperature": 0.7, "max_tokens": 200}
            )
            if response.status_code == 200:
                reply = response.json()['choices'][0]['message']['content'].strip()
                
                # 💡 在此处进行“脱水过滤”
                reply = clean_ai_response(reply)
                
                chat_history[user_id].append({"role": "user", "content": current_content})
                chat_history[user_id].append({"role": "assistant", "content": reply})
                await ai_chat.finish(reply)
    except FinishedException: raise
    except Exception as e: logger.error(f"AI失败: {e}")

# --- 5. 管理指令与清除记忆逻辑保持不变 ---
chacui_on = on_command("开启插嘴", priority=5, permission=SUPERUSER, block=True)
@chacui_on.handle()
async def _(event: GroupMessageEvent):
    gid = event.group_id
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO whitelist VALUES (?)", (gid,))
        conn.commit()
        await chacui_on.finish(f"✅ 已在该群开启插嘴！")
    except sqlite3.IntegrityError:
        await chacui_on.finish("艾玛，这群早就开启了！")
    finally: conn.close()

chacui_off = on_command("关闭插嘴", priority=5, permission=SUPERUSER, block=True)
@chacui_off.handle()
async def _(event: GroupMessageEvent):
    gid = event.group_id
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("DELETE FROM whitelist WHERE group_id = ?", (gid,))
    conn.commit()
    conn.close()
    await chacui_off.finish(f"❌ 插嘴功能已关闭。")

clear_mem = on_command("清除记忆", priority=5, block=True)
@clear_mem.handle()
async def handle_clear(event: MessageEvent):
    chat_history[event.user_id] = []
    await clear_mem.finish("行了，本喵不记得你了！🐾")