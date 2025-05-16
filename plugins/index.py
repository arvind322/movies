import asyncio
import time
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, CHANNELS
from database.ia_filterdb import save_file
from utils import temp, get_readable_time

lock = asyncio.Lock()


class FakeMedia:
    def __init__(self, file_id, file_name, caption):
        self.file_id = file_id
        self.file_ref = None
        self.file_name = file_name
        self.file_size = 0
        self.mime_type = None
        self.caption = caption
        self.file_type = "text"


@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    _, ident, chat_id, last_msg_id, skip = query.data.split("#")
    if ident == 'yes':
        msg = query.message
        await msg.edit("<b>Indexing started...</b>")
        try:
            chat_id = int(chat_id)
            last_msg_id = int(last_msg_id)
            skip = int(skip)
            await index_files_to_db(last_msg_id, chat_id, msg, bot, skip)
        except Exception as e:
            await msg.edit(f"Failed to start indexing: {e}")
    elif ident == 'cancel':
        temp.CANCEL = True
        await query.message.edit("Trying to cancel Indexing...")


@Client.on_message(filters.command('index') & filters.private & filters.user(ADMINS))
async def send_for_index(bot, message):
    if lock.locked():
        return await message.reply('Wait until previous process completes.')

    i = await message.reply("Forward the last message or send its link.")
    try:
        msg = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    finally:
        await i.delete()

    if msg.text and msg.text.startswith("https://t.me"):
        try:
            parts = msg.text.strip("/").split("/")
            last_msg_id = int(parts[-1])
            chat_id = parts[-2]
            if chat_id.isnumeric():
                chat_id = int(f"-100{chat_id}")
        except Exception:
            return await message.reply("Invalid message link!")
    elif msg.forward_from_chat and msg.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = msg.forward_from_message_id
        chat_id = msg.forward_from_chat.id
    else:
        return await message.reply("Invalid message. Send a channel message or link.")

    try:
        chat = await bot.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f"Error: {e}")

    if chat.type != enums.ChatType.CHANNEL:
        return await message.reply("Only channel messages can be indexed.")

    s = await message.reply("How many messages to skip?")
    try:
        skip_msg = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    finally:
        await s.delete()
    try:
        skip = int(skip_msg.text)
    except:
        return await message.reply("Invalid number.")

    buttons = [
        [InlineKeyboardButton('YES', callback_data=f'index#yes#{chat.id}#{last_msg_id}#{skip}')],
        [InlineKeyboardButton('CLOSE', callback_data='close_data')]
    ]
    reply_markup = InlineKeyboardMarkup(buttons)
    await message.reply(f'Do you want to index <b>{chat.title}</b>?\nTotal Messages: <code>{last_msg_id}</code>', reply_markup=reply_markup)


@Client.on_message(filters.command('channel'))
async def channel_info(bot, message):
    if message.from_user.id not in ADMINS:
        return await message.reply('Only bot owner can use this command.')

    if not CHANNELS:
        return await message.reply("CHANNELS not set.")

    text = '**Indexed Channels:**\n\n'
    for cid in CHANNELS:
        try:
            chat = await bot.get_chat(cid)
            text += f'{chat.title}\n'
        except:
            text += f'Unknown Channel ({cid})\n'
    text += f'\n**Total:** {len(CHANNELS)}'
    await message.reply(text)


async def index_files_to_db(last_msg_id, chat_id, msg, bot, skip):
    start_time = time.time()
    total_files = duplicate = errors = deleted = no_media = unsupported = 0
    current = skip

    async with lock:
        try:
            # Updated iter_messages usage: removed reverse, added offset_id and large limit
            async for message in bot.iter_messages(chat_id, offset_id=last_msg_id, limit=10000):
                if current > 0:
                    current -= 1
                    continue

                if temp.CANCEL:
                    temp.CANCEL = False
                    await msg.edit(
                        f"Cancelled!\nSaved: <code>{total_files}</code>\nDuplicates: <code>{duplicate}</code>\nDeleted: <code>{deleted}</code>\nNo Media: <code>{no_media + unsupported}</code>\nErrors: <code>{errors}</code>"
                    )
                    return

                if current % 100 == 0:
                    btn = [[InlineKeyboardButton('CANCEL', callback_data=f'index#cancel#{chat_id}#{last_msg_id}#{skip}')]]
                    await msg.edit_text(
                        f"Checked: <code>{current}</code>\nSaved: <code>{total_files}</code>\nDuplicates: <code>{duplicate}</code>\nDeleted: <code>{deleted}</code>\nNo Media: <code>{no_media + unsupported}</code>\nErrors: <code>{errors}</code>",
                        reply_markup=InlineKeyboardMarkup(btn)
                    )
                    await asyncio.sleep(1)

                current += 1

                if message.empty:
                    deleted += 1
                    continue

                media = message.photo or message.document or message.video

                if media:
                    media.caption = message.caption or ""
                    status = await save_file(media)
                elif message.text:
                    try:
                        username = message.chat.username or (await bot.get_chat(chat_id)).username
                        link = f"https://t.me/{username}/{message.message_id}" if username else str(message.message_id)
                    except:
                        link = str(message.message_id)

                    caption = message.text.strip()
                    name = caption.split('\n')[0][:50] if caption else "No Name"
                    status = await save_file(FakeMedia(link, name, caption))
                else:
                    no_media += 1
                    continue

                if status == 'suc':
                    total_files += 1
                elif status == 'dup':
                    duplicate += 1
                elif status == 'err':
                    errors += 1
                else:
                    unsupported += 1

        except FloodWait as e:
            await asyncio.sleep(e.x)
        except Exception as e:
            await msg.reply(f'Error during indexing: {e}')
        else:
            time_taken = get_readable_time(time.time() - start_time)
            await msg.edit(
                f'✅ Indexing Complete!\n⏱ Time: {time_taken}\nSaved: <code>{total_files}</code>\nDuplicates: <code>{duplicate}</code>\nDeleted: <code>{deleted}</code>\nNo Media: <code>{no_media + unsupported}</code>\nErrors: <code>{errors}</code>'
                              )
