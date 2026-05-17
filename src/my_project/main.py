from telegram import Update, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters, InlineQueryHandler, CallbackQueryHandler
from telegram.error import BadRequest, Forbidden
from uuid import uuid4
import logging
import json
import html # Для экранирования HTML

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# Настроим логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 🔧 ЗАМЕНИТЕ НА ВАШ ID ГРУППЫ (обязательно с -100 для супергрупп)
# Пример: GROUP_CHAT_ID = -1001234567890
GROUP_CHAT_ID = id

async def post_init(application):
    application.bot_data['running'] = True
    application.bot_data['msg_map'] = {} 
    application.bot_data['user_format'] = {}  

def create_reply_menu():
    keyboard = ReplyKeyboardMarkup([
        [KeyboardButton("🔧 Teto"), KeyboardButton("ℹ️ Подробнее")],
        [KeyboardButton("🏠 В начало")]
    ], resize_keyboard=True)
    return keyboard

def create_teto_inline_menu():
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("JSON", callback_data="format_json")],
        [InlineKeyboardButton("YAML", callback_data="format_yaml")],
        [InlineKeyboardButton("Both (Текст)", callback_data="format_both")],
        [InlineKeyboardButton("⬅️ Закрыть", callback_data="close_teto")]
    ])
    return keyboard

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.bot_data['running'] = True
    text = "Teto pear 🟢 Бот активен.\nНапишите сообщение, оно уйдет админам."
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=create_reply_menu())

async def show_details(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "ℹ️ Информация:\nПишите сюда — админы увидят в группе.\n"
    await update.message.reply_text(text, reply_markup=create_reply_menu())

async def show_teto_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔧 Выберите формат ответов:", reply_markup=create_teto_inline_menu())

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "format_json":
        context.bot_data['user_format'][query.from_user.id] = 'json'
        await query.edit_message_text(text="✅ Формат: JSON", reply_markup=create_teto_inline_menu())
    elif query.data == "format_yaml":
        if not YAML_AVAILABLE:
             await query.edit_message_text(text="❌ PyYAML не установлен.", reply_markup=create_teto_inline_menu())
             return
        context.bot_data['user_format'][query.from_user.id] = 'yaml'
        await query.edit_message_text(text="✅ Формат: YAML", reply_markup=create_teto_inline_menu())
    elif query.data == "format_both":
        context.bot_data['user_format'][query.from_user.id] = 'both'
        await query.edit_message_text(text="✅ Формат: Текст", reply_markup=create_teto_inline_menu())
    elif query.data == "close_teto":
        await query.edit_message_text(text="Меню закрыто.", reply_markup=None)

async def forward_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('running', True): return
    
    user = update.effective_user
    user_id = user.id
    
    try:
        sender_name = html.escape(user.full_name) if user.full_name else "Unknown"
        
        # Сохраняем сообщение в группу
        sent_msg = None
        
        if update.message.text:
            content_text = f"👤 <b>{sender_name}</b>:\n{html.escape(update.message.text)}"
            sent_msg = await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=content_text,
                parse_mode='HTML'
            )
        elif update.message.photo:
            photo_file_id = update.message.photo[-1].file_id
            caption = f"👤 <b>{sender_name}</b>"
            if update.message.caption:
                caption += f"\n{html.escape(update.message.caption)}"
            sent_msg = await context.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=photo_file_id,
                caption=caption,
                parse_mode='HTML'
            )
        else:
            # Игнорируем другие типы медиа для простоты
            return

        if sent_msg:
            # Сохраняем связь: ID сообщения в группе -> ID пользователя
            context.bot_data['msg_map'][sent_msg.message_id] = user_id
            logger.info(f"Msg {sent_msg.message_id} in group linked to user {user_id}")
        
    except Exception as e:
        logger.error(f"Ошибка пересылки: {e}")
        await context.bot.send_message(chat_id=user_id, text="❌ Ошибка отправки.", reply_markup=create_reply_menu())

async def handle_group_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает ответы администраторов"""
    
    # 1. Проверяем, что это ответ на сообщение
    reply_to = update.message.reply_to_message
    if not reply_to:
        return

    # 2. Проверяем, что ответили именно на сообщение бота
    if reply_to.from_user.id != context.bot.id:
        return

    msg_id_in_group = reply_to.message_id
    logger.debug(f"Admin replied to message ID: {msg_id_in_group}")

    # 3. Ищем пользователя в карте сообщений
    user_id = context.bot_data.get('msg_map', {}).get(msg_id_in_group)

    if not user_id:
        logger.warning(f"User ID not found for message {msg_id_in_group}. Map keys: {list(context.bot_data['msg_map'].keys())[:10]}")
        await update.message.reply_text("⚠️ Ошибка: Не могу найти автора этого сообщения. Возможно, бот был перезапущен после отправки исходного сообщения.")
        return

    try:
        user_format = context.bot_data.get('user_format', {}).get(user_id, 'both')
        
        final_text = ""
        final_caption = ""
        parse_mode = 'HTML' # По умолчанию HTML, так как он проще для смешанного контента

        # Получаем текст ответа админа
        admin_response_text = update.message.text
        admin_response_photo = update.message.photo

        if admin_response_text:
            # Формируем ответ в зависимости от формата
            if user_format == 'json':
                data = {"reply": admin_response_text}
                # Используем HTML <pre> или <code> для безопасности, чтобы не ломать MarkdownV2 экранированием
                json_str = json.dumps(data, ensure_ascii=False, indent=2)
                final_text = f"🔙 Ответ (JSON):\n<pre>{html.escape(json_str)}</pre>"
            elif user_format == 'yaml' and YAML_AVAILABLE:
                data = {"reply": admin_response_text}
                yaml_str = yaml.dump(data, allow_unicode=True)
                final_text = f"🔙 Ответ (YAML):\n<pre>{html.escape(yaml_str)}</pre>"
            else:
                # Обычный текст
                final_text = f"🔙 Ответ:\n{html.escape(admin_response_text)}"
                
        elif admin_response_photo:
            photo_file_id = admin_response_photo[-1].file_id
            caption_raw = update.message.caption or ""
            
            if user_format == 'json':
                data = {"reply": caption_raw, "type": "photo"}
                json_str = json.dumps(data, ensure_ascii=False, indent=2)
                final_caption = f"🔙 Ответ (JSON):\n<pre>{html.escape(json_str)}</pre>"
            elif user_format == 'yaml' and YAML_AVAILABLE:
                data = {"reply": caption_raw, "type": "photo"}
                yaml_str = yaml.dump(data, allow_unicode=True)
                final_caption = f"🔙 Ответ (YAML):\n<pre>{html.escape(yaml_str)}</pre>"
            else:
                final_caption = f"🔙 Ответ:\n{html.escape(caption_raw)}" if caption_raw else "🔙 Ответ (фото)"
            
            # Отправка фото
            await context.bot.send_photo(
                chat_id=user_id,
                photo=photo_file_id,
                caption=final_caption,
                reply_markup=create_reply_menu(),
                parse_mode=parse_mode
            )
            await update.message.reply_text("✅ Фото с ответом доставлено.")
            return # Выходим, так как фото уже отправлено

        else:
            # Если админ ответил пустым сообщением без фото
            await update.message.reply_text("⚠️ Пустой ответ не отправлен.")
            return

        # Отправка текстового сообщения
        if final_text:
            await context.bot.send_message(
                chat_id=user_id,
                text=final_text,
                reply_markup=create_reply_menu(),
                parse_mode=parse_mode
            )
            await update.message.reply_text("✅ Текстовый ответ доставлен.")

    except Forbidden:
        logger.warning(f"Пользователь {user_id} заблокировал бота!")
        await update.message.reply_text("❌ Ошибка: Пользователь заблокировал бота.")
        
    except Exception as e:
        logger.error(f"Ошибка отправки пользователю {user_id}: {e}")
        await update.message.reply_text(f"❌ Ошибка отправки: {str(e)}")

# --- Остальные хендлеры ---

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
    await context.bot.send_message(chat_id=update.effective_chat.id, text="🔴 Стоп.", reply_markup=create_reply_menu())

async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.bot_data.get('running', True): return
    await context.bot.send_message(chat_id=update.effective_chat.id, text="?", reply_markup=create_reply_menu())

if __name__ == '__main__':
    # ЗАМЕНИТЕ 'token' на ваш токен
    application = ApplicationBuilder().token('token').post_init(post_init).build()

    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('caps', caps))
    application.add_handler(CommandHandler('stop', stop))
    application.add_handler(InlineQueryHandler(inline_caps))
    application.add_handler(CallbackQueryHandler(handle_callback_query))
    
    # Хендлеры для кнопок меню
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^🔧 Teto$'), show_teto_menu))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^ℹ️ Подробнее$'), show_details))
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.Regex(r'^🏠 В начало$'), start))
    
    # Пересылка от юзера в группу
    application.add_handler(MessageHandler(filters.ChatType.PRIVATE & (filters.TEXT | filters.PHOTO) & (~filters.COMMAND), forward_to_group))
    
    # Ответ от админа из группы
    # Важно: filters.Chat(GROUP_CHAT_ID) требует точного ID
    application.add_handler(MessageHandler(filters.Chat(GROUP_CHAT_ID) & (filters.TEXT | filters.PHOTO) & (~filters.COMMAND), handle_group_reply))
    
    application.add_handler(MessageHandler(filters.COMMAND, unknown))

    print("🤖 Бот запущен.")
    application.run_polling(drop_pending_updates=True)
