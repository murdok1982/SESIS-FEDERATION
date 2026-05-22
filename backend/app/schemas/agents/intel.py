from pydantic import BaseModel


class IntelReport(BaseModel):
    title: str
    body: str
    classification: str = "restricted"
    source: str = ""
