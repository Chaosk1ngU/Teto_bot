from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, InlineQueryHandler
from uuid import uuid4
import logging

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# 🔧 ЗАМЕНИТЕ НА ВАШ ID ГРУППЫ (обязательно с -100)
GROUP_CHAT_ID = id

async def post_init(application):
    application.bot_data['running'] = True
    application.bot_data['msg_map'] = {}  # message_id в группе -> user_id

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data['running'] = True
    await context.bot.send_message(chat_id=update.effective_chat.id, text="Teto pear 🟢 Бот активен")

async def forward_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Пересылает текст и фото от пользователей в группу"""
    if not context.bot_data.get('running', True): return
    user = update.effective_user
    user_id = user.id

    try:
        # 📝 Обработка текста
        if update.message.text:
            sent_msg = await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"👤 От {user.mention_html()}: {update.message.text}",
                parse_mode='HTML'
            )
        # 🖼️ Обработка фото
        elif update.message.photo:
            # Берём фото максимального разрешения [-1]
            photo_file_id = update.message.photo[-1].file_id
            caption = f"👤 От {user.mention_html()}"
            if update.message.caption:
                caption += f"\n{update.message.caption}"

            sent_msg = await context.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=photo_file_id,
                caption=caption,
                parse_mode='HTML'
            )
        else:
            return  # Игнорируем голосовые, стикеры и т.д. (можно добавить позже)

        # Сохраняем связь: ID сообщения в группе -> ID пользователя
        context.bot_data['msg_map'][sent_msg.message_id] = user_id
        
        # ✅ Отправляем подтверждение пользователю
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Ваше сообщение было успешно отправлено!"
        )
    except Exception as e:
        logging.error(f"Ошибка пересылки в группу: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="❌ Произошла ошибка при отправке сообщения. Попробуйте позже."
        )

async def caps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('running', True): return
    await context.bot.send_message(chat_id=update.effective_chat.id, text=' '.join(context.args).upper())

async def inline_caps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('running', True):
        await context.bot.answer_inline_query(update.inline_query.id, [])
        return
    query = update.inline_query.query
    if not query: return
    results = [InlineQueryResultArticle(id=str(uuid4()), title='Caps', input_message_content=InputTextMessageContent(query.upper()))]
    await context.bot.answer_inline_query(update.inline_query.id, results)

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data['running'] = False
    await context.bot.send_message(chat_id=update.effective_chat.id, text="🔴 Бот остановлен. /start для запуска")

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('running', True): return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="WTF, NIGGA")

async def handle_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ответы администраторов (текст + фото) и отправляет в ЛС"""
    reply_to = update.message.reply_to_message
    if not reply_to or reply_to.from_user.id != context.bot.id:
        return

    msg_id = reply_to.message_id
    user_id = context.bot_data.get('msg_map', {}).get(msg_id)

    if not user_id:
        await update.message.reply_text("⚠️ Не удалось найти пользователя. Возможно, бот был перезапущен.")
        return

    try:
        # 📝 Текстовый ответ
        if update.message.text:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🔙 Ответ от администратора:\n{update.message.text}"
            )
        # 🖼️ Ответ картинкой
        elif update.message.photo:
            photo_file_id = update.message.photo[-1].file_id
            caption_text = update.message.caption if update.message.caption else ""
            caption = f"🔙 Ответ от администратора:\n{caption_text}" if caption_text else "🔙 Ответ от администратора (фото)"

            await context.bot.send_photo(
                chat_id=user_id,
                photo=photo_file_id,
                caption=caption
            )

        await update.message.reply_text("✅ Ответ отправлен в ЛС пользователю.")
    except Exception as e:
        logging.error(f"Ошибка отправки в ЛС: {e}")
        await update.message.reply_text("❌ Ошибка: пользователь заблокировал бота или удалил чат.")

if __name__ == '__main__':
    application = ApplicationBuilder().token('token').post_init(post_init).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('caps', caps))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(InlineQueryHandler(inline_caps))

    # 🔒 ЛИЧНЫЕ СООБЩЕНИЯ (текст + фото) -> пересылаются в группу
    application.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO) & (~filters.COMMAND),
        forward_to_group
    ))

    # 🔒 ОТВЕТЫ В ГРУППЕ (текст + фото) -> идут в ЛС пользователю
    application.add_handler(MessageHandler(
        filters.Chat(GROUP_CHAT_ID) & (filters.TEXT | filters.PHOTO) & (~filters.COMMAND),
        handle_group_reply
    ))

    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    print("🤖 Бот запущен. Поддержка текста и изображений активна.")
    application.run_polling()
