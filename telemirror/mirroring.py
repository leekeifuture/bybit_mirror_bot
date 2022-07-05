import logging
from typing import Dict, List, Union

import discord
from telethon import events
from telethon.sessions import StringSession
from telethon.sync import TelegramClient
from telethon.tl import types

from config import DISCORD_GUILD_ID, DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID
from .messagefilters import EmptyMessageFilter, MesssageFilter
from .storage import Database, MirrorMessage


async def send_to_discord_chat(text):
    intents = discord.Intents.all()
    client = NonInteractiveClient(intents=intents, text=text)
    client.run(DISCORD_BOT_TOKEN)


async def send_message_to_discord_chat(client, text):
    guild = client.get_guild(DISCORD_GUILD_ID)
    channel = guild.get_channel(DISCORD_CHANNEL_ID)
    await channel.send(text)


class NonInteractiveClient(discord.Client):
    def __init__(self, *, intents=None, text=None):
        super().__init__(intents=intents)
        self.text = text

    async def on_ready(self):
        await self.wait_until_ready()
        await send_message_to_discord_chat(self, self.text)
        await self.close()

    async def on_error(self, event, *args, **kwargs):
        raise


class EventHandlers:
    async def on_new_message(self: 'MirrorTelegramClient', event) -> None:
        """NewMessage event handler"""

        if hasattr(event, 'grouped_id') and event.grouped_id is not None:
            # skip if Album
            return

        incoming_message: types.Message = event.message
        incoming_chat: int = event.chat_id

        self._logger.info(
            f'New message from {incoming_chat}:\n{incoming_message}')

        try:
            outgoing_chats = self._mirror_mapping.get(incoming_chat)
            if outgoing_chats is None or len(outgoing_chats) < 1:
                self._logger.warning(f'No target chats for {incoming_chat}.')
                return

            incoming_message = self._message_filter.process(incoming_message)
            for outgoing_chat in outgoing_chats:
                if isinstance(incoming_message.media, types.MessageMediaPoll):
                    await send_to_discord_chat(event.message.message)
                    outgoing_message = await self.send_message(outgoing_chat,
                                                               file=types.InputMediaPoll(
                                                                   poll=incoming_message.media.poll))
                else:
                    await send_to_discord_chat(event.message.message)
                    outgoing_message = await self.send_message(outgoing_chat,
                                                               event.message)

                if outgoing_message is not None:
                    self._database.insert(
                        MirrorMessage(original_id=incoming_message.id,
                                      original_channel=incoming_chat,
                                      mirror_id=outgoing_message.id,
                                      mirror_channel=outgoing_chat))
        except Exception as e:
            self._logger.error(e, exc_info=True)

    async def on_album(self: 'MirrorTelegramClient', event) -> None:
        """Album event handler"""

        incoming_album: List[types.Message] = event.messages
        incoming_chat: int = event.chat_id

        self._logger.info(f'New album from {incoming_chat}')

        try:
            outgoing_chats = self._mirror_mapping.get(incoming_chat)
            if outgoing_chats is None or len(outgoing_chats) < 1:
                self._logger.warning(f'No target chats for {incoming_chat}.')
                return

            files = []
            captions = []
            source_message_ids = []

            for incoming_message in incoming_album:
                incoming_message = self._message_filter.process(
                    incoming_message)
                files.append(incoming_message.media)
                captions.append(incoming_message.message)
                source_message_ids.append(incoming_message.id)

            for outgoing_chat in outgoing_chats:
                outgoing_messages = await self.send_file(
                    outgoing_chat, caption=captions, file=files)

                if outgoing_messages is not None and len(outgoing_messages) > 1:
                    for i, outgoing_message in enumerate(outgoing_messages):
                        self._database.insert(
                            MirrorMessage(original_id=source_message_ids[i],
                                          original_channel=incoming_chat,
                                          mirror_id=outgoing_message.id,
                                          mirror_channel=outgoing_chat))
        except Exception as e:
            self._logger.error(e, exc_info=True)

    async def on_edit_message(self: 'MirrorTelegramClient', event) -> None:
        """MessageEdited event handler"""

        if event.message.edit_hide is True:
            # skip if edit_hide (reactions and so on...)
            return

        incoming_message: types.Message = event.message
        incoming_chat: int = event.chat_id

        self._logger.info(
            f'Edit message from {incoming_chat}#{incoming_message.id}')

        try:
            outgoing_messages = self._database.get_messages_to_edit(
                incoming_message.id, incoming_chat)
            if outgoing_messages is None or len(outgoing_messages) < 1:
                self._logger.warning(
                    f'No target messages for {incoming_chat}.')
                return

            incoming_message = self._message_filter.process(incoming_message)
            for outgoing_message in outgoing_messages:
                await self.edit_message(outgoing_message.mirror_channel,
                                        outgoing_message.mirror_id,
                                        incoming_message.message)
        except Exception as e:
            self._logger.error(e, exc_info=True)


class Mirroring(EventHandlers):

    def configure_mirroring(
            self: 'MirrorTelegramClient',
            source_chats: List[int],
            mirror_mapping: Dict[int, List[int]],
            database: Database,
            message_filter: MesssageFilter = EmptyMessageFilter(),
            logger: Union[str, logging.Logger] = None
    ) -> None:
        """Configure channels mirroring

        Args:
            source_chats (`List[int]`): Source chats ID list
            mirror_mapping (`Dict[int, List[int]]`): Mapping dictionary: {source: [target1, target2...]}
            database (`Database`): Message ID storage
            message_filter (`MesssageFilter`, optional): Message filter. Defaults to `EmptyMessageFilter`.
            logger (`str` | `logging.Logger`, optional): Logger. Defaults to None.
        """
        self._database = database
        self._mirror_mapping = mirror_mapping
        self._message_filter = message_filter

        if isinstance(logger, str):
            logger = logging.getLogger(logger)
        elif not isinstance(logger, logging.Logger):
            logger = logging.getLogger(__name__)

        self._logger = logger

        self.add_event_handler(self.on_new_message,
                               events.NewMessage(chats=source_chats))
        self.add_event_handler(self.on_album, events.Album(chats=source_chats))
        self.add_event_handler(self.on_edit_message,
                               events.MessageEdited(chats=source_chats))

    def start_mirroring(self: 'MirrorTelegramClient') -> None:
        """Start channels mirroring"""
        self.start()
        if self.is_user_authorized():
            me = self.get_me()
            self._logger.info(f'Authorized as {me.username} ({me.phone})')
            self._logger.info('Channels mirroring was started...')
            self.run_until_disconnected()
        else:
            self._logger.error('Cannot be authorized. Try to restart')


class MirrorTelegramClient(Mirroring, TelegramClient):

    def __init__(self, session_string: str = None, *args, **kwargs):
        super().__init__(StringSession(session_string), *args, **kwargs)

    def print_session_string(self: 'MirrorTelegramClient') -> None:
        """Prints session string"""
        print('Session string: ', self.session.save())
