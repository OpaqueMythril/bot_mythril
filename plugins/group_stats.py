import jieba
import sqlite3
import numpy as np
import io
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter
from wordcloud import WordCloud
from PIL import Image

from nonebot import on_message, on_command, logger, require, get_bot
from nonebot.adapters.onebot.v11 import Bot, MessageEvent, GroupMessageEvent, MessageSegment, Message
from nonebot.exception import FinishedException, ActionFailed
from nonebot.plugin import PluginMetadata
from typing import Union, List, Dict
# 💡 必须引入定时任务插件
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="水群统计",
    description="记录群消息，支持手动查询及每日零点自动推送词云",
    usage="群活跃/水群榜，群词云/今日词云"
)

# ================= 配置区域 =================
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "group_messages.db"
FONT_PATH = str(DATA_DIR / "simhei.ttf")

# ================= 强化版过滤词库 =================
STOPWORDS = {
    "的", "了", "在", "是", "我", "你", "他", "它", "们", "这", "那", "就", "也", "不", "有", "还", "个", "中", "说",
    "去", "到", "看", "被", "要", "这种", "真的", "怎么", "感觉", "一个", "结果", "还是", "觉得", "知道", "其实", "这个", "什么",
    "为什么", "为什么", "可以", "应该", "没有", "还有", "不能", "是不是", "不是", "可能", "或者", "因为", "所以", "如果", "那么",
    "哈哈", "呵呵", "有点", "好像", "确实", "比较", "非常", "一直", "干嘛", "原来", "本来", "反正", "总之",
    "自己", "这样", "那样", "这里", "那里", "大家", "别人", "某个", "内容", "一样", "全部", "所有",
    "看到", "发现", "发生", "开始", "结束", "已经", "正在", "准备", "进入", "进行", "通过", "由于",
    "bot", "消息", "系统", "提示", "内容", "回复", "指令", "发送", "成功", "失败",
    "今天", "明天", "昨天", "刚才", "之前", "之后", "现在", "以后", "后来", "最后"
}
# =================================================
# ===========================================

def init_db():
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS msg_logs 
                      (group_id INT, user_id INT, nickname TEXT, content TEXT, time TIMESTAMP)''')
    conn.commit()
    conn.close()

init_db()

# --- 消息记录逻辑 ---
msg_recorder = on_message(priority=99, block=False)

@msg_recorder.handle()
async def record_msg(event: GroupMessageEvent):
    content = event.get_plaintext().strip()
    if not content or len(content) < 2: return 

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("INSERT INTO msg_logs VALUES (?, ?, ?, ?, ?)",
                   (event.group_id, event.user_id, event.sender.nickname or str(event.user_id), 
                    content, datetime.now()))
    conn.commit()
    conn.close()

# --- 核心逻辑：生成词云报表 (提取成公用函数) ---
async def get_wordcloud_report(gid: int, start_time: datetime, end_time: datetime, title: str) -> Union[Message, str]:
    """获取指定群、指定时间段的词频统计和词云图片"""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT content FROM msg_logs WHERE group_id = ? AND time BETWEEN ? AND ?", 
                   (gid, start_time, end_time))
    msgs = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not msgs:
        return "艾玛，这段时间没人说话，本喵画不出来！"

    # 1. 分词与清洗
    all_text = " ".join(msgs)
    words = jieba.lcut(all_text)
    filtered_words = [w for w in words if len(w) > 1 and w not in STOPWORDS and not w.isdigit()]

    if not filtered_words:
        return "艾玛，内容太零碎，提取不出关键词！"

    # 2. 统计词频
    word_counts = Counter(filtered_words)
    top_10 = word_counts.most_common(10)
    
    report_text = f"📊 【{title}】\n"
    for i, (word, count) in enumerate(top_10):
        report_text += f"{i+1}. {word} ({count}次)\n"
    report_text += "──────────────"

    # 3. 生成词云图
    try:
        wc = WordCloud(
            font_path=FONT_PATH,
            width=800, height=400,
            background_color='white',
            max_words=100,
            collocations=False
        ).generate_from_frequencies(word_counts)
        
        img_buf = io.BytesIO()
        wc.to_image().save(img_buf, format="PNG")
        
        return Message(report_text) + MessageSegment.image(img_buf.getvalue())
    except Exception as e:
        logger.error(f"词云生成出错: {e}")
        return f"本喵画崩了：{e}"

# --- 指令处理 ---
stats_cmd = on_command("群活跃", aliases={"水群榜"}, priority=5, block=True)
@stats_cmd.handle()
async def handle_stats(event: GroupMessageEvent):
    gid = event.group_id
    yesterday = datetime.now() - timedelta(days=1)
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""SELECT nickname, COUNT(*) as cnt FROM msg_logs 
                      WHERE group_id = ? AND time > ? 
                      GROUP BY user_id ORDER BY cnt DESC LIMIT 5""", (gid, yesterday))
    rows = cursor.fetchall()
    conn.close()
    if not rows: await stats_cmd.finish("没人说话！")
    reply = "🏆 【24小时水群风云榜】\n" + "\n".join([f"{i+1}. {r[0]}：{r[1]} 条" for i, r in enumerate(rows)])
    await stats_cmd.finish(reply)

wordcloud_cmd = on_command("群词云", aliases={"今日词云"}, priority=5, block=True)
@wordcloud_cmd.handle()
async def handle_wordcloud(event: GroupMessageEvent):
    gid = event.group_id
    start = datetime.now().replace(hour=0, minute=0, second=0)
    end = datetime.now()
    await wordcloud_cmd.send("👁️ 本喵正在翻查账本，稍等...")
    result = await get_wordcloud_report(gid, start, end, "今日词云统计")
    await wordcloud_cmd.finish(result)

# --- ⏰ 定时任务：每晚 00:00 推送前一天统计 ---
@scheduler.scheduled_job("cron", hour=0, minute=0, id="daily_wordcloud_push")
async def scheduled_wordcloud():
    logger.info("开始执行每日词云自动推送任务...")
    bot = get_bot()
    
    # 设定时间范围：昨天一整天 (00:00:00 - 23:59:59)
    end_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    start_time = end_time - timedelta(days=1)
    date_str = start_time.strftime("%m月%d日")

    # 获取数据库中有记录的所有群
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT group_id FROM msg_logs WHERE time BETWEEN ? AND ?", (start_time, end_time))
    groups = [row[0] for row in cursor.fetchall()]
    conn.close()

    for gid in groups:
        try:
            report = await get_wordcloud_report(gid, start_time, end_time, f"{date_str} 结语汇报")
            if isinstance(report, Message):
                await bot.send_group_msg(group_id=gid, message=report)
                logger.info(f"成功推送至群 {gid}")
        except ActionFailed:
            logger.warning(f"推送至群 {gid} 失败，可能本喵不在该群了。")
        except Exception as e:
            logger.error(f"定时推送出错: {e}")