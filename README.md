#  mabot

基于 **NoneBot2** 框架开发的QQ 机器人


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

5. **唤醒**： 使用 NoneBot CLI 运行：

   Bash

   ```
   nb run --reload
   ```
