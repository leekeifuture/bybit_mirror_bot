import logging
import math
import shutil
from typing import Dict, List, Union

import discord
from telethon import events
from telethon.sessions import StringSession
from telethon.sync import TelegramClient
from telethon.tl import types

from config import DISCORD_GUILD_ID, DISCORD_BOT_TOKEN, DISCORD_CHANNEL_ID
from .messagefilters import EmptyMessageFilter, MesssageFilter


async def send_to_discord_chat(message, logger):
    intents = discord.Intents.all()
    client = NonInteractiveClient(intents=intents, message=message,
                                  logger=logger)
    await client.start(DISCORD_BOT_TOKEN)


async def send_message_to_discord_chat(client, message, logger):
    guild = client.get_guild(DISCORD_GUILD_ID)
    channel = guild.get_channel(DISCORD_CHANNEL_ID)

    if message.media:
        downloads_dir = './downloads'
        file_name = 'file'
        if message.media.document and \
                message.media.document.attributes[1].file_name:
            file_name = message.media.document.attributes[1].file_name

        logger.info('Downloading file...')

        i = int(math.floor(math.log(message.file.size, 1024)))
        p = math.pow(1024, i)
        file_sile = round(message.file.size / p, 2)

        if file_sile >= 8:
            logger.info(
                'Sending message without file because of more than 8MB...'
            )
            additional_text = f'{message.message}\n\n' \
                if message.message \
                else ''
            await channel.send(
                additional_text +
                f'https://t.me/{message.chat.username}/{message.id}'
            )
        else:
            logger.info('Downloading file...')
            file = await message.download_media(
                file=f'{downloads_dir}/{file_name}'
            )
            logger.info('Sending message with file...')
            await channel.send(message.message, file=discord.File(file))

        logger.info('Removing downloaded files...')
        shutil.rmtree(downloads_dir)
    else:
        await channel.send(message.message)

    logger.info('Message sent!')


class NonInteractiveClient(discord.Client):
    def __init__(self, *, intents=None, message=None, logger=None):
        super().__init__(intents=intents)
        self.message = message
        self.logger = logger

    async def on_ready(self):
        await self.wait_until_ready()
        await send_message_to_discord_chat(self, self.message, self.logger)
        await self.close()

    async def on_error(self, event, *args, **kwargs):
        raise


class EventHandlers:
    async def on_new_message(self: 'MirrorTelegramClient', event) -> None:
        """NewMessage event handler"""

        incoming_message: types.Message = event.message
        incoming_chat: int = event.chat_id

        self._logger.info(
            f'New message from {incoming_chat}:\n{incoming_message}')

        try:
            await send_to_discord_chat(incoming_message, self._logger)
        except Exception as e:
            self._logger.error(e, exc_info=True)


class Mirroring(EventHandlers):
    def configure_mirroring(
            self: 'MirrorTelegramClient',
            source_chats: List[int],
            mirror_mapping: Dict[int, List[int]],
            message_filter: MesssageFilter = EmptyMessageFilter(),
            logger: Union[str, logging.Logger] = None
    ) -> None:
        """Configure channels mirroring

        Args:
            source_chats (`List[int]`): Source chats ID list
            mirror_mapping (`Dict[int, List[int]]`): Mapping dictionary: {source: [target1, target2...]}
            message_filter (`MesssageFilter`, optional): Message filter. Defaults to `EmptyMessageFilter`.
            logger (`str` | `logging.Logger`, optional): Logger. Defaults to None.
        """
        self._mirror_mapping = mirror_mapping
        self._message_filter = message_filter

        if isinstance(logger, str):
            logger = logging.getLogger(logger)
        elif not isinstance(logger, logging.Logger):
            logger = logging.getLogger(__name__)

        self._logger = logger

        self.add_event_handler(self.on_new_message,
                               events.NewMessage(chats=source_chats))

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
