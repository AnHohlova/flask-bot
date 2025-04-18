from flask import Flask, request
import os
from twilio.rest import Client
from dotenv import load_dotenv
import whisper
import openai
from datetime import datetime
import requests
from openai import OpenAI

# Загружаем переменные окружения
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
WHATSAPP_NUMBER = os.getenv("WHATSAPP_NUMBER")
APPLICATIONS_DIR = os.getenv("APPLICATIONS_DIR", "BOT\\applications")

ADMIN_NUMBER = "+77476123370"  # Номер администратора

# Настройка клиента Twilio
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Убедимся, что папка существует
os.makedirs(APPLICATIONS_DIR, exist_ok=True)

# Whisper — транскрипция аудио
def transcribe_audio(file_path):
    model = whisper.load_model("small")
    result = model.transcribe(file_path, language="ru")
    return result["text"]

# GPT — создать заявку
def create_application(user_text, username):
    client = OpenAI(api_key=OPENAI_API_KEY)
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
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты помощник по оформлению заявок."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Ошибка общения с GPT: {e}")
        return None

# Сохранение заявки в файл
def save_application(application_text, username):
    if not application_text.strip():
        print("Ошибка: текст заявки пустой!")
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(APPLICATIONS_DIR, f"{username}_{timestamp}.txt")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(application_text)
    print(f"Заявка сохранена: {filename}")
    return filename

# Отправка сообщения в WhatsApp
def send_whatsapp_message(to_number, message):
    try:
        print(f"Отправка сообщения на номер: {to_number}")
        if to_number.startswith("whatsapp:"):
            to_number = to_number.replace("whatsapp:", "")
        to_number = f"whatsapp:{to_number}"
        message_sent = client.messages.create(
            body=message,
            from_=f'whatsapp:{WHATSAPP_NUMBER}',
            to=to_number
        )
        print(f"Сообщение отправлено: {message_sent.sid}")
    except Exception as e:
        print(f"Ошибка при отправке сообщения: {e}")

# Flask-приложение
app = Flask(__name__)

@app.route("/", methods=["GET"])
def index():
    return "✅ Сервер работает!"

@app.route("/webhook", methods=["POST"])
def webhook():
    print("Получен запрос:", request.form)
    from_number = request.form.get('From')
    message_body = request.form.get('Body')

    print(f"Входящее сообщение от {from_number}: {message_body}")

    user_text = message_body
    username = from_number

    media_url = request.form.get('MediaUrl0')
    if media_url:
        audio_file = download_audio(media_url)
        if audio_file:
            user_text = transcribe_audio(audio_file)
            print(f"Транскрибированное аудио: {user_text}")
        else:
            print("❌ Ошибка при загрузке аудио файла.")

    application_text = create_application(user_text, username)

    if application_text:
        saved_filename = save_application(application_text, username)
        if saved_filename:
            with open(saved_filename, "r", encoding="utf-8") as f:
                file_text = f.read()
            send_whatsapp_message(ADMIN_NUMBER, f"✅ Новая заявка:\n\n{file_text}")
            send_whatsapp_message(from_number, "✅ Ваша заявка успешно принята и отправлена!")  # <-- ОТПРАВКА ПОЛЬЗОВАТЕЛЮ
        else:
            send_whatsapp_message(ADMIN_NUMBER, "❌ Ошибка: заявка не была сохранена.")
            send_whatsapp_message(from_number, "❌ Произошла ошибка при сохранении заявки.")
    else:
        send_whatsapp_message(ADMIN_NUMBER, "❌ Ошибка: не удалось создать заявку.")
        send_whatsapp_message(from_number, "❌ Не удалось создать заявку. Попробуйте позже.")

    return "OK", 200

def download_audio(media_url):
    try:
        response = requests.get(media_url)
        file_path = os.path.join(APPLICATIONS_DIR, "audio_message.mp3")
        with open(file_path, "wb") as f:
            f.write(response.content)
        return file_path
    except Exception as e:
        print(f"Ошибка при скачивании аудио: {e}")
        return None

if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=int(os.getenv("PORT", 5000)))
