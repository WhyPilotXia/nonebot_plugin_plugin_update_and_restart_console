import asyncio
import os
import sys
import shutil
import subprocess
import nonebot
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from nonebot import get_driver, logger
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets
from fastapi import Request



# ================= 核心路径配置 =================
PLUGIN_DIR = Path(__file__).parent
BACKUP_DIR = PLUGIN_DIR.parent

# 正确获取 FastAPI 实例（你原来的写法，不报错）
app: FastAPI = nonebot.get_app()
driver = get_driver()

security = HTTPBasic()

USERNAME = "admin"
PASSWORD = "songyunzhang"  # 改成你自己的

def verify(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = secrets.compare_digest(credentials.username, USERNAME)
    correct_password = secrets.compare_digest(credentials.password, PASSWORD)

    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="认证失败",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def get_ip(request: Request):
    # 如果你用了反代（nginx），优先取 X-Forwarded-For
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host


# ================= 工具函数 =================
def get_plugin_files():
    files = []
    for f in os.listdir(PLUGIN_DIR):
        if f.endswith(".py") and os.path.isfile(PLUGIN_DIR / f):
            files.append(f)
    return sorted(files)

# ================= Web 面板页面 =================
@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: str = Depends(verify)):
    ip = get_ip(request)
    logger.info(f"[访问] IP={ip} 用户={user} 访问首页")
    files = get_plugin_files()
    file_list_html = ""
    for f in files:
        file_list_html += f"""
        <tr>
            <td>{f}</td>
            <td><a href="/delete?filename={f}" onclick="return confirm('确定删除 {f} 吗？')">🗑️ 删除</a></td>
        </tr>
        """

    return f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>插件远程管理</title>
    <style>
        body{{font-family:Microsoft YaHei;margin:30px}}
        .container{{max-width:700px;margin:0 auto}}
        .section{{margin:20px 0;padding:20px;border:1px solid #ddd;border-radius:8px}}
        table{{width:100%;border-collapse:collapse}}
        td,th{{padding:10px;border-bottom:1px solid #ddd}}
        .btn{{padding:8px 16px;background:#409eff;color:white;border:none;border-radius:4px;cursor:pointer}}
        .btn-red{{background:#f56c6c}}
    </style>
</head>
<body>
<div class="container">
    <h2>插件远程管理面板</h2>

    <div class="section">
        <h3>上传插件文件（覆盖）</h3>
        <form action="/upload" method="post" enctype="multipart/form-data">
            <input type="file" name="file" required>
            <button class="btn" type="submit">上传并覆盖</button>
        </form>
    </div>

    <div class="section">
        <h3>插件文件列表</h3>
        <table>
            <tr><th>文件名</th><th>操作</th></tr>
            {file_list_html}
        </table>
    </div>

    <div class="section">
        <h3>机器人控制</h3>
        <form action="/restart" method="post">
            <button class="btn btn-red" type="submit" onclick="return confirm('确定重启？')">重启机器人</button>
        </form>
    </div>
</div>
</body>
</html>
    """

# ================= 上传文件 =================
@app.post("/upload", response_class=HTMLResponse)
async def upload_file(request: Request, file: UploadFile = File(...), user: str = Depends(verify)):
    ip = get_ip(request)
    logger.info(f"[上传] IP={ip} 用户={user} 文件={file.filename}")
    try:
        file_path = PLUGIN_DIR / file.filename
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return f"<h3>✅ 上传成功：{file.filename}</h3><a href='/manager'>返回</a>"
    except Exception as e:
        return f"<h3>❌ 上传失败：{e}</h3><a href='/manager'>返回</a>"

# ================= 删除文件（移动到 /src 备份） =================
@app.get("/delete", response_class=HTMLResponse)
async def delete_file(request: Request, filename: str, user: str = Depends(verify)):
    ip = get_ip(request)
    logger.warning(f"[删除] IP={ip} 用户={user} 文件={filename}")
    src = PLUGIN_DIR / filename
    dst = BACKUP_DIR / filename

    if not src.exists():
        return f"<h3>❌ 文件不存在</h3><a href='/manager'>返回</a>"

    try:
        if dst.exists():
            dst.unlink()
        shutil.move(str(src), str(dst))
        return f"<h3>✅ 已删除并备份到 /src 目录</h3><a href='/manager'>返回</a>"
    except Exception as e:
        return f"<h3>❌ 删除失败：{e}</h3><a href='/manager'>返回</a>"

# ================= 重启机器人 =================
@app.post("/restart", response_class=HTMLResponse)
async def restart_bot(request: Request, user: str = Depends(verify)):
    ip = get_ip(request)
    logger.error(f"[重启] IP={ip} 用户={user} 执行重启")
    try:
        python = sys.executable
        script = sys.argv[0]

        subprocess.Popen([python, script], cwd=Path(script).parent)

        # 延迟退出（让HTTP响应先返回）
        asyncio.get_event_loop().call_later(1, lambda: sys.exit(0))

        return "<h3>🔄 重启中...</h3>"
    except Exception as e:
        return f"<h3>❌ 重启失败：{e}</h3>"