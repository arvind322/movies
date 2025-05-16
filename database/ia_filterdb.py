import logging
import re
import base64
from pyrogram.file_id import FileId
from pymongo.errors import DuplicateKeyError
from umongo import Instance, Document, fields
from motor.motor_asyncio import AsyncIOMotorClient
from marshmallow.exceptions import ValidationError
from info import DATABASE_URI, DATABASE_NAME, COLLECTION_NAME, MAX_BTN

client = AsyncIOMotorClient(DATABASE_URI)
mydb = client[DATABASE_NAME]
instance = Instance.from_db(mydb)

@instance.register
class Media(Document):
    file_id = fields.StrField(attribute='_id')
    file_ref = fields.StrField(allow_none=True)
    file_name = fields.StrField(required=True)
    file_size = fields.IntField(required=True)
    mime_type = fields.StrField(allow_none=True)
    caption = fields.StrField(allow_none=True)
    file_type = fields.StrField(allow_none=True)

    class Meta:
        indexes = ('$file_name', )
        collection_name = COLLECTION_NAME

async def get_files_db_size():
    return (await mydb.command("dbstats"))['dataSize']

async def save_file(media):
    file_id = getattr(media, "file_id", None)
    file_ref = None

    # Caption text
    caption = media.caption.html if getattr(media, "caption", None) else None
    plain_caption = media.caption.text if getattr(media, "caption", None) else None

    # File name
    if hasattr(media, "file_name") and media.file_name:
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
    elif plain_caption:
        file_name = plain_caption.strip().split("\n")[0][:100]
    else:
        file_name = "No Name"

    # Fallback for post-only file_id
    if not file_id:
        try:
            chat_id = media.chat.username if media.chat.username else f"c/{str(media.chat.id)[4:]}"
            file_id = f"https://t.me/{chat_id}/{media.id}"
        except:
            file_id = file_name

    file_size = getattr(media, "file_size", 0)
    mime_type = getattr(media, "mime_type", None)
    file_type = mime_type.split('/')[0] if mime_type else "text"

    try:
        file = Media(
            file_id=file_id,
            file_ref=file_ref,
            file_name=file_name,
            file_size=file_size,
            mime_type=mime_type,
            caption=caption,
            file_type=file_type
        )
    except ValidationError:
        print('Error occurred while saving file/post in database')
        return 'err'
    else:
        try:
            await file.commit()
        except DuplicateKeyError:
            print(f'{file_name} is already saved in database')
            return 'dup'
        else:
            print(f'{file_name} is saved to database')
            return 'suc'

async def get_search_results(query, max_results=MAX_BTN, offset=0, lang=None):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        regex = query
    filter = {'file_name': regex}
    cursor = Media.find(filter)
    cursor.sort('$natural', -1)
    if lang:
        lang_files = [file async for file in cursor if lang in file.file_name.lower()]
        files = lang_files[offset:][:max_results]
        total_results = len(lang_files)
        next_offset = offset + max_results
        if next_offset >= total_results:
            next_offset = ''
        return files, next_offset, total_results
    cursor.skip(offset).limit(max_results)
    files = await cursor.to_list(length=max_results)
    total_results = await Media.count_documents(filter)
    next_offset = offset + max_results
    if next_offset >= total_results:
        next_offset = ''
    return files, next_offset, total_results

async def get_bad_files(query, file_type=None, offset=0, filter=False):
    query = query.strip()
    if not query:
        raw_pattern = '.'
    elif ' ' not in query:
        raw_pattern = r'(\b|[\.\+\-_])' + query + r'(\b|[\.\+\-_])'
    else:
        raw_pattern = query.replace(' ', r'.*[\s\.\+\-_]')
    try:
        regex = re.compile(raw_pattern, flags=re.IGNORECASE)
    except:
        return []
    filter = {'file_name': regex}
    if file_type:
        filter['file_type'] = file_type
    total_results = await Media.count_documents(filter)
    cursor = Media.find(filter)
    cursor.sort('$natural', -1)
    files = await cursor.to_list(length=total_results)
    return files, total_results

async def get_file_details(query):
    filter = {'file_id': query}
    cursor = Media.find(filter)
    filedetails = await cursor.to_list(length=1)
    return filedetails

def encode_file_id(s: bytes) -> str:
    r = b""
    n = 0
    for i in s + bytes([22]) + bytes([4]):
        if i == 0:
            n += 1
        else:
            if n:
                r += b"\x00" + bytes([n])
                n = 0
            r += bytes([i])
    return base64.urlsafe_b64encode(r).decode().rstrip("=")

def encode_file_ref(file_ref: bytes) -> str:
    return base64.urlsafe_b64encode(file_ref).decode().rstrip("=")

def unpack_new_file_id(file_id: str) -> FileId:
    return unpack(file_id)
