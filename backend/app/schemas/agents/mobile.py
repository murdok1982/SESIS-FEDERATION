from pydantic import BaseModel
from typing import Optional


class DeviceRegistration(BaseModel):
    device_id: str
    device_name: str
    platform: str
    public_key: Optional[str] = None
