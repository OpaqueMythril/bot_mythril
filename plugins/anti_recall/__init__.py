import time
from typing import Dict, Any, Union
from nonebot import on_message, on_notice, get_driver
from nonebot.adapters.onebot.v11 import (
    Bot,
    Message,
    GroupMessageEvent,
    PrivateMessageEvent,
    GroupRecallNoticeEvent,
    FriendRecallNoticeEvent,
)
from nonebot.plugin import PluginMetadata

# 插件元数据
__plugin_meta__ = PluginMetadata(
    name="防撤回助手 Pro",
    description="自动记录消息并在撤回时复原，具备防套娃和防刷屏逻辑",
    usage="自动运行；屏蔽包含本喵口头禅的复读消息",
)

# 消息缓存字典
msg_cache: Dict[int, Dict[str, Any]] = {}
CACHE_LIMIT = 300  # 稍微加大一点缓存限制

# 记录最后一次撤回提醒的时间，防止刷屏 {group_id/user_id: timestamp}
last_recall_time: Dict[Union[int, str], float] = {}
RECALL_INTERVAL = 3.0  # 同一环境下 3 秒内只触发一次

# 本喵的标志性口头禅，用于防套娃识别
BOT_SIGNATURES = ["特呵呵", "抓到你了", "撤回我也能看见"]

# 1. 监听所有消息并存入缓存
msg_recorder = on_message(priority=1, block=False)

@msg_recorder.handle()
async def record_msg(bot: Bot, event: Union[GroupMessageEvent, PrivateMessageEvent]):
    msg_id = event.message_id
    plain_text = event.get_plaintext()

    # --- 🛡️ 防套娃逻辑 ---
    # 1. 如果是机器人自己发的（保险起见）
    if str(event.user_id) == str(bot.self_id):
        return

    # 2. 如果消息内容里包含本喵的口头禅，说明是用户在复读或者套娃，不予记录
    if any(sig in plain_text for sig in BOT_SIGNATURES):
        return

    # 3. 记录有效消息
    msg_cache[msg_id] = {
        "user_id": event.user_id,
        "content": event.message,
        "time": time.time()
    }

    # 清理过期的旧缓存
    if len(msg_cache) > CACHE_LIMIT:
        oldest_id = next(iter(msg_cache))
        del msg_cache[oldest_id]


# 2. 监听群组撤回通知
group_recall = on_notice(priority=5)

@group_recall.handle()
async def handle_group_recall(bot: Bot, event: GroupRecallNoticeEvent):
    msg_id = event.message_id
    gid = event.group_id

    # 基础过滤：不在缓存、或是机器人自撤回
    if msg_id not in msg_cache or event.user_id == int(bot.self_id):
        return

    # --- ⏱️ 防刷频率逻辑 ---
    now = time.time()
    if gid in last_recall_time and now - last_recall_time[gid] < RECALL_INTERVAL:
        return
    last_recall_time[gid] = now

    data = msg_cache[msg_id]
    user_id = data["user_id"]
    content = data["content"]

    # 构造并发送提醒
    ret_msg = Message(f"特呵呵，抓到你了！[CQ:at,qq={user_id}] 刚才撤回了：\n") + content
    await bot.send(event, ret_msg)

    # 发完就删，防止针对同一条 ID 的二次操作
    if msg_id in msg_cache:
        del msg_cache[msg_id]


# 3. 监听好友撤回通知
friend_recall = on_notice(priority=5)

@friend_recall.handle()
async def handle_friend_recall(bot: Bot, event: FriendRecallNoticeEvent):
    msg_id = event.message_id
    uid = event.user_id

    if msg_id not in msg_cache:
        return

    # 私聊防刷
    now = time.time()
    if uid in last_recall_time and now - last_recall_time[uid] < RECALL_INTERVAL:
        return
    last_recall_time[uid] = now

    data = msg_cache[msg_id]
    content = data["content"]

    await bot.send(event, Message("特呵呵，撤回我也能看见！你刚才发了：\n") + content)

    if msg_id in msg_cache:
        del msg_cache[msg_id]