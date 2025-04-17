from flask import Flask, request
import os
from twilio.rest import Client
from dotenv import load_dotenv
import whisper
import openai
from datetime import datetime
import requests
import asyncio

# Загружаем переменные окружения
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")
APPLICATIONS_DIR = os.getenv("APPLICATIONS_DIR", "/tmp/applications")  # Папка для заявок

# Настройка клиента Twilio
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Убедимся, что папка существует
os.makedirs(APPLICATIONS_DIR, exist_ok=True)

# Whisper — транскрипция аудио
async def transcribe_audio(file_path):
    model = whisper.load_model("small")  # Используем более легкую модель
    result = model.transcribe(file_path, language="ru")
    return result["text"]

# GPT — создать заявку по строгому шаблону
async def create_application(user_text, username):
    openai.api_key = OPENAI_API_KEY
    try:
        prompt = (
            f"На основе следующего описания проблемы или идеи:\n\n"
            f"{user_text}\n\n"
            f"Создай заявку по следующей структуре:\n\n"
            f"1. От кого заявка: {username}\n"
            f"2. Наименование заявки: (коротко сформулируй суть)\n"
            f"3. Цель или описание заявки: (развернуто опиши суть)\n\n"
            f"Ответ должен строго соответствовать этой форме, без лишнего текста!"
        )
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[{"role": "system", "content": "Ты помощник по оформлению заявок."},
                      {"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3
        )
        application_text = response['choices'][0]['message']['content'].strip()
        return application_text
    except Exception as e:
        print(f"Ошибка общения с GPT: {e}")
        return None

# Сохранение заявки в файл
def save_application(application_text, username):
    if not application_text.strip():  # Если текст пустой или состоит только из пробелов
        print("Ошибка: текст заявки пустой!")
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(APPLICATIONS_DIR, f"{username}_{timestamp}.txt")
    
    with open(filename, "w", encoding="utf-8") as f:
        f.write(application_text)
    
    print(f"Заявка сохранена: {filename}")
    return filename

# Функция для отправки сообщения через WhatsApp с использованием Twilio
def send_whatsapp_message(to_number, message):
    try:
        message_sent = client.messages.create(
            body=message,
            from_=f'whatsapp:{WHATSAPP_NUMBER}',  # Ваш номер WhatsApp в Twilio
            to=f'whatsapp:{to_number}'  # Номер получателя
        )
        print(f"Сообщение отправлено: {message_sent.sid}")
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

# Инициализация Flask приложения
app = Flask(__name__)

@app.route("/webhook", methods=["POST"])
async def webhook():
    """Обработка входящего сообщения от Twilio"""
    from_number = request.form['From']  # Номер отправителя
    message_body = request.form['Body']  # Текст сообщения

    print(f"Входящее сообщение от {from_number}: {message_body}")
    
    # Обработка сообщения и отправка ответа
    user_text = message_body
    username = from_number

    # Проверяем, пришел ли голосовой файл (медиа)
    media_url = request.form.get('MediaUrl0')
    if media_url:
        # Скачиваем аудио файл и транскрибируем его
        audio_file = download_audio(media_url)
        user_text = await transcribe_audio(audio_file)
        print(f"Транскрибированное аудио: {user_text}")

    # Создаем заявку
    application_text = await create_application(user_text, username)

    if application_text:
        # Сохраняем заявку в файл
        saved_filename = save_application(application_text, username)
        if saved_filename:
            # Отправляем ответ в WhatsApp
            send_whatsapp_message(from_number, "✅ Заявка обработана и сохранена. Спасибо!")
        else:
            # Если не удалось сохранить заявку
            send_whatsapp_message(from_number, "❌ Заявка не была сохранена, так как текст пуст.")
    else:
        # Если не удалось создать заявку
        send_whatsapp_message(from_number, "❌ Не удалось обработать заявку. Попробуйте позже.")
    
    return "OK", 200

def download_audio(media_url):
    """Скачивание аудио файла по URL из Twilio"""
    response = requests.get(media_url)
    file_path = os.path.join(APPLICATIONS_DIR, "audio_message.mp3")
    with open(file_path, "wb") as f:
        f.write(response.content)
    return file_path

if __name__ == "__main__":
    # Запуск сервера Flask для получения Webhook от Twilio
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
