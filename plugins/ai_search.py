import httpx
import re
from typing import Union, List
from nonebot import on_command, logger, get_driver
from nonebot.adapters.onebot.v11 import MessageEvent, Message, MessageSegment
from nonebot.params import CommandArg
from nonebot.rule import Rule
from nonebot.plugin import PluginMetadata

# ================= 插件元数据 =================
__plugin_meta__ = PluginMetadata(
    name="联网 AI 搜索",
    description="使用 Tavily 联网并调用大模型进行傲娇总结",
    usage="搜索 [问题] / 问 [问题] (自动规避'问号'等误触)"
)

# ================= 配置读取 =================
config = get_driver().config
# 💡 请确保 .env 中有这两项配置
tavily_api_key = str(getattr(config, "tavily_api_key", "")).strip().strip('"').strip("'")
silicon_api_key = str(getattr(config, "ai_api_key", "")).strip().strip('"').strip("'")

TAVILY_URL = "https://api.tavily.com/search"
SILICON_URL = "https://api.siliconflow.cn/v1/chat/completions"
MODEL_ID = "Qwen/Qwen2.5-72B-Instruct-128K" # 选用稳定的 72B 模型

# --- 🛡️ 规则：防止“问号/问候”等词汇误触发 ---
async def search_rule(event: MessageEvent) -> bool:
    msg = event.get_plaintext().strip()
    # 只要是以这些词开头的，本喵直接装死，不打断日常聊天
    blacklist = ("问号", "问候", "问问", "问路", "问世")
    return not msg.startswith(blacklist)

# --- 🧹 清理 Markdown 星号的工具 ---
def clean_stars(text: str) -> str:
    # 移除所有的 * 符号，防止 AI 乱加 Markdown 加粗
    return re.sub(r'\*+', '', text).strip()

# --- 核心逻辑 1：Tavily 搜索 ---
async def get_tavily_search(query: str) -> str:
    if not tavily_api_key: return "错误：未配置 TAVILY_API_KEY"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            payload = {"api_key": tavily_api_key, "query": query, "max_results": 5}
            resp = await client.post(TAVILY_URL, json=payload)
            results = resp.json().get("results", [])
            if not results: return "未能搜到实时信息。"
            return "\n".join([f"[{i+1}] {r['title']}: {r['content']}" for i, r in enumerate(results)])
    except Exception as e:
        logger.error(f"[Tavily] 错误: {e}")
        return f"网络塞车了喵：{e}"

# --- 核心逻辑 2：AI 傲娇总结 ---
async def get_ai_summary(query: str, context: str) -> str:
    if not silicon_api_key: return "错误：未配置 AI_API_KEY"

    persona = """你现在是智能马桶Bot（火斑喵）。性格：傲娇、毒舌、口嫌体正直。
回复要求：
1. 严禁使用任何 Markdown 符号（严禁出现 *** 或 **）。
2. 说话精简，带口头禅“特呵呵呵”、“艾玛”或“喵”。
3. 表面上嫌弃用户笨，实际上根据【搜索资料】认真回答问题。
4. 所有的加粗重点请直接用文字描述，不要用星号！"""

    prompt = f"问题：{query}\n资料：\n{context}\n请总结回答："

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            headers = {"Authorization": f"Bearer {silicon_api_key}", "Content-Type": "application/json"}
            payload = {
                "model": MODEL_ID,
                "messages": [{"role": "system", "content": persona}, {"role": "user", "content": prompt}],
                "temperature": 0.7
            }
            resp = await client.post(SILICON_URL, json=payload, headers=headers)
            content = resp.json()['choices'][0]['message']['content']
            return clean_stars(content) # 再次强制清理星号
    except Exception as e:
        return f"本喵脑路走火入魔了：{e}"

# --- 指令处理 ---
ai_search = on_command(
    "搜索", 
    aliases={"问", "查一下"}, 
    rule=Rule(search_rule), # 💡 加入防误触规则
    priority=5, 
    block=True
)

@ai_search.handle()
async def handle_search(args: Message = CommandArg()):
    # 💡 核心修复：使用 args 获取内容，不再手动 replace
    query = args.extract_plain_text().strip()

    # 如果用户只发了一个“问”，且后面没内容，直接退出，不误伤
    if not query:
        return

    await ai_search.send(f"🔍 本喵帮你查一下‘{query}’，坐稳了喵~")

    # 1. 联网
    context = await get_tavily_search(query)
    if "错误" in context:
        await ai_search.finish(context)

    # 2. AI 总结
    final_answer = await get_ai_summary(query, context)
    await ai_search.finish(final_answer)