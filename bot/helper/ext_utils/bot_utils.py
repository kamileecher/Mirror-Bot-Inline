import re
import threading
import time
import math
import psutil
import shutil

from bot.helper.telegram_helper.bot_commands import BotCommands
from bot import dispatcher, download_dict, download_dict_lock, STATUS_LIMIT, botStartTime
from telegram import InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from bot.helper.telegram_helper import button_build, message_utils

MAGNET_REGEX = r"magnet:\?xt=urn:btih:[a-zA-Z0-9]*"

URL_REGEX = r"(?:(?:https?|ftp):\/\/)?[\w/\-?=%.]+\.[\w/\-?=%.]+"

COUNT = 0
PAGE_NO = 1


class MirrorStatus:
    STATUS_UPLOADING = "𝘜𝘱𝘭𝘰𝘢𝘥𝘪𝘯𝘨 ..."
    STATUS_DOWNLOADING = "𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥𝘪𝘯𝘨 ..."
    STATUS_CLONING = "𝘊𝘭𝘰𝘯𝘪𝘯𝘨 ..."
    STATUS_WAITING = "𝘘𝘶𝘦𝘶𝘦𝘥 ..."
    STATUS_FAILED = "𝘍𝘢𝘪𝘭𝘦𝘥. 𝘊𝘭𝘦𝘢𝘯𝘪𝘯𝘨 𝘋𝘰𝘸𝘯𝘭𝘰𝘢𝘥 ..."
    STATUS_PAUSE = " 𝘗𝘢𝘶𝘴𝘦𝘥 ..."
    STATUS_ARCHIVING = "𝘈𝘳𝘤𝘩𝘪𝘷𝘪𝘯𝘨 ..."
    STATUS_EXTRACTING = "𝘌𝘹𝘵𝘳𝘢𝘤𝘵𝘪𝘯𝘨 ..."
    STATUS_SPLITTING = "𝘚𝘱𝘭𝘪𝘵𝘵𝘪𝘯𝘨 ..."
    STATUS_CHECKING = "𝘊𝘩𝘦𝘤𝘬𝘪𝘯𝘨𝘜𝘱 ..."
    STATUS_SEEDING = "𝘚𝘦𝘦𝘥𝘪𝘯𝘨 ..."

SIZE_UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']


class setInterval:
    def __init__(self, interval, action):
        self.interval = interval
        self.action = action
        self.stopEvent = threading.Event()
        thread = threading.Thread(target=self.__setInterval)
        thread.start()

    def __setInterval(self):
        nextTime = time.time() + self.interval
        while not self.stopEvent.wait(nextTime - time.time()):
            nextTime += self.interval
            self.action()

    def cancel(self):
        self.stopEvent.set()

def get_readable_file_size(size_in_bytes) -> str:
    if size_in_bytes is None:
        return '0B'
    index = 0
    while size_in_bytes >= 1024:
        size_in_bytes /= 1024
        index += 1
    try:
        return f'{round(size_in_bytes, 2)}{SIZE_UNITS[index]}'
    except IndexError:
        return 'File too large'

def getDownloadByGid(gid):
    with download_dict_lock:
        for dl in download_dict.values():
            status = dl.status()
            if (
                status
                not in [
                    MirrorStatus.STATUS_ARCHIVING,
                    MirrorStatus.STATUS_EXTRACTING,
                    MirrorStatus.STATUS_SPLITTING,
                ]
                and dl.gid() == gid
            ):
                return dl
    return None

def getAllDownload():
    with download_dict_lock:
        for dlDetails in download_dict.values():
            status = dlDetails.status()
            if (
                status
                not in [
                    MirrorStatus.STATUS_ARCHIVING,
                    MirrorStatus.STATUS_EXTRACTING,
                    MirrorStatus.STATUS_SPLITTING,
                    MirrorStatus.STATUS_CLONING,
                    MirrorStatus.STATUS_UPLOADING,
                    MirrorStatus.STATUS_CHECKING,
                    MirrorStatus.STATUS_SEEDING,
                ]
                and dlDetails
            ):
                return dlDetails
    return None

def get_progress_bar_string(status):
    completed = status.processed_bytes() / 8
    total = status.size_raw() / 8
    p = 0 if total == 0 else round(completed * 100 / total)
    p = min(max(p, 0), 100)
    cFull = p // 8
    p_str = '▰' * cFull
    p_str += '▱' * (12 - cFull)
    p_str = f"{p_str}"
    return p_str

def get_readable_message():
    with download_dict_lock:
        msg = ""
        START = 0
        dlspeed_bytes = 0
        uldl_bytes = 0
        if STATUS_LIMIT is not None:
            dick_no = len(download_dict)
            global pages
            pages = math.ceil(dick_no/STATUS_LIMIT)
            if pages != 0 and PAGE_NO > pages:
                globals()['COUNT'] -= STATUS_LIMIT
                globals()['PAGE_NO'] -= 1
            START = COUNT
        for index, download in enumerate(list(download_dict.values())[START:], start=1):
            msg += f"<b>𝐅𝐢𝐥𝐞𝐧𝐚𝐦𝐞 :</b>\n<code>{download.name()}</code>"
            #msg += f"\n<b>Status:</b> <i>{download.status()}</i>"
            if download.status() not in [
                MirrorStatus.STATUS_ARCHIVING,
                MirrorStatus.STATUS_EXTRACTING,
                MirrorStatus.STATUS_SPLITTING,
                MirrorStatus.STATUS_SEEDING,
            ]:
                msg += f"\n\n<b>𝔗𝔬 𝔖𝔱𝔬𝔭 :</b> <code>/cancel {download.gid()}</code>"
                msg += f"\n\n<b>╭ 𝙿𝚛𝚘𝚐𝚛𝚎𝚜𝚜\n│\n│</b>  {get_progress_bar_string(download)}"
                if download.status() == MirrorStatus.STATUS_CLONING:
                    msg += f"<b>\n│\n├ 𝑫𝒐𝒏𝒆 :</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                elif download.status() == MirrorStatus.STATUS_UPLOADING:
                    msg += f"<b>\n│\n├ 𝑫𝒐𝒏𝒆 :</b> {get_readable_file_size(download.processed_bytes())} of {download.size()}"
                else:
                    msg += f"<b>\n│\n├ 𝑫𝒐𝒏𝒆 : </b>{get_readable_file_size(download.processed_bytes())} of {download.size()}"
                msg += f"<b>\n│\n├ 𝑺𝒑𝒆𝒆𝒅 : </b>{download.speed()} <b>\n│\n├ 𝑬𝑻𝑨 : </b>{download.eta()}"
                try:
                    msg += f"<b>\n│\n├ 𝑺𝒆𝒆𝒅𝒆𝒓𝒔 :</b> <code>{download.aria_download().num_seeders}</code>" \
                           f" | <b>𝑷𝒆𝒆𝒓𝒔 : </b><code>{download.aria_download().connections}</code>"
                except:
                    pass
                try:
                    msg += f"<b>\n│\n├ 𝑺𝒆𝒆𝒅𝒆𝒓𝒔 : </b><code>{download.torrent_info().num_seeds}</code>" \
                           f" | <b>𝑳𝒆𝒆𝒄𝒉𝒆𝒓𝒔 :</b> <code>{download.torrent_info().num_leechs}</code>"
                except:
                    pass
                msg += f"<b>\n│\n╰ 𝑺𝒕𝒂𝒕𝒖𝒔 : </b>{download.status()}"
            elif download.status() == MirrorStatus.STATUS_SEEDING:
                msg += f"<b>\n\n𝔗𝔬 𝔖𝔱𝔬𝔭 :</b> <code>/cancel {download.gid()}</code>"
                msg += f"<b>\n\n╭ 𝑺𝒊𝒛𝒆 : </b>{download.size()}"
                msg += f"<b>\n│\n├ 𝑺𝒑𝒆𝒆𝒅 : </b>{get_readable_file_size(download.torrent_info().upspeed)}/s"
                msg += f"<b>\n│\n├ 𝑼𝒑𝒍𝒐𝒂𝒅𝒆𝒅 : </b>{get_readable_file_size(download.torrent_info().uploaded)}"
                msg += f"<b>\n│\n├ 𝑹𝒂𝒕𝒊𝒐 : </b>{round(download.torrent_info().ratio, 3)}"
                msg += f"<b>\n│\n╰ 𝑻𝒊𝒎𝒆 : </b>{get_readable_time(download.torrent_info().seeding_time)}"
                #msg += f"\n<code>/{BotCommands.CancelMirror} {download.gid()}</code>"
            else:
                msg += f"<b>\n\n「 </b>𝑺𝒕𝒂𝒕𝒖𝒔 : {download.status()} <b>」</b>"
            msg += "\n\n"
            if STATUS_LIMIT is not None and index == STATUS_LIMIT:
                break
        total, used, free = shutil.disk_usage('.')
        free = get_readable_file_size(free)
        currentTime = get_readable_time(time.time() - botStartTime)
        for download in list(download_dict.values()):
            speedy = download.speed()
            if download.status() == MirrorStatus.STATUS_DOWNLOADING:
                if 'K' in speedy:
                    dlspeed_bytes += float(speedy.split('K')[0]) * 1024
                elif 'M' in speedy:
                    dlspeed_bytes += float(speedy.split('M')[0]) * 1048576
            if download.status() == MirrorStatus.STATUS_UPLOADING:
                if 'KB/s' in speedy:
                    uldl_bytes += float(speedy.split('K')[0]) * 1024
                elif 'MB/s' in speedy:
                    uldl_bytes += float(speedy.split('M')[0]) * 1048576
        dlspeed = get_readable_file_size(dlspeed_bytes)
        ulspeed = get_readable_file_size(uldl_bytes)
        bmsg = f"\n<b>DLS :</b> {dlspeed}/s | <b>ULS :</b> {ulspeed}/s"
                
        if STATUS_LIMIT is not None and dick_no > STATUS_LIMIT:
            msg += f"<b>Page:</b> {PAGE_NO}/{pages} | <b>Tasks:</b> {dick_no}\n"
            buttons = button_build.ButtonMaker()
            buttons.sbutton("Previous", "pre")
            buttons.sbutton("Next", "nex")
            button = InlineKeyboardMarkup(buttons.build_menu(2))
            return msg + bmsg, button
        return msg + bmsg, ""

def turn(update, context):
    query = update.callback_query
    query.answer()
    global COUNT, PAGE_NO
    if query.data == "nex":
        if PAGE_NO == pages:
            COUNT = 0
            PAGE_NO = 1
        else:
            COUNT += STATUS_LIMIT
            PAGE_NO += 1
    elif query.data == "pre":
        if PAGE_NO == 1:
            COUNT = STATUS_LIMIT * (pages - 1)
            PAGE_NO = pages
        else:
            COUNT -= STATUS_LIMIT
            PAGE_NO -= 1
    message_utils.update_all_messages()

def get_readable_time(seconds: int) -> str:
    result = ''
    (days, remainder) = divmod(seconds, 86400)
    days = int(days)
    if days != 0:
        result += f'{days}d'
    (hours, remainder) = divmod(remainder, 3600)
    hours = int(hours)
    if hours != 0:
        result += f'{hours}h'
    (minutes, seconds) = divmod(remainder, 60)
    minutes = int(minutes)
    if minutes != 0:
        result += f'{minutes}m'
    seconds = int(seconds)
    result += f'{seconds}s'
    return result

def is_url(url: str):
    url = re.findall(URL_REGEX, url)
    return bool(url)

def is_gdrive_link(url: str):
    return "drive.google.com" in url

def is_gdtot_link(url: str):
    url = re.match(r'https?://.*\.gdtot\.\S+', url)
    return bool(url)

def is_mega_link(url: str):
    return "mega.nz" in url or "mega.co.nz" in url

def get_mega_link_type(url: str):
    if "folder" in url:
        return "folder"
    elif "file" in url:
        return "file"
    elif "/#F!" in url:
        return "folder"
    return "file"

def is_magnet(url: str):
    magnet = re.findall(MAGNET_REGEX, url)
    return bool(magnet)

def new_thread(fn):
    """To use as decorator to make a function call threaded.
    Needs import
    from threading import Thread"""

    def wrapper(*args, **kwargs):
        thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
        thread.start()
        return thread

    return wrapper


next_handler = CallbackQueryHandler(turn, pattern="nex", run_async=True)
previous_handler = CallbackQueryHandler(turn, pattern="pre", run_async=True)
dispatcher.add_handler(next_handler)
dispatcher.add_handler(previous_handler)
