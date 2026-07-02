import os
import shutil
import gc
from pathlib import Path
from nonebot import require, logger
from nonebot.plugin import PluginMetadata

# 必须引入定时插件
require("nonebot_plugin_apscheduler")
from nonebot_plugin_apscheduler import scheduler

__plugin_meta__ = PluginMetadata(
    name="赛博清道夫",
    description="自动清理服务器日志和内存缓存，为 1.92GB 续命",
    usage="每周一凌晨 03:00 自动执行"
)

# ================= 配置区域 =================
# 获取项目根目录 (myqqbot/)
BASE_DIR = Path(__file__).parent.parent
# 需要清理的日志文件夹（如果有）
LOG_DIR = BASE_DIR / "log"
# 临时图片生成目录（如果有）
DATA_DIR = BASE_DIR / "data"


# ===========================================

def clean_logic():
    logger.info("🧹 【赛博清道夫】上线，准备大扫除...")
    count = 0

    # 1. 清理 Python 字节码缓存 (__pycache__)
    for p in BASE_DIR.rglob("__pycache__"):
        try:
            shutil.rmtree(p)
            count += 1
        except Exception:
            pass

    # 2. 清理超过 7 天的旧日志 (*.log)
    if LOG_DIR.exists():
        for log_file in LOG_DIR.glob("*.log"):
            try:
                # 如果文件大于 10MB 或者太旧，直接抹除内容或删除
                if log_file.stat().st_size > 10 * 1024 * 1024:
                    with open(log_file, "w") as f: f.truncate()
                    logger.info(f"已重置过大的日志文件: {log_file.name}")
            except Exception:
                pass

    # 3. 强制触发内存垃圾回收
    gc.collect()
    logger.info(f"✨ 扫除完毕！清理了 {count} 处垃圾，已强制释放内存。特呵呵呵~")


# ⏰ 定时任务：每周一凌晨 03:00 执行
@scheduler.scheduled_job("cron", day_of_week="mon", hour=3, minute=0, id="cyber_cleanup")
async def scheduled_cleanup():
    clean_logic()


# (可选) 机器人启动时也先打扫一次
@get_driver().on_startup
async def startup_clean():
    clean_logic()