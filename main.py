import logging

from config import (API_HASH, API_ID, CHAT_MAPPING, LOG_LEVEL,
                    REMOVE_URLS)
from config import REMOVE_URLS_LIST as URLS_BLACKLIST
from config import REMOVE_URLS_WHITELIST as URLS_WHITELIST
from config import SESSION_STRING, SOURCE_CHATS
from telemirror.messagefilters import EmptyMessageFilter, UrlMessageFilter
from telemirror.mirroring import MirrorTelegramClient


def main():
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.setLevel(level=LOG_LEVEL)

    if REMOVE_URLS:
        message_filter = UrlMessageFilter(
            blacklist=URLS_BLACKLIST, whitelist=URLS_WHITELIST)
    else:
        message_filter = EmptyMessageFilter()

    client = MirrorTelegramClient(SESSION_STRING, API_ID, API_HASH)
    client.configure_mirroring(
        source_chats=SOURCE_CHATS,
        mirror_mapping=CHAT_MAPPING,
        message_filter=message_filter,
        logger=logger
    )
    client.start_mirroring()


if __name__ == "__main__":
    main()
