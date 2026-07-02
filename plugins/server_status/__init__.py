import psutil
import platform
from datetime import datetime
from typing import List, Dict, Any

from nonebot import on_command
from nonebot.permission import SUPERUSER
from nonebot.adapters.onebot.v11 import Bot, MessageEvent

# 仅限超级用户查看，保护服务器隐私
status_cmd = on_command("状态", aliases={"status", "服务器"}, priority=5, permission=SUPERUSER, block=True)

def get_size(bytes, suffix="B"):
    """
    格式化字节单位
    """
    factor = 1024
    for unit in ["", "K", "M", "G", "T", "P"]:
        if bytes < factor:
            return f"{bytes:.2f}{unit}{suffix}"
        bytes /= factor

def get_top_processes(n=5) -> str:
    """
    获取占用内存最高的前 n 个进程
    """
    processes: List[Dict[str, Any]] = []
    
    # 遍历所有运行中的进程
    for proc in psutil.process_iter(['pid', 'name', 'memory_percent', 'cpu_percent']):
        try:
            # 获取进程信息
            p_info = proc.info
            # 过滤掉一些系统空闲进程
            if p_info['name'] == "System Idle Process" or p_info['memory_percent'] == 0:
                continue
            processes.append(p_info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

    # 按内存占用排序
    processes.sort(key=lambda x: x['memory_percent'], reverse=True)
    
    top_list = []
    for p in processes[:n]:
        # 截断过长的进程名
        name = (p['name'][:15] + '..') if len(p['name']) > 15 else p['name']
        top_list.append(
            f"🔹 {name} (PID:{p['pid']})\n"
            f"   CPU: {p['cpu_percent']:.1f}% | 内存: {p['memory_percent']:.1f}%"
        )
    
    return "\n".join(top_list) if top_list else "暂无活跃进程信息"

@status_cmd.handle()
async def handle_status():
    # 1. 系统基础信息
    uname = platform.uname()
    boot_time = datetime.fromtimestamp(psutil.boot_time())
    uptime = datetime.now() - boot_time
    
    # 2. 资源占用
    cpu_usage = psutil.cpu_percent(interval=0.5)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage('/')
    
    # 3. 获取主要进程详情
    process_info = get_top_processes(5)

    # 4. 组装看板
    report = (
        f"📊 【本喵的云端宿主 Pro 报告】\n"
        f"━━━━━━━━━━━━━━\n"
        f"🖥️ 系统: {uname.system} {uname.release}\n"
        f"⏰ 运行时间: {str(uptime).split('.')[0]}\n"
        f"🔥 CPU 总占用: {cpu_usage}%\n"
        f"🧠 内存: {get_size(mem.used)} / {get_size(mem.total)} ({mem.percent}%)\n"
        f"💾 硬盘: {get_size(disk.used)} / {get_size(disk.total)} ({disk.percent}%)\n"
        f"━━━━━━━━━━━━━━\n"
        f"🔝 【TOP 5 资源消耗榜】\n"
        f"{process_info}\n"
        f"━━━━━━━━━━━━━━\n"
        f"艾玛，目前一切都在掌控之中！特呵呵呵~"
    )
    
    await status_cmd.finish(report)