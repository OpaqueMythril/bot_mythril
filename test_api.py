import httpx
import asyncio


async def test():
    # ！！！请把这里换成你在 .env.dev 里的真实 sk- 开头的 Key ！！！
    api_key = "你的_SILICONFLOW_API_KEY"

    url = "https://api.siliconflow.cn/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "Qwen/Qwen3.5-27B",
        "messages": [{"role": "user", "content": "hi"}]
    }

    print("🚀 正在尝试连接硅基流动服务器...")
    try:
        # 设置一个短的超时时间，看是否能报错
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            resp = await client.post(url, json=payload, headers=headers)
            print(f"✅ 连接成功！状态码: {resp.status_code}")
            print(f"🤖 AI 回复: {resp.json()['choices'][0]['message']['content']}")
    except httpx.ConnectError:
        print("❌ 连接失败：网络不通，请检查是否开启了代理或防火墙。")
    except httpx.TimeoutException:
        print("❌ 请求超时：服务器没理你，可能是网络太慢或 API 地址写错。")
    except Exception as e:
        print(f"❌ 发生未知错误: {e}")


if __name__ == "__main__":
    asyncio.run(test())