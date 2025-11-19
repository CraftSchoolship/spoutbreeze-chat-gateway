from pydantic import BaseModel
from typing import Optional, Dict, Any

class NormalizedMessage(BaseModel):
    platform: str
    type: str = "message"
    user: Dict[str, Any]
    text: str
    timestamp: Optional[str] = None
    message_id: Optional[str] = None

class IncomingMessage(BaseModel):
    platform: str
    user_id: Optional[str] = None
    user_name: str
    content: str
    message_id: Optional[str] = None

class OutboundMessage(BaseModel):
    type: str = "outbound_message"
    platform: str
    text: str
    user: Optional[Dict[str, Any]] = None