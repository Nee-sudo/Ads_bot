"""Membership-gated Telegram media delivery bot (python-telegram-bot v20+).

Setup:
    1. Install: python -m pip install -r requirements.txt
    2. Set BOT_TOKEN, REQUIRED_PUBLIC_GROUP, REQUIRED_GROUP_URL, and
         PUBLIC_CHANNEL_URL in a .env file or as environment variables.
    3. Add the bot as an administrator in the required public group/channel so
       Telegram reliably permits getChatMember membership checks.
     4. Set PUBLIC_CHANNEL_URL to a valid invite link for the private movies group.
         The bot does not need to be a member of that destination group.
     Do not share your bot token.
"""

from __future__ import annotations

import logging
import os
from typing import Final

from dotenv import load_dotenv
from telegram import ChatMember, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import RetryAfter, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

load_dotenv()


# Configuration: environment variables are convenient for deployment; replace
# the defaults here for a quick local setup.
TOKEN: Final[str] = os.getenv("BOT_TOKEN", "PASTE_YOUR_BOT_TOKEN_HERE")
REQUIRED_PUBLIC_GROUP: Final[str] = os.getenv(
    "REQUIRED_PUBLIC_GROUP", "@your_public_group"
)
REQUIRED_GROUP_URL: Final[str] = os.getenv(
    "REQUIRED_GROUP_URL", "https://t.me/your_public_group"
)
PUBLIC_CHANNEL_URL: Final[str] = os.getenv(
    "PRIVATE_CHANNEL_URL", "https://t.me/your_private_group"
)

JOIN_REQUIRED_TEXT: Final[str] = (
    "Please join the required group/channel first, then tap "
    "\"Check Membership\"."
)
MEMBERSHIP_UNAVAILABLE_TEXT: Final[str] = (
    "I couldn't verify your membership right now. Please try again shortly."
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def membership_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Join the group", url=REQUIRED_GROUP_URL)],
            [InlineKeyboardButton("🔄 Check Membership", callback_data="check")],
        ]
    )


def movies_group_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Join Movies Group", url=PUBLIC_CHANNEL_URL)]]
    )


async def is_group_member(context: ContextTypes.DEFAULT_TYPE, user_id: int) -> bool:
    member = await context.bot.get_chat_member(
        chat_id=REQUIRED_PUBLIC_GROUP,
        user_id=user_id,
    )
    if member.status in {
        ChatMember.OWNER,
        ChatMember.ADMINISTRATOR,
        ChatMember.MEMBER,
    }:
        return True
    return member.status == ChatMember.RESTRICTED and bool(member.is_member)


async def show_gate(
    update: Update,
    *,
    edit: bool = False,
) -> None:
    message = update.effective_message
    if message is None:
        return
    keyboard = membership_keyboard()
    if edit and update.callback_query is not None:
        await update.callback_query.edit_message_text(
            JOIN_REQUIRED_TEXT,
            reply_markup=keyboard,
        )
    else:
        await message.reply_text(JOIN_REQUIRED_TEXT, reply_markup=keyboard)


async def show_movies_group_link(update: Update, *, edit: bool = False) -> None:
    message = update.effective_message
    if message is None:
        return
    text = "Join this group to access movies."
    if edit and update.callback_query is not None:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=movies_group_keyboard(),
        )
    else:
        await message.reply_text(text, reply_markup=movies_group_keyboard())


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if user is None:
        return

    try:
        member = await is_group_member(context, user.id)
    except RetryAfter as error:
        logger.warning("Rate limited while checking membership: %s", error)
        await update.effective_message.reply_text(MEMBERSHIP_UNAVAILABLE_TEXT)
        return
    except TelegramError:
        logger.exception("Could not check membership for user %s", user.id)
        await update.effective_message.reply_text(MEMBERSHIP_UNAVAILABLE_TEXT)
        return

    if not member:
        await show_gate(update)
    else:
        await show_movies_group_link(update)


async def membership_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None or query.data is None:
        return

    await query.answer()

    try:
        member = await is_group_member(context, user.id)
    except RetryAfter as error:
        logger.warning("Rate limited while checking membership: %s", error)
        await query.edit_message_text(
            MEMBERSHIP_UNAVAILABLE_TEXT,
            reply_markup=membership_keyboard(),
        )
        return
    except TelegramError:
        logger.exception("Could not check membership for user %s", user.id)
        await query.edit_message_text(
            MEMBERSHIP_UNAVAILABLE_TEXT,
            reply_markup=membership_keyboard(),
        )
        return

    if not member:
        await show_gate(update, edit=True)
    else:
        await show_movies_group_link(update, edit=True)


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    error = context.error
    if error is not None:
        logger.error(
            "Unhandled error while processing update %r",
            update,
            exc_info=(type(error), error, error.__traceback__),
        )



def main() -> None:
    if not TOKEN or TOKEN == "PASTE_YOUR_BOT_TOKEN_HERE":
        raise RuntimeError(
            "Set BOT_TOKEN in the environment or replace TOKEN in bot.py."
        )
    if REQUIRED_PUBLIC_GROUP == "@your_public_group":
        raise RuntimeError("Set REQUIRED_PUBLIC_GROUP to your public group/channel.")
    if REQUIRED_GROUP_URL == "https://t.me/your_public_group":
        raise RuntimeError("Set REQUIRED_GROUP_URL to the public join link.")
    if PUBLIC_CHANNEL_URL == "https://t.me/your_private_group":
        raise RuntimeError("Set PUBLIC_CHANNEL_URL to the private movies group invite link.")

    application: Application = ApplicationBuilder().token(TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(
        CallbackQueryHandler(membership_callback, pattern=r"^check$")
    )
    application.add_error_handler(error_handler)
    logger.info("Starting membership-gated media bot")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
