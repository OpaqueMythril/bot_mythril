#  mabot - 傲娇猫智能助理

这是学习期间基于 **NoneBot2** 框架开发的跨平台 QQ 机器人，集成了 AI 聊天、视觉分析、图片处理和报童推送等一系列功能。

## 核心Plugins

目前掌握了以下技能，全部藏在 `plugins` 文件夹里：

- ** AI 聊天 (`ai_chat.py`)**：接入大模型，陪你天南地北地瞎胡扯。
- ** 视觉评价 (`evaluator.py`)**：利用 Qwen-VL 等多模态模型，对图片进行毒舌点评。
- ** 图片镜像 (`image_editor.py`)**：支持静态图和 GIF 的对称处理。
- ** RSS 报童 (`rss_pusher.py`)**：定时抓取订阅源，有瓜第一时间在群里喊你。
- ** 状态监控 (`server_status`)**：监控服务器 CPU、内存及主要进程的资源占用情况。
- ** 防撤回 (`anti_recall`)**：如题。
- ** 延迟测试 (`ping.py`)**：如题。

##  环境准备

- **Python**: 3.12+ 
- **框架**: NoneBot2
- **适配器**: OneBot V11 (建议配合 NapCat 使用)

##  快速启动

1. **克隆仓库并进入目录**：

   Bash

   ```
   git clone https://github.com/OpaqueMythril/bot_mythril.git
   cd myqqbot
   ```

2. **创建并激活虚拟环境**：

   Bash

   ```
   python -m venv venv
   source venv/bin/activate  # Linux/macOS
   # venv\Scripts\activate  # Windows
   ```

3. **安装依赖**：

   Bash

   ```
   pip install -r requirements.txt
   ```

4. **配置环境参数**： 复制一份 `.env.dev` 命名为 `.env`，并填入你自己的 `API_KEY` 和相关配置：

   Plaintext

   ```
   DRIVER=~fastapi
   COMMAND_START=["", "/"]
   SILICONFLOW_API_KEY=你的_KEY
   ```

5. **唤醒本喵**： 使用 NoneBot CLI 运行：

   Bash

   ```
   nb run --reload
   ```
