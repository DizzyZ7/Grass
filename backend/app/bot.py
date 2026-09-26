"""aiogram v3 router; initialized only when BOT_TOKEN exists."""
from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

router = Router(name='touch_grass')


def play_keyboard(url: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='🌱 НАЧАТЬ СОЦИАЛИЗАЦИЮ', web_app=WebAppInfo(url=url))
    ]])


@router.message(CommandStart())
async def start(message: Message, public_url: str):
    if not public_url:
        await message.answer('🌱 TOUCH GRASS.exe еще настраивается. Загляни позже.')
        return
    await message.answer(
        '🌱 TOUCH GRASS.exe\n\n'
        'Мне сказали трогать траву. Я написал для этого бота.\n\n'
        'Симулятор социализации для тех, у кого открыт VS Code.\n'
        'Гладь живую траву, собирай комбо и получай достижения.',
        reply_markup=play_keyboard(public_url),
    )


@router.message(Command('help'))
async def help_command(message: Message, public_url: str):
    await start(message, public_url)
