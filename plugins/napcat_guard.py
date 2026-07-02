from nonebot import on_message, get_driver
from nonebot.rule import Rule
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent
from nonebot.plugin import PluginMetadata



# --- ⚙️ 获取超级用户列表 ---
superusers = get_driver().config.superusers


# --- 🛡️ 拦截规则 ---
async def is_napcat_cmd(event: MessageEvent) -> bool:
    msg = event.get_plaintext().strip().lower()
    # 只要消息是以 #napcat 开头的，就触发
    return msg.startswith("#napcat")


# 💡 优先级设为 1 (最高级别)，block=True 表示拦截后不再传给其他逻辑
napcat_guard = on_message(rule=Rule(is_napcat_cmd), priority=1, block=True)


@napcat_guard.handle()
async def handle_guard(event: MessageEvent):
    user_id = str(event.user_id)

    # 如果不是超级用户，直接静默退出（或者你可以回一句“别乱摸本喵！”）
    if user_id not in superusers:
        # logger.info(f"🚫 拦截了来自 {user_id} 的非法查询")
        return

        # 💡 如果是超级用户，我们可以手动调用 NapCat 的信息 (这里可以保持沉默，让原指令运行)
    # 但由于 block=True，我们需要在这里手动回复，或者把这里改成不拦截
    # 为了简单，我们干脆让它对所有人失效，你自己想看时去后台看：
    # await napcat_guard.finish("切，别在群里看本喵的隐私！")