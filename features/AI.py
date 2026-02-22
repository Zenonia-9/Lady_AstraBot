from functions.memory import ConversationMemory
from openai import OpenAI
from config import OPENROUTER_API_KEY, TOPIC_MODELS, SUMMARIZE_MODELS, CLASSIFY_MODELS, BOT_USERNAME, BOT_NAME

from apscheduler.schedulers.background import BackgroundScheduler

# Set up OpenRouter client
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)
 
memory = ConversationMemory()

# Schedule cleanup of old messages every day
scheduler = BackgroundScheduler()
scheduler.add_job(lambda: memory.trim_old_messages(days=15), 'interval', hours=24)
scheduler.start()

def remove_non_ascii(text):
    return text.encode('ascii', 'ignore').decode('ascii')

async def classify(text: str) -> str:
    system_prompt = "You are a fast, efficient AI classifier. Your task is to **categorize user input into exactly one of these topics**: casual_chat, technical, coding, languages, science. \n\n- Read the user's message carefully.\n- Return **only the topic name**, nothing else.\n- Do not add explanations, comments, or emojis.\n- Always pick the topic that best fits the overall content of the message.\n- If unsure, pick the closest match from the list above."

    messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text.strip()}
    ]

    for model in CLASSIFY_MODELS:
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                extra_headers={
                    "HTTP-Referer": f"https://t.me/{BOT_USERNAME}",
                    "X-Title": BOT_NAME
                },
            )

            return completion.choices[0].message.content.strip()

        except Exception as e:
            _logger.warning(f"Classify Model '{model}' failed with error: {e}")
            continue
    return text.strip()

async def talk_back(user_id: str, user_message: str, type: str = 'private') -> str:
    # Save user message
    memory.save_message(user_id, 'user', user_message)

    if type == 'private':
        # Load recent history
        input_msg = memory.get_history(user_id, limit=20)
    else:
        input_msg = memory.get_history(user_id, limit=20)

    category = await classify(user_message)
    models = TOPIC_MODELS[category]["primary"] + TOPIC_MODELS[category]["fallback"]
    system_prompt = TOPIC_MODELS[category]["system_prompt"]

    input_msg.insert(0, system_prompt)

    for model in models:
        print(f'Topic: {category}\nUsed Model: {model}')
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=input_msg,
                extra_headers={
                    "HTTP-Referer": f"https://t.me/{BOT_USERNAME}",
                    "X-Title": BOT_NAME
                },
                extra_body={"reasoning": {"enabled": True}}
            )

            reply = completion.choices[0].message.content.strip()

            memory.save_message(user_id, "assistant", reply)
            if not reply:
                raise ValueError("Model returned empty response")  # triggers except block
            
            print("Bot replied.")
            return reply

        except Exception as e:
            _logger.warning(f"Main Model '{model}' failed with error: {e}")
            continue

    return "I am unable to respond at this moment. Please try again shortly."

async def summarize_text(text: str) -> str:
    models = SUMMARIZE_MODELS["summarize"]["primary"] + SUMMARIZE_MODELS["summarize"]["fallback"]
    system_prompt = SUMMARIZE_MODELS["summarize"]["system_prompt"]

    messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text.strip()}
    ]
    
    for model in models:
        print(f'Topic: Summarizing\nUsed Model: {model}')
        try:
            completion = client.chat.completions.create(
                model=model,
                messages=messages,
                extra_headers={
                    "HTTP-Referer": f"https://t.me/{BOT_USERNAME}",
                    "X-Title": BOT_NAME
                },
            )

            return completion.choices[0].message.content.strip()

        except Exception as e:
            _logger.warning(f"Summarize Model '{model}' failed with error: {e}")
            continue

    return "I am unable to complete the summary right now. Please try again in a moment."