import os
from time import sleep
from json import loads
from typing import Any, Dict, Optional, cast
from threading import Thread
from urllib.request import urlopen
from aminofix import Client, SubClient
from aminofix.lib.util.objects import Event, Message
from dotenv import load_dotenv

load_dotenv()

# parameters
EMAIL = os.getenv("EMAIL")
PASSWORD = os.getenv("PASSWORD")
DEVICE = os.getenv("DEVICE")

# messages
NO_PARAMS_ENV_MSG = "[@you]: setup the environment variable file (.env)"
NO_CHAT_BUBBLE_MSG = "[@{nickname!r}]: no chat-bubble detected!"
COPY_CONFIRMATION_MSG = "[@you]: copy bubble of {nickname!r}? [Y/n]"
COPY_SUCCESS_MSG = "[@{nickname!r}]: successfully copied!"

if not (EMAIL and PASSWORD and DEVICE):
    print(NO_PARAMS_ENV_MSG)
    with open('.env', 'w') as env:
        env.write("EMAIL=\nPASSWORD=\nDEVICE=")
    os._exit(1)


bot = Client(deviceId=DEVICE, socket_enabled=False)
bot.reconnect_thread = None  # type: ignore


def build_msg_params(gbot: Client, cbot: Optional[SubClient], event: Event) -> Dict[str, Any]:
    return dict(
        profile=cbot.profile if cbot else gbot.profile,
        comId=event.comId,
        chatId=event.message.chatId,
        nickname=(event.message.replyMessage or {}).get("author", {}).get("nickname")
    )


def confirm_copy() -> bool:
    content = input('>>> ').lower().strip()
    return any(map(lambda t: t in content, ['y', 'yes', 's', 'si']))


def extract_bubble_url(gbot: Client, cbot: SubClient, comId: int, chatId: str, messageId: str) -> Optional[str]:
    input()
    if not comId:
        message = gbot.get_message_info(chatId=chatId, messageId=messageId)
    else:
        message = cbot.get_message_info(chatId=chatId, messageId=messageId)
    return cast(Optional[str], message.json.get("chatBubble", {}).get("resourceUrl", None))


def generate_custom_bubble(cbot: SubClient, comId: int, bubbleSrc: bytes) -> Optional[str]:
    api = cbot.api.removesuffix('/')
    response = cbot.session.post(
        f"{api}/x{comId}/s/chat/chat-bubble/templates/107147e9-05c5-405f-8553-af65d2823457/generate",
        headers=cbot.parse_headers(type='application/octet-stream'),
        data=bubbleSrc,
        proxies=cbot.proxies,
        verify=cbot.certificatePath
    )
    data = loads(response.text)
    try:
        return data['chatBubble']['bubbleId']
    except KeyError:
        print("[@amino]:", data["api:message"])


def apply_bubble(cbot: SubClient, comId: int, bubbleSrc: bytes, bubbleId: str) -> None:
    api = cbot.api.removesuffix('/')
    cbot.session.post(
        f"{api}/x{comId}/s/chat/chat-bubble/{bubbleId}",
        headers=cbot.parse_headers(type='application/octet-stream'),
        data=bubbleSrc,
        proxies=cbot.proxies,
        verify=cbot.certificatePath
    )


def handle_event(gbot: Client, event: Event) -> None:
    botId = cast(str, gbot.profile.userId)  # type: ignore
    comId = cast(int, event.comId)
    chatId = cast(str, event.message.chatId)
    userId = cast(str, event.message.author.userId)
    if isinstance(event.message.replyMessage, dict):
        reply = Message(event.message.replyMessage).Message
    else:
        reply = None
    # ignore other messages
    if (userId != botId) or (not reply):
        return None
    cbot = SubClient(comId=comId, profile=gbot.profile, deviceId=DEVICE)  # type: ignore
    text_params = build_msg_params(gbot, cbot, event)
    print(COPY_CONFIRMATION_MSG.format(**text_params))
    if not confirm_copy():
        return None
    messageId = cast(str, reply.messageId)
    bubbleUrl = extract_bubble_url(gbot, cbot, comId, chatId, messageId)
    if not bubbleUrl:
        print(NO_CHAT_BUBBLE_MSG.format(**text_params))
        return None
    with urlopen(bubbleUrl) as response:
        bubbleSrc = cast(bytes, response.read())
    bubbleId = generate_custom_bubble(cbot, comId, bubbleSrc)
    if not bubbleId:
        return None
    apply_bubble(cbot, comId, bubbleSrc, bubbleId)
    print(COPY_SUCCESS_MSG.format(**text_params))


@bot.event("on_text_message")
def on_text_message(event: Event) -> None:
    Thread(target=handle_event, args=(bot, event,)).start()


def main():
    bot.login(EMAIL, PASSWORD)
    # safe websocket connection
    while True:
        bot.run_amino_socket()
        print('[i] Reply a message for start')
        sleep(60*5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass


os._exit(0)
