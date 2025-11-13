from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os
import uvicorn
import logging
import json
import asyncio
import socket
import tempfile
import qrcode

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("server_qr_render")

# ---------- FastAPI 初始化 ----------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory="static"), name="static")

# ---------- AI 客戶端 ----------
try:
    from openai import AsyncOpenAI
    client = AsyncOpenAI()
    logger.info("OpenAI client initialized.")
except Exception:
    client = None
    logger.warning("⚠️ 未安裝 openai 或未設定 API key，AI 主題功能停用")

# ---------- 全域狀態 ----------
rooms: dict[str, set[WebSocket]] = {}
rooms_lock = asyncio.Lock()
roomThemes: dict[str, str] = {}

# ---------- 廣播函式 ----------
async def broadcast(room: str, message: str, sender: WebSocket | None = None):
    async with rooms_lock:
        sockets = rooms.get(room, set()).copy()
    to_remove = []
    for ws in sockets:
        try:
            await ws.send_text(message)
        except Exception:
            to_remove.append(ws)
    if to_remove:
        async with rooms_lock:
            for ws in to_remove:
                rooms[room].discard(ws)

# ---------- WebSocket Endpoint ----------
@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str):
    await websocket.accept()
    async with rooms_lock:
        if room_id not in rooms:
            rooms[room_id] = set()
        rooms[room_id].add(websocket)
    logger.info(f"WebSocket connected: room={room_id}")

    # 傳送當前主題
    if room_id in roomThemes:
        await websocket.send_text(json.dumps({"type": "themeUpdate", "theme": roomThemes[room_id]}))

    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)

            # AI 主題生成
            if msg.get("type") == "generateTheme" and client:
                completion = await client.chat.completions.create(
                    model="gpt-5-mini",
                    messages=[
                        {"role": "system", "content": "You are a creative theme generator for a drawing game."},
                        {"role": "user", "content": "Generate a fun and creative drawing theme in 5–10 words."}
                    ],
                    temperature=0.9
                )
                theme = completion.choices[0].message.content.strip()
                roomThemes[room_id] = theme
                await broadcast(room_id, json.dumps({"type": "themeUpdate", "theme": theme}))
            else:
                await broadcast(room_id, data, sender=websocket)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: room={room_id}")
    finally:
        async with rooms_lock:
            rooms.get(room_id, set()).discard(websocket)
            if not rooms[room_id]:
                del rooms[room_id]

# ---------- HTTP 端點 ----------
@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "FastAPI on Render is working!"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

# ---------- 取得本地 IP ----------
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# ---------- QR Code 生成 ----------
def show_qr_code(room="room1"):
    host = os.getenv("RENDER_EXTERNAL_HOSTNAME") or get_local_ip()
    port = os.getenv("PORT", "8000")
    url = f"http://{host}:{port}/static/index.html?room={room}&name=User"
    print(f"\n🔗 手機掃描以下 QR Code 加入房間：\n{url}\n")

    img = qrcode.make(url)
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    img.save(tmp.name)
    print(f"✅ 已生成 QR Code: {tmp.name}")

    # 嘗試自動開啟
    try:
        import platform
        if platform.system() == "Darwin":
            os.system(f"open {tmp.name}")
        elif platform.system() == "Windows":
            os.system(f"start {tmp.name}")
        else:
            os.system(f"xdg-open {tmp.name}")
    except Exception:
        logger.warning("⚠️ 無法自動開啟圖片，請手動查看。")

# ---------- 主程式 ----------
if __name__ == "__main__":
    show_qr_code("room1")
    port = int(os.getenv("PORT", 8000))
    logger.info(f"Starting server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port)



