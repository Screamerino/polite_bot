import asyncio
import os
import logging
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.utils.formatting import Text, Spoiler, Bold
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime
import requests
import hashlib
import re



# --- Конфигурация ---
load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GIGACHAT_TOKEN = os.getenv("GIGACHAT_TOKEN")  # Получаем через API Сбера
CHAT_ID = os.getenv("CHAT_ID")
logging.basicConfig(level=logging.INFO)
dp = Dispatcher()

RE_PATTERN = re.compile(r"([_\[#\]()~>+\-=|{}.!\\])")



def escape_md(text):
    return re.sub(pattern=RE_PATTERN, repl=r"\\\1", string=text)


def generate_hash(text: str):
    h = hashlib.new("md5")
    h.update(bytes(text, encoding="utf-8"))
    hash_raw = h.hexdigest()
    return f"{hash_raw[:8]}-{hash_raw[8:12]}-{hash_raw[12:16]}-{hash_raw[16:20]}-{hash_raw[20:]}"


# --- Аутентификация в GigaChat ---
async def get_gigachat_token():
    url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    now_dt = datetime.now().isoformat()
    _hash = generate_hash(now_dt)
    headers = {
        "Authorization": f"Bearer {GIGACHAT_TOKEN}",
        "RqUID": _hash,  # Уникальный ID запроса
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {"scope": "GIGACHAT_API_PERS"}
    
    # # Для обхода SSL-сертификата (только для тестов!)
    # ssl_context = ssl._create_unverified_context()
    
    response = requests.post(url, headers=headers, data=data, verify=False)
    return response.json().get("access_token")


def read_prompt(prompt_name: str):
    with open(f"prompts/{prompt_name}.md", encoding="utf-8") as f:
        return f.read()

prompts = {
    "task": read_prompt("task"),
    "quiz": read_prompt("quiz"),
    "dialogue": read_prompt("dialogue")
}
print(prompts)

# --- Генерация контента через GigaChat ---
async def generate_gigachat_content(prompt_type):
    token = await get_gigachat_token()
    

    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "GigaChat-2",
        "messages": [{"role": "user", "content": prompts[prompt_type]}],
        "temperature":  1,
        "max_tokens": 1000
    }
    
    response = requests.post(
        "https://gigachat.devices.sberbank.ru/api/v1/chat/completions",
        headers=headers,
        json=data,
        verify=False  # Отключаем проверку SSL для тестов
    )
    
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]
    else:
        logging.error(f"GigaChat error: {response.text}")
        return "Не удалось сгенерировать задание. Попробуйте позже."

# --- Отправка постов ---
async def send_scheduled_post(bot):
    post_types = ["task", "quiz", "dialogue"]
    post_type = post_types[datetime.now().minute % 3]
    
    content = await generate_gigachat_content(post_type)
    
    if post_type == "task":
        answer_idx = content.find("3) Объяснение")
        task_part = content[:answer_idx]
        answer_part = content[answer_idx:]
        answer_message = Text(
            task_part,
            Spoiler(answer_part)
        )
        await bot.send_message(CHAT_ID, **answer_message.as_kwargs())
    else:
        msg = Text(
            "🎲 ", Bold("Новая активность!"), f"\n\n{content}"
        )
        await bot.send_message(CHAT_ID, **msg.as_kwargs())

# --- Обработчики ---
@dp.callback_query(F.data == "show_answer")
async def show_answer(callback: types.CallbackQuery):
    msg = Text("💡 Разбор ответа будет здесь!")
    await callback.message.answer(**msg.as_kwargs())

@dp.message(Command("start"))
async def start(message: types.Message):
    msg = Text("👋 Я бот для изучения вежливости с GigaChat!")
    await message.reply(**msg.as_kwargs())


# --- Запуск ---
async def main():
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN_V2))
    scheduler = AsyncIOScheduler()
    scheduler.add_job(send_scheduled_post, "interval", minutes=1, args=(bot,))
    scheduler.start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
