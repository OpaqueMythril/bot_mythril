import time
from typing import Union
from nonebot import on_command, logger
from nonebot.adapters.onebot.v11 import MessageEvent, GroupMessageEvent, PrivateMessageEvent
from nonebot.plugin import PluginMetadata

__plugin_meta__ = PluginMetadata(
    name="猫猫状态检测",
    description="检测猫猫是否睡着",
    usage="/ping 或 /喵"
)

# 💡 注册指令：支持 ping 和 喵 两个触发词
# priority=5 确保优先级，block=True 防止消息继续下传
ping_cmd = on_command("ping", aliases={"喵", "状态"}, priority=5, block=True)

@ping_cmd.handle()
async def handle_ping(event: MessageEvent):
    # 1. 获取消息发送时的时间戳 (秒级)
    start_time = event.time

    # 2. 获取当前接收到并处理的时间戳 (高精度)
    end_time = time.time()

    # 3. 计算延迟 (毫秒)
    latency = (end_time - start_time) * 1000
    
    # 防止出现负数或极小值（由于系统时钟同步差异）
    latency = max(latency, 0.01)

    # 4. 根据延迟程度给出【傲娇火斑喵】的评价
    if latency < 150:
        comment = "特呵呵呵，本喵现在神清气爽，全线通畅！🐾"
    elif latency < 500:
        comment = "艾玛，反应稍微有点迟钝，是没给本喵喂小鱼干吗？O_o"
    else:
        comment = "啧，这破网络气得老子鬼火冒！( ` 皿´ )"

    # 5. 返回结果 (纯文本，拒绝星号)
    result = (
        f"🏓 砰！\n"
        f"延迟: {latency:.2f}ms\n"
        f"评价: {comment}"
    )
    
    await ping_cmd.finish(result)