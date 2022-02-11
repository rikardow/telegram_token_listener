import asyncio
from asyncio.log import logger
import logging
import os
import re
import sys

from dotenv import load_dotenv
from telethon import TelegramClient, events, functions, types
from telethon.errors.rpcerrorlist import UsernameNotOccupiedError, UsernameInvalidError

# These example values won't work. You must get your own api_id and
# api_hash from https://my.telegram.org, under API Development.
from pancake import Pancake

api_id = 12529301
api_hash = 'd8bc56fa63dc3ae0a5ad091e496bc6b0'


def init():
    logging.basicConfig(
        level=logging.INFO, filename="log.log", filemode="w",
        format="%(asctime)-15s %(levelname)-8s %(message)s"
    )
    logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))

    if not os.path.exists('.env'):
        logger.error(".env file doesn't exists")
        exit(0)

    load_dotenv()


async def main():
    init()
    client = TelegramClient('CustomClient', api_id, api_hash)
    await client.start(phone=lambda: os.environ.get('CELLPHONE'))

    me = await client.get_me()
    logging.info(f"Signed in as {me.first_name}")
    logging.info('========================================')

    channels = os.environ.get('CHANNELS').split(',')

    for channel in channels:
        not_exists = await client(functions.account.CheckUsernameRequest(channel))
        if not_exists:
            logging.error(f"Channel {channel} doesn't exists")
            exit(0)

    client.add_event_handler(
        on_new_message, events.NewMessage(from_users=channels))


async def on_new_message(event: events.NewMessage.Event):
    logging.info('New message received')
    content: str = event.message.message
    token = None

    is_ama = re.findall(r'\bAMA \bANNOUNCEMENT', content, re.IGNORECASE)
    if is_ama:
        print('Is an AMA announcement, ignoring')
        return

    pancake_results = re.findall(r'outputCurrency=0[xX][a-zA-Z0-9]{40}', content)
    if pancake_results:
        token = pancake_results[0].replace('outputCurrency=', '')
        logging.info(f'Token found in pancake link {token}')
    else:
        results = re.findall(r'0[xX][a-zA-Z0-9]{40}', content)
        if results:
            token = results[0]
            logging.info(f'Token found {token}')

    if token:
        pancake = Pancake()

        has_liquidity, is_bnb_pair = pancake.check_liquidity(token)
        while not has_liquidity:
            has_liquidity, is_bnb_pair = pancake.check_liquidity(token)

        pancake.buy_tokens(token, bnb_pair=is_bnb_pair)


loop = asyncio.get_event_loop()
task = asyncio.gather(main())
try:
    loop.run_forever()
except KeyboardInterrupt:
    logging.info('\nCanceling tasks\n')
    logging.disable(logging.ERROR)
    loop.stop()
    # loop.close()
