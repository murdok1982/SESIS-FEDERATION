from pydantic import BaseModel
from typing import Optional


class WearableEvent(BaseModel):
    event_type: str
    agent_id: str
    timestamp: str
    payload: dict = {}
