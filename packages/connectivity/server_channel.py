import json
from typing import Optional
from connectivity.channel import Channel
from connectivity.server_models import (
    ControlMessageEnvelope,
    LogMessageEnvelope,
    S2MessageEnvelope,
    ServerMessageEnvelope,
    MessageEnvelopeTypeEnum,
)


class ServerChannel(Channel[ServerMessageEnvelope, str]):

    async def process_received_message(self, message: str) -> ServerMessageEnvelope:
        msg_json = json.loads(message)

        envelope: Optional[ServerMessageEnvelope]
        match msg_json["message_type"]:
            case MessageEnvelopeTypeEnum.CONTROL:
                envelope = ControlMessageEnvelope.model_validate_json(message)
            case MessageEnvelopeTypeEnum.S2:
                envelope = S2MessageEnvelope.model_validate_json(message)
            case MessageEnvelopeTypeEnum.LOG:
                envelope = LogMessageEnvelope.model_validate_json(message)

        if envelope is None:
            raise ValueError("Invalid Envelope.")

        return envelope

    def send(self, message: ServerMessageEnvelope):
        str_msg = message.model_dump_json()
        return super().send(str_msg)
