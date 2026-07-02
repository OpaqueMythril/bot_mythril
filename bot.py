import nonebot
from nonebot.adapters.onebot.v11 import Adapter as ONEBOT_V11_Adapter

# 1. 初始化 NoneBot (它会自动读取 .env)
nonebot.init()

# 2. 注册适配器
driver = nonebot.get_driver()
driver.register_adapter(ONEBOT_V11_Adapter)

# 3. 加载插件
nonebot.load_plugins("plugins")

if __name__ == "__main__":
    # 直接运行，不要传任何参数
    nonebot.run()