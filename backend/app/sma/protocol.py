from enum import Enum
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime

class Performative(str, Enum):
    CFP = "CALL_FOR_PROPOSAL"
    BID = "BID"
    ACCEPT_PROPOSAL = "ACCEPT_PROPOSAL"
    REJECT_PROPOSAL = "REJECT_PROPOSAL"
    INFORM = "INFORM"
    FAILURE = "FAILURE"

class FIPAACLMessage(BaseModel):
    conversation_id: str = Field(default_factory=lambda: datetime.now().strftime("%Y%m%d%H%M%S%f"))
    sender: str
    receiver: str
    performative: Performative
    content: Dict[str, Any]
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    in_reply_to: Optional[str] = None