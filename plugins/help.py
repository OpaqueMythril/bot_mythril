from nonebot import on_command, get_loaded_plugins
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.plugin import PluginMetadata

# ================= 插件元数据 =================
__plugin_meta__ = PluginMetadata(
    name="帮助系统",
    description="本喵的赛博使用说明书",
    usage="发送 'help' 或 '帮助' 查看所有功能",
)

# 💡 黑名单列表：把你不希望在帮助菜单里显示的插件【包名】填在这里
# APScheduler 的包名通常是 "nonebot_plugin_apscheduler"
BLACKLIST = {"nonebot_plugin_apscheduler"}

help_cmd = on_command("help", aliases={"帮助", "功能"}, priority=5, block=True)

@help_cmd.handle()
async def handle_help(event: MessageEvent):
    plugins = get_loaded_plugins()
    
    help_text = "📜 【本喵的赛博说明书 v2.0】\n"
    help_text += "━━━━━━━━━━━━━━\n"
    
    has_valid_plugin = False
    
    for plugin in plugins:
        # 💡 增加一个判断：如果插件在黑名单里，直接跳过
        if plugin.name in BLACKLIST:
            continue
            
        if plugin.metadata:
            has_valid_plugin = True
            name = plugin.metadata.name
            desc = plugin.metadata.description
            usage = plugin.metadata.usage
            
            help_text += f"✨ 【{name}】\n"
            help_text += f"📖 简介：{desc}\n"
            help_text += f"🎮 用法：{usage}\n"
            help_text += "──────────────\n"
    
    if not has_valid_plugin:
        help_text += "艾玛，本喵现在脑子里空荡荡的，啥也不会！\n"
    else:
        help_text += "特呵呵呵~ 别乱试，弄坏了本喵可不负责！(๑•̀ㅂ•́)و✧"

    await help_cmd.finish(help_text)