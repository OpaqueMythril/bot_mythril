import random
from typing import List, Union
from nonebot import on_command
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="今天吃什么",
    description="随机抽取菜单，解决选择困难症",
    usage="发送 '今天吃什么' 或 '吃啥'"
)

# 基础菜单（你可以随意扩充）
BASE_MENU = [
    "黄焖鸡米饭", "螺蛳粉", "疯狂星期四", "沙县大酒店", "萨莉亚",
    "兰州拉面", "麻辣烫", "麦当劳", "烧烤", "火锅", "汉堡王",
    "牛蛙", "隆江猪脚饭", "烤肉拌饭", "烤鱼", "猫罐头(喵~)"
]

eat_cmd = on_command("今天吃什么", aliases={"吃啥", "吃什么"}, priority=5, block=True)

@eat_cmd.handle()
async def handle_eat(event: MessageEvent):
    food = random.choice(BASE_MENU)
    # 傲娇回复逻辑
    responses = [
        f"艾玛，没主见就吃【{food}】吧！特呵呵呵~",
        f"本喵建议你吃【{food}】，吃完记得洗碗，喵！",
        f"既然你诚心诚意地发问了，那就【{food}】！(๑•̀ㅂ•́)و✧",
        f"瞅你那纠结样，【{food}】，爱吃不吃！"
    ]
    await eat_cmd.finish(random.choice(responses))