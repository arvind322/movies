import asyncio
from pyrogram import Client, filters, enums
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from info import ADMINS, LOG_CHANNEL, CHANNELS
from database.ia_filterdb import save_file
from utils import temp, get_readable_time
import time

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

@Client.on_message(filters.command('index') & filters.private & filters.incoming & filters.user(ADMINS))
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
            return await message.reply('Invalid message link!')
    elif msg.forward_from_chat and msg.forward_from_chat.type == enums.ChatType.CHANNEL:
        last_msg_id = msg.forward_from_message_id
        chat_id = msg.forward_from_chat.username or msg.forward_from_chat.id
    else:
        return await message.reply('This is not a forwarded message or link.')

    try:
        chat = await bot.get_chat(chat_id)
    except Exception as e:
        return await message.reply(f'Error: {e}')

    if chat.type != enums.ChatType.CHANNEL:
        return await message.reply("Only channel messages can be indexed.")

    s = await message.reply("Send how many messages to skip.")
    msg = await bot.listen(chat_id=message.chat.id, user_id=message.from_user.id)
    await s.delete()
    try:
        skip = int(msg.text)
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
    ids = CHANNELS
    if not ids:
        return await message.reply("CHANNELS not set.")
    text = '**Indexed Channels:**\n\n'
    for id in ids:
        chat = await bot.get_chat(id)
        text += f'{chat.title}\n'
    text += f'\n**Total:** {len(ids)}'
    await message.reply(text)

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
            async for message in bot.iter_messages(chat, lst_msg_id, skip):
                if temp.CANCEL:
                    temp.CANCEL = False
                    await msg.edit(f"Cancelled!\nSaved: <code>{total_files}</code>\nDuplicates: <code>{duplicate}</code>\nDeleted: <code>{deleted}</code>\nNo Media: <code>{no_media + unsupported}</code>\nErrors: <code>{errors}</code>")
                    return

                current += 1
                if current % 100 == 0:
                    btn = [[
                        InlineKeyboardButton('CANCEL', callback_data=f'index#cancel#{chat}#{lst_msg_id}#{skip}')
                    ]]
                    await msg.edit_text(
                        f"Checked: <code>{current}</code>\nSaved: <code>{total_files}</code>\nDuplicates: <code>{duplicate}</code>\nDeleted: <code>{deleted}</code>\nNo Media: <code>{no_media + unsupported}</code>\nErrors: <code>{errors}</code>",
                        reply_markup=InlineKeyboardMarkup(btn)
                    )
                    await asyncio.sleep(2)

                if message.empty:
                    deleted += 1
                    continue

                media = None
                if message.photo:
                    media = message.photo
                elif message.document:
                    media = message.document
                elif message.video:
                    media = message.video

                forward_info = None
                if message.forward_from_chat:
                    forward_info = {
                        "from_chat_id": message.forward_from_chat.id,
                        "from_chat_username": message.forward_from_chat.username,
                        "from_chat_title": message.forward_from_chat.title
                    }

                if media:
                    media.caption = message.caption or ""
                    status = await save_file(media, forward_info)
                elif message.text:
                    status = await save_file(message, forward_info)
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
