from fastapi import WebSocket


class WebSocketManager:
    def __init__(self) -> None:
        self.active: dict[WebSocket, dict[str, str | None]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active[websocket] = {"project": None, "environment": None}

    def disconnect(self, websocket: WebSocket) -> None:
        self.active.pop(websocket, None)

    def set_subscription(
        self,
        websocket: WebSocket,
        *,
        project: str | int | None,
        environment: str | int | None,
    ) -> None:
        if websocket not in self.active:
            return
        self.active[websocket] = {
            "project": str(project) if project is not None else None,
            "environment": str(environment) if environment is not None else None,
        }

    def _should_deliver(self, meta: dict[str, str | None], message: dict) -> bool:
        if message.get("type") != "log:new":
            return True
        data = message.get("data") or {}
        subscribed_project = meta.get("project")
        subscribed_environment = meta.get("environment")
        if not subscribed_project and not subscribed_environment:
            return False
        log_project = data.get("project")
        log_environment = data.get("environment")
        if subscribed_project and str(log_project) != str(subscribed_project):
            return False
        if subscribed_environment and str(log_environment) != str(subscribed_environment):
            return False
        return True

    async def broadcast(self, message: dict) -> None:
        dead: list[WebSocket] = []
        for ws, meta in list(self.active.items()):
            if not self._should_deliver(meta, message):
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


ws_manager = WebSocketManager()
