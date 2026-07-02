from nonebot import on_command
from nonebot.adapters.onebot.v11 import Bot, Event, MessageSegment
from nonebot.params import CommandArg
from nonebot.rule import to_me

# 定义一个名为 "天气" 的指令
weather = on_command("天气", priority=10, block=True)


@weather.handle()
async def handle_weather(args=CommandArg()):
    city = args.extract_plain_text().strip()
    if not city:
        await weather.finish("你想查询哪个城市的天气？请发送：/天气 北京")

    # 这里可以接入真实 API，现在先写一个模拟回复
    await weather.finish(f"2026年3月12日，{city}的天气是：晴转多云，15°C，适合写代码！")


# 定义一个被 @ 时触发的回复
at_me = on_command("在吗", rule=to_me(), priority=10)


@at_me.handle()
async def handle_at():
    # 发送一张表情包或文字
    await at_me.finish("滚吧")