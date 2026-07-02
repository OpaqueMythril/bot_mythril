import json
import secrets
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException
from nonebot import get_app, get_bot, get_driver, logger, on_command
from nonebot.adapters.onebot.v11 import GroupMessageEvent, Message
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="课程 Webhook",
    description="接收寝室脚本推送的课程变更通知，支持手动查询课表",
    usage="自动接收 Webhook; 手动查询: /查课表 /课表"
)

# ================= 配置区（从 .env 动态加载）=================
config = get_driver().config

# 授权推送的目标群号（从 .env 读取，杜绝硬编码）
AUTHORIZED_GROUP = int(getattr(config, "course_webhook_group", "0"))

# Webhook 鉴权 Token — 从环境变量读取，杜绝硬编码弱密钥
WEBHOOK_SECRET_TOKEN = str(getattr(config, "webhook_secret_token", "")).strip().strip('"').strip("'")

if not WEBHOOK_SECRET_TOKEN:
    logger.error("[课程Webhook] 未配置 WEBHOOK_SECRET_TOKEN！Webhook 端点将拒绝所有请求。")
    logger.error("[课程Webhook] 请在 .env 中添加: WEBHOOK_SECRET_TOKEN=<强随机Token>")

# 数据缓存目录
DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
CLOUD_HISTORY_FILE = DATA_DIR / "cloud_course_cache.json"

# 获取 FastAPI app 实例
app: FastAPI = get_app()


# ================= 辅助函数 =================

def save_cache(data: list) -> None:
    """把收到的全量课程存入本地缓存"""
    try:
        CLOUD_HISTORY_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=4), encoding="utf-8"
        )
    except Exception as e:
        logger.error(f"[课程Webhook] 写入缓存失败: {e}")


def load_cache() -> list:
    """读取本地缓存的课表"""
    if CLOUD_HISTORY_FILE.exists():
        try:
            return json.loads(CLOUD_HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"[课程Webhook] 读取缓存失败: {e}")
            return []
    return []


def verify_bearer_token(request: Request) -> bool:
    """
    强健的 Bearer Token 鉴权校验。
    使用 secrets.compare_digest 防止时序攻击。
    支持两种传递方式（按优先级）：
      1. Authorization: Bearer <token>
      2. X-Secret-Key: <token> (向后兼容旧版寝室脚本)
    """
    if not WEBHOOK_SECRET_TOKEN:
        return False

    # 方式一：标准 Bearer Token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]  # 去掉 "Bearer " 前缀
        return secrets.compare_digest(token, WEBHOOK_SECRET_TOKEN)

    # 方式二：向后兼容 X-Secret-Key（过渡期保留，建议调用方尽快迁移到 Bearer）
    x_secret = request.headers.get("X-Secret-Key", "")
    if x_secret:
        return secrets.compare_digest(x_secret, WEBHOOK_SECRET_TOKEN)

    return False


# ================= Webhook 接收端点 =================

@app.post("/report_course")
async def receive_course_report(request: Request):
    """
    课程变更 Webhook 端点。
    由寝室 Agent 调用，需携带有效的 Bearer Token。
    """
    # 强健鉴权
    if not verify_bearer_token(request):
        logger.warning(f"[课程Webhook] 鉴权失败 — 来源 IP: {request.client.host if request.client else 'unknown'}")
        raise HTTPException(status_code=401, detail="身份认证失败：Token 无效或缺失")

    # 解析请求体
    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="请求体不是有效的 JSON")

    newly_added = data.get("new_courses", [])
    all_courses = data.get("all_courses", [])

    # 全量课表存入缓存（供手动查询）
    if all_courses:
        save_cache(all_courses)
        logger.info(f"[课程Webhook] 已更新全量课表缓存，共 {len(all_courses)} 门课程")

    # 无新课则静默返回成功
    if not newly_added:
        return {"status": "ok", "new_count": 0}

    # 构造推送消息
    msg_lines = ["🔔 侦察兵急报！发现新课！", "──────────────"]
    for c in newly_added:
        msg_lines.append(f"课程: {c.get('courseName', '未知')}")
        msg_lines.append(f"教师: {c.get('teacherName', '未知')}")
        msg_lines.append(f"代码: {c.get('courseCode', '未知')}")
        msg_lines.append("──────────────")

    try:
        bot = get_bot()
        await bot.send_group_msg(group_id=AUTHORIZED_GROUP, message="\n".join(msg_lines))
        logger.info(f"[课程Webhook] 成功推送 {len(newly_added)} 门新课至群 {AUTHORIZED_GROUP}")
        return {"status": "success", "new_count": len(newly_added)}
    except Exception as e:
        logger.error(f"[课程Webhook] 推送失败: {e}")
        raise HTTPException(status_code=500, detail=f"消息推送失败: {e}")


# ================= 手动查询指令 =================

list_cmd = on_command("查课表", aliases={"课表", "list_course"}, priority=5, block=True)

@list_cmd.handle()
async def handle_list(event: GroupMessageEvent):
    if event.group_id != AUTHORIZED_GROUP:
        return

    courses = load_cache()
    if not courses:
        await list_cmd.finish("艾玛，账本是空的！寝室侦察兵还没传情报过来呢喵。")

    msg_lines = [f"📊 当前课表快照 (共 {len(courses)} 门)", "──────────────"]
    for c in courses[:15]:
        msg_lines.append(f"[{c.get('courseCode', '?')}] {c.get('courseName', '未知')} - {c.get('teacherName', '未知')}")

    if len(courses) > 15:
        msg_lines.append(f"...... 还有 {len(courses) - 15} 门课没列出来。")

    msg_lines.append("──────────────")
    await list_cmd.finish("\n".join(msg_lines))
