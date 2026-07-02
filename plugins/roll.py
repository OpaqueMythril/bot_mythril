import random
import re
from typing import List, Union
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="抉择Roll点",
    description="在多个选项中随机挑选一个",
    usage="roll 选项1 选项2 / A 还是 B / 抽签 A B C"
)

# 支持多种分隔符：空格、/、,、还是
roll_cmd = on_command("roll", aliases={"抽签", "抉择", "帮我选"}, priority=5, block=True)
# 专门匹配 "A 还是 B" 的正则表达式
haishi_regex = re.compile(r"(.+?)\s*还是\s*(.+)")


@roll_cmd.handle()
async def handle_roll(event: MessageEvent):
    msg = event.get_plaintext().strip()

    # 1. 先尝试处理 "还是" 逻辑
    match = haishi_regex.search(msg)
    if match:
        options = [match.group(1).split()[-1], match.group(2).split()[0]]
    else:
        # 2. 否则按空格或斜杠分割
        # 移除掉触发词
        clean_msg = re.sub(r"^(roll|抽签|抉择|帮我选)", "", msg).strip()
        options = re.split(r"[\s/，,]+", clean_msg)

    options = [o.strip() for o in options if o.strip()]

    if len(options) < 2:
        await roll_cmd.finish("艾玛，至少给两个选项啊，笨蛋！喵！")

    result = random.choice(options)
    await roll_cmd.finish(f"📊 赛博算命结果：本喵选【{result}】！特呵呵呵~")