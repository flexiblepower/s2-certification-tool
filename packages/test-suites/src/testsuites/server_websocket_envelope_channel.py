from connectivity.channel import Channel
from .envelope_models import ServerMessageEnvelope, parse_envelope


class ServerWebsocketConnectionChannel(Channel[ServerMessageEnvelope, str]):
    async def send(self, message: ServerMessageEnvelope):
        str_msg: str = message.model_dump_json()

        return await self.connection.send(str_msg)

    async def process_received_message(self, str_msg: str):

        message = parse_envelope(str_msg)

        await self.message_queue.put(message)
