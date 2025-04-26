import asyncio
import random
import json
from dotenv import load_dotenv
import os

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

games = {}

with open("questions.json", "r") as f:
    question_bank = json.load(f)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    keyboard = ReplyKeyboardMarkup(
        [["🎯 10", "🎯 20", "🎯 50"]],
        one_time_keyboard=True,
        resize_keyboard=True
    )

    await update.message.reply_text(
        "🎉 Welcome to Trivia Challenge!\n\nPlease select the number of questions you want to play:",
        reply_markup=keyboard
    )

    games[chat_id] = {
        "awaiting_question_count": True,
        "num_questions": 0,
        "questions_asked": 0,
        "scoreboard": {},
        "current_question": None,
        "current_answer": None,
        "stage": 0,
        "task": None,
        "question_active": False,
        "remaining_questions": question_bank.copy()
    }

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in games:
        if games[chat_id]["task"]:
            games[chat_id]["task"].cancel()
        await end_game(update, context, manual_stop=True)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if chat_id not in games:
        return

    game = games[chat_id]

    if game["awaiting_question_count"]:
        text_clean = text.replace("🎯", "").strip()
        if text_clean in ["10", "20", "50"]:
            game["num_questions"] = int(text_clean)
            game["awaiting_question_count"] = False
            await update.message.reply_text(
                f"✅ Got it! We'll play {text_clean} questions. Get ready!",
                reply_markup=ReplyKeyboardRemove()
            )
            await ask_question(update, context)
        else:
            await update.message.reply_text("Please select using the menu!")
        return

    if not game["question_active"]:
        return

    if game["current_answer"] and game["current_answer"].lower().strip() in text.lower().strip():
        user_name = update.effective_user.first_name
        points = [5, 3, 2, 1][game["stage"]]
        correct_answer = game["current_answer"]

        game["scoreboard"][user_name] = game["scoreboard"].get(user_name, 0) + points
        game["question_active"] = False
        game["current_answer"] = None

        if game["task"]:
            game["task"].cancel()

        await context.bot.send_message(
            chat_id,
            f"✅ That's right, *{correct_answer}*!\n\n"
            f"🎖️ *{user_name}* +*{points}*\n\n",
            parse_mode="Markdown"
        )

        await asyncio.sleep(3)
        await ask_question(update, context)

async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games[chat_id]

    if game["questions_asked"] >= game["num_questions"]:
        await end_game(update, context)
        return

    if not game["remaining_questions"]:
        await context.bot.send_message(chat_id, "😶 No more questions available!")
        await end_game(update, context)
        return

    await context.bot.send_message(chat_id, f"👉 Moving on to Question {game['questions_asked'] + 1}/{game['num_questions']}...")

    question = random.choice(game["remaining_questions"])
    game["remaining_questions"].remove(question)

    game["current_question"] = question["question"]
    game["current_answer"] = question["answer"]
    game["questions_asked"] += 1
    game["stage"] = 0
    game["question_active"] = True

    await asyncio.sleep(2)
    await context.bot.send_message(chat_id, f"❓ *Question* {game['questions_asked']}/{game["num_questions"]}\n\n {question['question']}", parse_mode="Markdown")
    game["task"] = asyncio.create_task(run_stages(update, context))

async def run_stages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    game = games[chat_id]
    answer = game["current_answer"]
    question_text = game["current_question"]

    stages = [
        ("no_hint", 5),
        ("blanks", 3),
        ("20%", 2),
        ("40%", 1)
    ]

    for idx, (mode, points) in enumerate(stages):
        await asyncio.sleep(12)

        if not game.get("question_active", False):
            return

        game["stage"] = idx

        if mode == "no_hint":
            continue
        else:
            hint = generate_hint(answer, mode)
            await context.bot.send_message(
                chat_id,
                f"❓ *Question* {game['questions_asked']}/{game["num_questions"]}\n\n{question_text}\n\n"
                f"💬 Hint: {hint}"
            )

    await asyncio.sleep(12)

    if not game.get("question_active", False):
        return

    await context.bot.send_message(chat_id, f"⏳ *Time's up!*\n\nThe correct answer was: *{answer}*", parse_mode="Markdown")
    game["question_active"] = False
    game["current_answer"] = None
    await asyncio.sleep(3)
    await ask_question(update, context)

async def end_game(update: Update, context: ContextTypes.DEFAULT_TYPE, manual_stop=False):
    chat_id = update.effective_chat.id
    game = games.get(chat_id)

    if not game:
        return

    scoreboard = {name: score for name, score in game["scoreboard"].items() if score > 0}

    if not scoreboard:
        await context.bot.send_message(chat_id, "😶 *Oops!*\n\nNo one scored any points this game. Better luck next time!")
    else:
        leaderboard = sorted(scoreboard.items(), key=lambda x: x[1], reverse=True)
        medals = ["🥇", "🥈", "🥉"]

        message = "🏁 Game Over!\n\n🏆 *Leaderboard* 🏆\n"
        for idx, (name, score) in enumerate(leaderboard, start=1):
            medal = medals[idx-1] if idx <= 3 else f"{idx}."
            message += f"{medal} *{name}*   {score} points\n"

        await context.bot.send_message(chat_id, message)

    del games[chat_id]

def generate_hint(answer, mode):
    if mode == "blanks":
        return create_blanks(answer, reveal_ratio=0.0)
    elif mode == "20%":
        return create_blanks(answer, reveal_ratio=0.2)
    elif mode == "40%":
        return create_blanks(answer, reveal_ratio=0.4)
    else:
        return create_blanks(answer, reveal_ratio=0.0)

def create_blanks(answer, reveal_ratio=0.0):
    import random

    displayed_words = []
    words = answer.split(' ')

    for word in words:
        letters = list(word)
        indices = [i for i, c in enumerate(letters) if c.isalnum()]

        reveal_count = int(len(indices) * reveal_ratio)
        reveal_indices = set(random.sample(indices, reveal_count)) if reveal_count else set()

        word_hint = []
        for idx, c in enumerate(letters):
            if not c.isalnum():
                word_hint.append(c)
            elif idx in reveal_indices:
                word_hint.append(c)
            else:
                word_hint.append("_")

        displayed_words.append(' '.join(word_hint))

    return '   '.join(displayed_words)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    app.run_polling()
