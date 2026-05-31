import json
from datetime import datetime, UTC

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ContentType, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import ADMIN_ID, APP_URL
from database import async_session, User, Section, Lesson, Question, UserProgress
from bot.keyboards import back_kb

router = Router()


# ─── FSM States ───────────────────────────────────────────────────

class AddSection(StatesGroup):
    title = State()
    description = State()
    icon = State()


class AddLesson(StatesGroup):
    section_id = State()
    title = State()
    description = State()
    content_text = State()
    video_type = State()
    video_url = State()
    video_file = State()


class AddQuiz(StatesGroup):
    lesson_id = State()
    questions = State()
    question_text = State()
    options = State()
    correct_answer = State()
    explanation = State()


# ─── Helpers ──────────────────────────────────────────────────────

def is_admin(user_id: str) -> bool:
    return user_id == ADMIN_ID


async def get_or_create_user(telegram_id: str, username: str = "", first_name: str = ""):
    async with async_session() as session:
        user = await session.get(User, telegram_id)
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                is_admin=is_admin(telegram_id),
            )
            session.add(user)
            await session.commit()
        return user


async def get_section(section_id: int):
    async with async_session() as session:
        return await session.get(Section, section_id)


async def get_lesson(lesson_id: int):
    async with async_session() as session:
        return await session.get(Lesson, lesson_id)


async def get_questions(lesson_id: int):
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(Question).where(Question.lesson_id == lesson_id).order_by(Question.id)
        )
        return result.scalars().all()


# ─── Start ────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message):
    uid = str(message.from_user.id)
    await get_or_create_user(uid, message.from_user.username or "", message.from_user.first_name or "")
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Открыть Winglish", web_app=WebAppInfo(url=f"{APP_URL}/webapp/app"))
    await message.answer(
        "👋 <b>Winglish</b> — учи английский с удовольствием!\n\n"
        "📚 Разделы и уроки\n"
        "🎬 Видеоуроки (YouTube)\n"
        "📝 Тесты для проверки знаний\n\n"
        "Нажми кнопку ниже, чтобы начать:",
        reply_markup=builder.as_markup(),
    )


# ─── WebApp Data (Quiz Results) ──────────────────────────────────

@router.message(F.web_app_data)
async def handle_webapp_data(message: Message):
    uid = str(message.from_user.id)
    try:
        data = json.loads(message.web_app_data.data)
    except (json.JSONDecodeError, TypeError):
        await message.answer("Ошибка обработки данных теста.")
        return

    lesson_id = data.get("lesson_id")
    score = data.get("score", 0)
    total = data.get("total", 0)
    answers = data.get("answers", [])
    passed = score >= total / 2

    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(UserProgress).where(
                UserProgress.user_id == uid,
                UserProgress.lesson_id == lesson_id,
            )
        )
        progress = result.scalar_one_or_none()
        if progress:
            if score > progress.score:
                progress.score = score
                progress.answers = answers
            if passed and not progress.completed:
                progress.completed = True
                progress.completed_at = datetime.now(UTC)
        else:
            progress = UserProgress(
                user_id=uid,
                lesson_id=lesson_id,
                completed=passed,
                score=score,
                total_questions=total,
                answers=answers,
                completed_at=datetime.now(UTC) if passed else None,
            )
            session.add(progress)
        await session.commit()

    lesson = await get_lesson(lesson_id)
    lesson_title = lesson.title if lesson else "урок"

    status = "✅ <b>Пройдено!</b>" if passed else "❌ <b>Попробуй ещё раз</b>"
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Открыть Winglish", web_app=WebAppInfo(url=f"{APP_URL}/webapp/app"))
    await message.answer(
        f"{status}\n\n"
        f"📖 <b>{lesson_title}</b>\n"
        f"🎯 Результат: {score} / {total}\n\n"
        f"{'Отличная работа! 👏' if passed else 'Ничего страшного, повтори материал и попробуй снова! 💪'}",
        reply_markup=builder.as_markup(),
    )


# ─── Cancel FSM ──────────────────────────────────────────────────

@router.message(Command("cancel"))
async def cancel_fsm(message: Message, state: FSMContext):
    await state.clear()
    builder = InlineKeyboardBuilder()
    builder.button(text="🚀 Открыть Winglish", web_app=WebAppInfo(url=f"{APP_URL}/webapp/app"))
    await message.answer("🚫 Действие отменено.", reply_markup=builder.as_markup())
