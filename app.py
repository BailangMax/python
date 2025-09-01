# -------------------------
# 优化后的代码示例 (部分)
# -------------------------

import os
import re
import json
import asyncio
import platform
import logging
from pathlib import Path
from dataclasses import dataclass, field

import httpx  # 替代 requests
import aiofiles # 异步文件操作
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

# --- 1. 优化点: 使用 logging 模块 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


# --- 2. 优化点: 集中化、类型安全的配置 ---
@dataclass
class Config:
    """集中管理所有环境变量配置"""
    UPLOAD_URL: str = os.environ.get('UPLOAD_URL', '')
    PROJECT_URL: str = os.environ.get('PROJECT_URL', '')
    AUTO_ACCESS: bool = os.environ.get('AUTO_ACCESS', 'false').lower() == 'true'
    # 使用 Path 对象处理路径
    FILE_PATH: Path = Path(os.environ.get('FILE_PATH', './.cache'))
    SUB_PATH: str = os.environ.get('SUB_PATH', 'sub')
    UUID: str = os.environ.get('UUID', 'ff24ebc4-8b2f-4eae-a40b-0fe47473541f')
    NEZHA_SERVER: str = os.environ.get('NEZHA_SERVER', '')
    NEZHA_PORT: str = os.environ.get('NEZHA_PORT', '')
    NEZHA_KEY: str = os.environ.get('NEZHA_KEY', '')
    ARGO_DOMAIN: str = os.environ.get('ARGO_DOMAIN', '')
    ARGO_AUTH: str = os.environ.get('ARGO_AUTH', '')
    NAME: str = os.environ.get('NAME', 'Vls')
    PORT: int = int(os.environ.get('SERVER_PORT') or os.environ.get('PORT') or 3000)
    
    # 派生路径
    SUB_FILE: Path = field(init=False)
    LIST_FILE: Path = field(init=False)
    CONFIG_FILE: Path = field(init=False)
    BOOT_LOG_FILE: Path = field(init=False)
    NPM_BIN: Path = field(init=False)
    PHP_BIN: Path = field(init=False)
    WEB_BIN: Path = field(init=False)
    BOT_BIN: Path = field(init=False)

    def __post_init__(self):
        """在初始化后自动生成完整的路径"""
        self.SUB_FILE = self.FILE_PATH / 'sub.txt'
        self.LIST_FILE = self.FILE_PATH / 'list.txt'
        self.CONFIG_FILE = self.FILE_PATH / 'config.json'
        self.BOOT_LOG_FILE = self.FILE_PATH / 'boot.log'
        self.NPM_BIN = self.FILE_PATH / 'npm'
        self.PHP_BIN = self.FILE_PATH / 'php'
        self.WEB_BIN = self.FILE_PATH / 'web'
        self.BOT_BIN = self.FILE_PATH / 'bot'
        
# 在脚本开始时实例化配置
config = Config()

# --- 3. 优化点: 异步子进程执行 ---
async def execute_command(command: str) -> tuple[str, str]:
    """异步执行 shell 命令并返回输出"""
    process = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return stdout.decode().strip(), stderr.decode().strip()

# --- 4. 优化点: 异步文件下载 ---
async def download_file(client: httpx.AsyncClient, file_name: str, file_url: str, target_path: Path):
    """使用 httpx 异步下载文件"""
    logging.info(f"Downloading {file_name} from {file_url}...")
    try:
        async with client.stream('GET', file_url, timeout=60) as response:
            response.raise_for_status()
            async with aiofiles.open(target_path, 'wb') as f:
                async for chunk in response.aiter_bytes():
                    await f.write(chunk)
        logging.info(f"Successfully downloaded {target_path}")
        return True
    except httpx.HTTPStatusError as e:
        logging.error(f"Download failed for {file_name}: HTTP {e.response.status_code}")
    except Exception as e:
        logging.error(f"An unexpected error occurred while downloading {file_name}: {e}")
    return False

# --- 5. 优化点: 拆分后的、完全异步的函数 ---
async def setup_environment():
    """创建目录并清理旧文件"""
    logging.info("Setting up environment...")
    config.FILE_PATH.mkdir(exist_ok=True)
    # (清理文件的逻辑可以放在这里)

async def run_background_process(name: str, command: str):
    """以 nohup 方式异步启动后台进程"""
    # nohup 和 & 使得命令在后台运行，我们不需要等待它完成
    logging.info(f"Starting background process: {name}")
    process = await asyncio.create_subprocess_shell(f"nohup {command} >/dev/null 2>&1 &")
    # 我们不调用 process.communicate()，因为我们不想等待它
    await process.wait() # 等待子进程被 shell 成功启动
    logging.info(f"{name} process started.")

async def start_services():
    """下载并启动所有必要的服务"""
    architecture = 'arm' if 'aarch64' in platform.machine().lower() else 'amd'
    
    # 定义文件下载源
    files_to_download = {
        config.WEB_BIN: f"https://{architecture}64.ssss.nyc.mn/web",
        config.BOT_BIN: f"https://{architecture}64.ssss.nyc.mn/2go"
    }
    if config.NEZHA_SERVER and config.NEZHA_KEY:
        if config.NEZHA_PORT:
             files_to_download[config.NPM_BIN] = f"https://{architecture}64.ssss.nyc.mn/agent"
        else:
             files_to_download[config.PHP_BIN] = f"https://{architecture}64.ssss.nyc.mn/v1"

    # 使用一个 httpx.AsyncClient 会话来复用连接
    async with httpx.AsyncClient() as client:
        download_tasks = [
            download_file(client, path.name, url, path) 
            for path, url in files_to_download.items()
        ]
        results = await asyncio.gather(*download_tasks)
        if not all(results):
            logging.error("One or more file downloads failed. Aborting.")
            return

    # 授权文件
    for file_path in files_to_download.keys():
        if file_path.exists():
            file_path.chmod(0o775)
            logging.info(f"Set execute permission for {file_path}")

    # (生成 config.json 和其他配置文件的逻辑...)
    logging.info("Configurations generated.")

    # 启动后台服务
    tasks = []
    tasks.append(run_background_process("web", f"{config.WEB_BIN} -c {config.CONFIG_FILE}"))
    
    # 启动哪吒 Agent (示例)
    if config.PHP_BIN.exists():
         tasks.append(run_background_process("php", f"{config.PHP_BIN} -c 'config.yaml'")) # 注意：config.yaml 的生成逻辑需要补充
    
    # 启动 Argo Tunnel (示例)
    args = f'tunnel --edge-ip-version auto --no-autoupdate --url http://localhost:{config.PORT}'
    tasks.append(run_background_process("bot", f"{config.BOT_BIN} {args}"))
    
    await asyncio.gather(*tasks)
    
    logging.info("All services have been started.")


async def main():
    """主异步入口"""
    await setup_environment()
    
    # 在后台启动HTTP服务器
    server_thread = Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # 启动核心服务并获取订阅链接
    await start_services()

    # (获取 Argo 域名、生成订阅、发送通知等逻辑...)
    logging.info("Extracting domain and generating subscription...")
    # ...

    logging.info("Setup complete. Application is running.")
    # 保持主程序运行
    while True:
        await asyncio.sleep(3600)

def run_server():
    """同步运行的 HTTP 服务器 (保持不变)"""
    # 这个函数已经在线程中运行，所以同步是OK的
    server = HTTPServer(('0.0.0.0', config.PORT), RequestHandler)
    logging.info(f"HTTP server is running on port {config.PORT}")
    server.serve_forever()

# RequestHandler 类和其他同步函数可以保持原样...
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        # ...
        pass
    def log_message(self, format, *args):
        pass # 保持安静

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Application stopped by user.")
