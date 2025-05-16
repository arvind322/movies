from pyrogram import filters
from pyrogram.types import Message
from Jisshu.bot import JisshuBot
from info import ADMINS
from database.ia_filterdb import Media

@JisshuBot.on_message(filters.command("deleteall") & filters.user(ADMINS))
async def delete_all_entries(_, message: Message):
    result = await Media.collection.delete_many({})
    await message.reply_text(f"Deleted {result.deleted_count} records from the database.")
