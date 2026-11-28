import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class MessageInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    received_time: datetime.datetime
    from_server: bool
    sub_msg_name: str
    obf_msg_json: dict[str, Any] | None = None
    msg_json: dict[str, Any] | None = None
