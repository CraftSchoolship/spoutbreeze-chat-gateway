from typing import Callable, Dict, Any
from fastapi import FastAPI
from pydantic import BaseModel
from uuid import uuid4

class Event(BaseModel):
    id: str
    type: str
    data: Dict[str, Any]

class EventHandler:
    def __init__(self):
        self.handlers: Dict[str, Callable[[Event], None]] = {}

    def register(self, event_type: str, handler: Callable[[Event], None]) -> None:
        self.handlers[event_type] = handler

    def dispatch(self, event: Event) -> None:
        handler = self.handlers.get(event.type)
        if handler:
            handler(event)

event_handler = EventHandler()

def create_app() -> FastAPI:
    app = FastAPI()

    @app.post("/events")
    async def handle_event(event: Event):
        event.id = str(uuid4())  # Assign a unique ID to the event
        event_handler.dispatch(event)
        return {"status": "event dispatched", "event_id": event.id}

    return app

app = create_app()