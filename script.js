// script.js
const urlParams = new URLSearchParams(window.location.search);
const room = urlParams.get("room") || "default";
const name = urlParams.get("name") || "anonymous";

// ⚠️ 請修改這行為你的雲端伺服器網址
const serverUrl = "wss://your-backend.onrender.com/ws";  

const ws = new WebSocket(`${serverUrl}?room=${room}&name=${name}`);

ws.onopen = () => console.log("✅ WebSocket 已連線");

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  if (typeof handleMessage === "function") handleMessage(data);
};
