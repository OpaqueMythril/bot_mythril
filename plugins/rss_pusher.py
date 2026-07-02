import feedparser
import sqlite3
import asyncio
from typing import List, Dict
from datetime import datetime

from nonebot import on_command, get_bot, require, logger
from nonebot.adapters.onebot.v11 import Bot, Message, GroupMessageEvent, MessageSegment
from nonebot.params import CommandArg
from nonebot.permission import SUPERUSER
from nonebot.exception import FinishedException

# 💡 必须引入定时任务插件
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

# ================= 数据库初始化 =================
# 使用 SQLite 存储订阅列表和已推送的消息 ID（防止重复推送）
DB_PATH = "rss_data.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # 订阅表：群号, RSS名称, URL
    cursor.execute('''CREATE TABLE IF NOT EXISTS subs 
                      (group_id INT, name TEXT, url TEXT)''')
    # 已推送记录表：URL, 消息唯一标识(link或id)
    cursor.execute('''CREATE TABLE IF NOT EXISTS pushed 
                      (url TEXT, entry_id TEXT)''')
    conn.commit()
    conn.close()


init_db()

# ================= 指令处理 =================

rss_add = on_command("添加订阅", priority=5, permission=SUPERUSER, block=True)
rss_del = on_command("删除订阅", priority=5, permission=SUPERUSER, block=True)
rss_list = on_command("订阅列表", priority=5, block=True)


@rss_add.handle()
async def _(event: GroupMessageEvent, arg: Message = CommandArg()):
    args = arg.extract_plain_text().strip().split()
    if len(args) < 2:
        await rss_add.finish("艾玛，格式错了！格式：添加订阅 [名称] [URL]")

    name, url = args[0], args[1]
    group_id = event.group_id

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO subs VALUES (?, ?, ?)", (group_id, name, url))
    conn.commit()
    conn.close()

    await rss_add.finish(f"✅ 成功订阅【{name}】！本喵会盯着它的。")


@rss_del.handle()
async def _(event: GroupMessageEvent, arg: Message = CommandArg()):
    name = arg.extract_plain_text().strip()
    if not name:
        await rss_del.finish("笨蛋，告诉我你要删哪个订阅啊！")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM subs WHERE group_id = ? AND name = ?", (event.group_id, name))
    conn.commit()
    conn.close()

    await rss_del.finish(f"🗑️ 已取消订阅【{name}】。")


@rss_list.handle()
async def _(event: GroupMessageEvent):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, url FROM subs WHERE group_id = ?", (event.group_id,))
    subs = cursor.fetchall()
    conn.close()

    if not subs:
        await rss_list.finish("艾玛，这儿空空如也，啥也没订。")

    reply = "📋 当前群订阅列表：\n" + "\n".join([f"- {s[0]}: {s[1]}" for s in subs])
    await rss_list.finish(reply)


# ================= 定时任务逻辑 =================

# 每隔 10 分钟执行一次检查
@scheduler.scheduled_job("interval", minutes=10, id="rss_update_job")
async def check_rss():
    logger.info("RSS 定时检查启动...")
    bot = get_bot()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 获取所有不重复的订阅 URL
    cursor.execute("SELECT DISTINCT url FROM subs")
    urls = [row[0] for row in cursor.fetchall()]

    for url in urls:
        try:
            # 💡 异步爬取会更好，这里为了演示使用 feedparser 同步解析
            feed = feedparser.parse(url)
            if not feed.entries:
                continue

            # 检查最新的 3 条
            for entry in feed.entries[:3]:
                entry_id = getattr(entry, 'id', entry.link)

                # 检查是否已推送
                cursor.execute("SELECT 1 FROM pushed WHERE url = ? AND entry_id = ?", (url, entry_id))
                if cursor.fetchone():
                    continue

                # 构造推送消息
                title = entry.title
                link = entry.link
                summary = getattr(entry, 'summary', '无摘要')[:100] + "..."

                push_msg = f"🔔 【RSS 更新】\n标题：{title}\n链接：{link}\n摘要：{summary}"

                # 找到订阅了这个 URL 的所有群进行推送
                cursor.execute("SELECT group_id FROM subs WHERE url = ?", (url,))
                target_groups = cursor.fetchall()

                for group in target_groups:
                    try:
                        await bot.send_group_msg(group_id=group[0], message=push_msg)
                        await asyncio.sleep(1)  # 稍微喘口气，防止被风控
                    except Exception as e:
                        logger.error(f"推送至群 {group[0]} 失败: {e}")

                # 标记为已推送
                cursor.execute("INSERT INTO pushed VALUES (?, ?)", (url, entry_id))
                conn.commit()

        except Exception as e:
            logger.error(f"解析 RSS {url} 出错: {e}")

    conn.close()
    logger.info("RSS 定时检查结束。")