import asyncio
import time
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, LOG_CHANNEL, CHANNELS
from database.ia_filterdb import save_file
from utils import temp, get_readable_time

lock = asyncio.Lock()

@Client.on_callback_query(filters.regex(r'^index'))
async def index_files(bot, query):
    _, ident, chat, lst_msg_id, skip = query.data.split("#")
    if ident == 'yes':
        msg = query.message
        await msg.edit("<b>Indexing started...</b>")
        try:
            chat = int(chat)
        except:
            pass
        await index_files_to_db(int(lst_msg_id), chat, msg, bot, int(skip))
    elif ident == 'cancel':
        temp.CANCEL = True
        await query.message.edit("Trying to cancel Indexing...")

@Client.on_message(filters.command('index') & filters.private & filters.user(ADMINS))
async def send_for_index(bot, message):
    if lock.locked():
        return await message.reply('Wait until previous process completes.')
    i = await message.reply("Forward last message or send last message link.")
    msg = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await i.delete()

    if msg.text and msg.text.startswith("https://t.me"):
        try:
            msg_link = msg.text.split("/")
            last_msg_id = int(msg_link[-1])
            chat_id = msg_link[-2]
            if chat_id.isnumeric():
                chat_id = int("-100" + chat_id)
        except:
            return await message.reply("Invalid message link!")
    elif msg.forward_from_chat and msg.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = msg.forward_from_message_id
        chat_id = msg.forward_from_chat.id
    else:
        return await message.reply("Please forward a valid message or link.")

    try:
        chat = await bot.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f'Error: {e}')
    if chat.type != enums.ChatType.CHANNEL:
        return await message.reply("Only channels are supported.")
    
    s = await message.reply("Send skip message number.")
    msg = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await s.delete()
    try:
        skip = int(msg.text)
    except:
        return await message.reply("Invalid number.")
    
    buttons = [[
        InlineKeyboardButton("YES", callback_data=f'index#yes#{chat_id}#{last_msg_id}#{skip}')
    ],[
        InlineKeyboardButton("CANCEL", callback_data='close_data')
    ]]
    await message.reply(
        f'Do you want to index "{chat.title}"?\nLast Message ID: <code>{last_msg_id}</code>',
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def index_files_to_db(lst_msg_id, chat, msg, bot, skip):
    start_time = time.time()
    total_files = 0
    duplicate = 0
    errors = 0
    deleted = 0
    no_media = 0
    unsupported = 0
    current = skip

    async with lock:
        try:
            async for message in bot.iter_messages(chat_id=chat, reverse=True, offset_id=0):
                if message.id > lst_msg_id:
                    continue
                current += 1
                if current <= skip:
                    continue

                if current % 100 == 0:
                    btn = [[InlineKeyboardButton("CANCEL", callback_data=f'index#cancel#{chat}#{lst_msg_id}#{skip}')]]
                    await msg.edit_text(
                        f"Total messages received: <code>{current}</code>\n"
                        f"Saved: <code>{total_files}</code> | Duplicate: <code>{duplicate}</code>\n"
                        f"Deleted: <code>{deleted}</code> | Non-media: <code>{no_media + unsupported}</code>",
                        reply_markup=InlineKeyboardMarkup(btn)
                    )
                    await asyncio.sleep(2)

                if message.empty:
                    deleted += 1
                    continue
                elif not message.media:
                    no_media += 1
                    continue
                elif message.media not in [enums.MessageMediaType.DOCUMENT, enums.MessageMediaType.VIDEO]:
                    unsupported += 1
                    continue

                media = getattr(message, message.media.value, None)
                if not media:
                    unsupported += 1
                    continue
                elif media.mime_type not in ['video/mp4', 'video/x-matroska']:
                    unsupported += 1
                    continue

                caption = message.caption or ""
                first_line = caption.strip().split('\n')[0] if caption else "No Caption"

                media.caption = first_line
                status = await save_file(media)

                if status == "suc":
                    total_files += 1
                elif status == "dup":
                    duplicate += 1
                else:
                    errors += 1

                if temp.CANCEL:
                    temp.CANCEL = False
                    break

        except FloodWait as e:
            await asyncio.sleep(e.value)
        except Exception as e:
            await msg.edit(f"Indexing stopped due to error: {e}")
            return

        time_taken = get_readable_time(time.time() - start_time)
        await msg.edit(
            f"<b>Indexing Finished</b>\n\n"
            f"✅ Saved: <code>{total_files}</code>\n"
            f"♻️ Duplicate: <code>{duplicate}</code>\n"
            f"❌ Deleted: <code>{deleted}</code>\n"
            f"⛔ Non-media: <code>{no_media + unsupported}</code>\n"
            f"⚠️ Errors: <code>{errors}</code>\n"
            f"⏱ Time Taken: {time_taken}"
        )
