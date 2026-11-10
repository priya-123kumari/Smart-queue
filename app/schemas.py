from typing import Literal
from pydantic import BaseModel, Field

class TicketIn(BaseModel):
    customer_name: str = Field("Anonymous", max_length=80)
    plan_tier: Literal["free", "pro", "enterprise"] = "free"
    channel: Literal["email", "chat", "twitter"] = "email"
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)

class CategoryIn(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    keywords: str | list[str]
    team: str = Field("", max_length=40)
    base: int = Field(0, ge=0, le=5)

class FeedbackIn(BaseModel):
    ticket_id: str
    category: str

class DraftIn(BaseModel):
    tone: str = Field("friendly and concise", max_length=80)

class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

class ChatIn(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=50)
