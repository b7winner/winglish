import json
from datetime import datetime, UTC

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, ContentType, InputFile, FSInputFile

from config import ADMIN_ID, APP_URL
from database import async_session, User, Section, Lesson, Question, UserProgress
from bot.keyboards import (
    main_menu_kb, sections_kb, lessons_kb, lesson_actions_kb,
    admin_menu_kb, admin_sections_kb, admin_section_actions_kb,
    admin_lessons_kb, admin_lesson_actions_kb, back_kb,
)

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
    video_choice = State()
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
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Question).where(Question.lesson_id == lesson_id).order_by(Question.id)
        )
        return result.scalars().all()


# ─── Start ────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message):
    uid = str(message.from_user.id)
    await get_or_create_user(uid, message.from_user.username or "", message.from_user.first_name or "")
    admin = is_admin(uid)
    await message.answer(
        f"👋 <b>English Learning Bot</b>\n\n"
        f"Добро пожаловать! Здесь ты можешь учить английский язык:\n"
        f"📚 Проходить уроки по разделам\n"
        f"🎬 Смотреть видеоуроки\n"
        f"📝 Проходить тесты для проверки знаний\n\n"
        f"Выбери действие в меню ниже:",
        reply_markup=main_menu_kb(admin),
    )


# ─── Main Menu Navigation ─────────────────────────────────────────

@router.callback_query(F.data == "back_main")
async def back_to_main(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    admin = is_admin(uid)
    await cb.message.edit_text(
        "📚 <b>Главное меню</b>\n\nВыбери действие:",
        reply_markup=main_menu_kb(admin),
    )


@router.callback_query(F.data == "sections")
async def show_sections(cb: CallbackQuery):
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Section).order_by(Section.order, Section.id))
        sections = result.scalars().all()

    if not sections:
        await cb.message.edit_text("📚 Пока нет разделов. Подожди, скоро добавят!", reply_markup=back_kb())
        return

    text = "📚 <b>Разделы:</b>\n\nВыбери раздел для изучения:"
    await cb.message.edit_text(text, reply_markup=sections_kb(sections))


@router.callback_query(F.data.startswith("section_"))
async def show_lessons(cb: CallbackQuery):
    section_id = int(cb.data.split("_")[1])
    section = await get_section(section_id)
    if not section:
        await cb.answer("Раздел не найден", show_alert=True)
        return

    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Lesson).where(Lesson.section_id == section_id).order_by(Lesson.order, Lesson.id)
        )
        lessons = result.scalars().all()

    if not lessons:
        await cb.message.edit_text(
            f"{section.icon} <b>{section.title}</b>\n\nВ этом разделе пока нет уроков.",
            reply_markup=back_kb("sections"),
        )
        return

    text = f"{section.icon} <b>{section.title}</b>\n\nВыбери урок:"
    await cb.message.edit_text(text, reply_markup=lessons_kb(lessons, section_id))


@router.callback_query(F.data == "section_lessons_back")
async def back_to_sections_from_lesson(cb: CallbackQuery):
    await show_sections(cb)


@router.callback_query(F.data.startswith("lesson_"))
async def show_lesson(cb: CallbackQuery):
    lesson_id = int(cb.data.split("_")[1])
    lesson = await get_lesson(lesson_id)
    if not lesson:
        await cb.answer("Урок не найден", show_alert=True)
        return

    questions = await get_questions(lesson_id)
    has_quiz = len(questions) > 0
    has_video_url = bool(lesson.video_url)
    has_video_file = bool(lesson.video_file_id)

    text = f"<b>{lesson.title}</b>\n\n"
    if lesson.description:
        text += f"{lesson.description}\n\n"
    if lesson.content_text:
        text += f"{lesson.content_text}\n\n"
    text += f"📝 Вопросов в тесте: {len(questions)}"

    await cb.message.edit_text(
        text,
        reply_markup=lesson_actions_kb(lesson_id, has_video_url, has_video_file, has_quiz),
    )


@router.callback_query(F.data.startswith("lesson_video_"))
async def send_video_file(cb: CallbackQuery):
    lesson_id = int(cb.data.split("_")[2])
    lesson = await get_lesson(lesson_id)
    if not lesson or not lesson.video_file_id:
        await cb.answer("Видео не найдено", show_alert=True)
        return
    await cb.message.answer_video(lesson.video_file_id, caption=lesson.title)


# ─── My Progress ──────────────────────────────────────────────────

@router.callback_query(F.data == "my_progress")
async def show_progress(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    async with async_session() as session:
        from sqlalchemy import select, func
        total_lessons = (await session.execute(select(func.count(Lesson.id)))).scalar() or 0
        completed = (await session.execute(
            select(func.count(UserProgress.id))
            .where(UserProgress.user_id == uid, UserProgress.completed == True)
        )).scalar() or 0
        total_score = (await session.execute(
            select(func.coalesce(func.sum(UserProgress.score), 0))
            .where(UserProgress.user_id == uid)
        )).scalar() or 0

    text = (
        f"📊 <b>Мой прогресс</b>\n\n"
        f"✅ Пройдено уроков: {completed} / {total_lessons}\n"
        f"⭐ Всего баллов: {total_score}\n\n"
        f"Продолжай учиться! 💪"
    )
    await cb.message.edit_text(text, reply_markup=back_kb())


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
    await message.answer(
        f"{status}\n\n"
        f"📖 <b>{lesson_title}</b>\n"
        f"🎯 Результат: {score} / {total}\n\n"
        f"{'Отличная работа! 👏' if passed else 'Ничего страшного, повтори материал и попробуй снова! 💪'}",
        reply_markup=main_menu_kb(is_admin(uid)),
    )


# ─── Admin ────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin")
async def admin_panel(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        await cb.answer("Доступ запрещён", show_alert=True)
        return
    await cb.message.edit_text(
        "⚙️ <b>Админ-панель</b>\n\nУправление разделами и уроками:",
        reply_markup=admin_menu_kb(),
    )


# ─── Admin: Sections ──────────────────────────────────────────────

@router.callback_query(F.data == "admin_list_sections")
async def admin_list_sections(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(select(Section).order_by(Section.order, Section.id))
        sections = result.scalars().all()
    text = "📋 <b>Разделы:</b>" if sections else "📋 Пока нет разделов."
    await cb.message.edit_text(text, reply_markup=admin_sections_kb(sections))


@router.callback_query(F.data == "admin_add_section")
async def admin_add_section_start(cb: CallbackQuery, state: FSMContext):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    await state.set_state(AddSection.title)
    await cb.message.edit_text(
        "➕ <b>Новый раздел</b>\n\nВведите название раздела:",
        reply_markup=back_kb("admin"),
    )


@router.message(AddSection.title)
async def add_section_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AddSection.description)
    await message.answer(
        "Введите описание раздела (или отправьте /skip):",
        reply_markup=back_kb("admin"),
    )


@router.message(AddSection.description)
async def add_section_desc(message: Message, state: FSMContext):
    text = message.text if message.text != "/skip" else ""
    await state.update_data(description=text)
    await state.set_state(AddSection.icon)
    await message.answer(
        "Введите эмодзи-иконку для раздела (или /skip для 📚):",
        reply_markup=back_kb("admin"),
    )


@router.message(AddSection.icon)
async def add_section_icon(message: Message, state: FSMContext):
    icon = message.text if message.text != "/skip" else "📚"
    data = await state.get_data()
    async with async_session() as session:
        section = Section(title=data["title"], description=data.get("description", ""), icon=icon)
        session.add(section)
        await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Раздел «{data['title']}» создан!",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(F.data.startswith("admin_section_"))
async def admin_section_actions(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    section_id = int(cb.data.split("_")[2])
    section = await get_section(section_id)
    if not section:
        await cb.answer("Раздел не найден", show_alert=True)
        return
    text = f"{section.icon} <b>{section.title}</b>\n\n{section.description or 'Нет описания'}"
    await cb.message.edit_text(text, reply_markup=admin_section_actions_kb(section_id))


@router.callback_query(F.data.startswith("admin_del_section_"))
async def admin_del_section_confirm(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    section_id = int(cb.data.split("_")[3])
    section = await get_section(section_id)
    if not section:
        await cb.answer("Раздел не найден", show_alert=True)
        return
    from bot.keyboards import confirm_kb
    await cb.message.edit_text(
        f"❌ <b>Удалить раздел</b> «{section.title}»?\n\nВсе уроки и тесты будут удалены!",
        reply_markup=confirm_kb(f"del_section_{section_id}"),
    )


@router.callback_query(F.data.startswith("confirm_del_section_"))
async def admin_del_section_execute(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    section_id = int(cb.data.split("_")[3])
    async with async_session() as session:
        section = await session.get(Section, section_id)
        if section:
            await session.delete(section)
            await session.commit()
    await cb.message.edit_text("✅ Раздел удалён.", reply_markup=admin_menu_kb())


# ─── Admin: Lessons ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_section_lessons_"))
async def admin_list_lessons(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    section_id = int(cb.data.split("_")[3])
    section = await get_section(section_id)
    if not section:
        await cb.answer("Раздел не найден", show_alert=True)
        return
    async with async_session() as session:
        from sqlalchemy import select
        result = await session.execute(
            select(Lesson).where(Lesson.section_id == section_id).order_by(Lesson.order, Lesson.id)
        )
        lessons = result.scalars().all()
    text = f"📋 <b>Уроки раздела</b> «{section.title}»:" if lessons else f"В разделе «{section.title}» пока нет уроков."
    await cb.message.edit_text(text, reply_markup=admin_lessons_kb(lessons, section_id))


@router.callback_query(F.data.startswith("admin_add_lesson_"))
async def admin_add_lesson_start(cb: CallbackQuery, state: FSMContext):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    section_id = int(cb.data.split("_")[3])
    await state.update_data(section_id=section_id)
    await state.set_state(AddLesson.title)
    section = await get_section(section_id)
    await cb.message.edit_text(
        f"➕ <b>Новый урок</b> в разделе «{section.title}»\n\nВведите название урока:",
        reply_markup=back_kb("admin"),
    )


@router.message(AddLesson.title)
async def add_lesson_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AddLesson.description)
    await message.answer("Введите описание урока (или /skip):", reply_markup=back_kb("admin"))


@router.message(AddLesson.description)
async def add_lesson_desc(message: Message, state: FSMContext):
    text = message.text if message.text != "/skip" else ""
    await state.update_data(description=text)
    await state.set_state(AddLesson.content_text)
    await message.answer("Введите текст урока (или /skip):", reply_markup=back_kb("admin"))


@router.message(AddLesson.content_text)
async def add_lesson_content(message: Message, state: FSMContext):
    text = message.text if message.text != "/skip" else ""
    await state.update_data(content_text=text)
    await state.set_state(AddLesson.video_choice)
    await message.answer(
        "Хотите добавить видео к уроку?\n\n"
        "1️⃣ Отправить ссылку на YouTube\n"
        "2️⃣ Загрузить видео файлом\n"
        "/skip — без видео",
        reply_markup=back_kb("admin"),
    )


@router.message(AddLesson.video_choice)
async def add_lesson_video_choice(message: Message, state: FSMContext):
    text = message.text.strip()
    if text == "1":
        await state.set_state(AddLesson.video_url)
        await message.answer("Отправьте ссылку на YouTube видео:")
    elif text == "2":
        await state.set_state(AddLesson.video_file)
        await message.answer("Загрузите видео файл:")
    elif text == "/skip":
        await save_lesson(message, state)
    else:
        await message.answer("Пожалуйста, выберите 1, 2 или /skip")


@router.message(AddLesson.video_url)
async def add_lesson_video_url(message: Message, state: FSMContext):
    await state.update_data(video_url=message.text.strip(), video_file_id="")
    await save_lesson(message, state)


@router.message(AddLesson.video_file, F.content_type == ContentType.VIDEO)
async def add_lesson_video_file(message: Message, state: FSMContext):
    await state.update_data(video_file_id=message.video.file_id, video_url="")
    await save_lesson(message, state)


@router.message(AddLesson.video_file)
async def add_lesson_video_file_invalid(message: Message, state: FSMContext):
    await message.answer("Пожалуйста, загрузите видео файл (или /skip):")


async def save_lesson(message: Message, state: FSMContext):
    data = await state.get_data()
    async with async_session() as session:
        lesson = Lesson(
            section_id=data["section_id"],
            title=data["title"],
            description=data.get("description", ""),
            content_text=data.get("content_text", ""),
            video_url=data.get("video_url", ""),
            video_file_id=data.get("video_file_id", ""),
        )
        session.add(lesson)
        await session.commit()
    await state.clear()
    await message.answer(
        f"✅ Урок «{data['title']}» создан!",
        reply_markup=admin_menu_kb(),
    )


@router.callback_query(F.data.startswith("admin_lesson_"))
async def admin_lesson_actions(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    lesson_id = int(cb.data.split("_")[2])
    lesson = await get_lesson(lesson_id)
    if not lesson:
        await cb.answer("Урок не найден", show_alert=True)
        return
    questions = await get_questions(lesson_id)
    text = (
        f"📖 <b>{lesson.title}</b>\n\n"
        f"{lesson.description or ''}\n"
        f"🎬 YouTube: {'✅' if lesson.video_url else '❌'}\n"
        f"🎬 Видео файл: {'✅' if lesson.video_file_id else '❌'}\n"
        f"📝 Вопросов: {len(questions)}"
    )
    await cb.message.edit_text(text, reply_markup=admin_lesson_actions_kb(lesson_id))


@router.callback_query(F.data.startswith("admin_del_lesson_"))
async def admin_del_lesson_confirm(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    lesson_id = int(cb.data.split("_")[3])
    lesson = await get_lesson(lesson_id)
    if not lesson:
        await cb.answer("Урок не найден", show_alert=True)
        return
    from bot.keyboards import confirm_kb
    await cb.message.edit_text(
        f"❌ <b>Удалить урок</b> «{lesson.title}»?\n\nВсе тесты будут удалены!",
        reply_markup=confirm_kb(f"del_lesson_{lesson_id}"),
    )


@router.callback_query(F.data.startswith("confirm_del_lesson_"))
async def admin_del_lesson_execute(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    lesson_id = int(cb.data.split("_")[3])
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if lesson:
            await session.delete(lesson)
            await session.commit()
    await cb.message.edit_text("✅ Урок удалён.", reply_markup=admin_menu_kb())


# ─── Admin: Quiz ──────────────────────────────────────────────────

@router.callback_query(F.data.startswith("admin_add_quiz_"))
async def admin_add_quiz_start(cb: CallbackQuery, state: FSMContext):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    lesson_id = int(cb.data.split("_")[3])
    lesson = await get_lesson(lesson_id)
    if not lesson:
        await cb.answer("Урок не найден", show_alert=True)
        return
    await state.update_data(lesson_id=lesson_id, questions=[])
    await state.set_state(AddQuiz.question_text)
    await cb.message.edit_text(
        f"➕ <b>Добавление вопросов</b> к уроку «{lesson.title}»\n\n"
        f"Введите текст первого вопроса:",
        reply_markup=back_kb("admin"),
    )


@router.message(AddQuiz.question_text)
async def add_quiz_question_text(message: Message, state: FSMContext):
    await state.update_data(question_text=message.text)
    await state.set_state(AddQuiz.options)
    await message.answer(
        "Введите варианты ответов, каждый с новой строки:\n\n"
        "Пример:\n"
        "Apple\n"
        "Banana\n"
        "Orange\n"
        "Grape",
    )


@router.message(AddQuiz.options)
async def add_quiz_options(message: Message, state: FSMContext):
    options = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
    if len(options) < 2:
        await message.answer("Нужно минимум 2 варианта ответа. Попробуйте снова:")
        return
    await state.update_data(options=options)
    await state.set_state(AddQuiz.correct_answer)
    opts_text = "\n".join(f"{i}. {o}" for i, o in enumerate(options))
    await message.answer(
        f"Варианты:\n{opts_text}\n\n"
        f"Введите <b>номер</b> правильного ответа (0-{len(options) - 1}):"
    )


@router.message(AddQuiz.correct_answer)
async def add_quiz_correct(message: Message, state: FSMContext):
    try:
        correct = int(message.text.strip())
    except ValueError:
        await message.answer("Пожалуйста, введите число.")
        return
    data = await state.get_data()
    if correct < 0 or correct >= len(data["options"]):
        await message.answer(f"Число должно быть от 0 до {len(data['options']) - 1}.")
        return
    await state.update_data(correct_answer=correct)
    await state.set_state(AddQuiz.explanation)
    await message.answer(
        "Введите объяснение правильного ответа (или /skip):"
    )


@router.message(AddQuiz.explanation)
async def add_quiz_explanation(message: Message, state: FSMContext):
    explanation = message.text if message.text != "/skip" else ""
    data = await state.get_data()
    questions = data.get("questions", [])
    questions.append({
        "question_text": data["question_text"],
        "options": data["options"],
        "correct_answer": data["correct_answer"],
        "explanation": explanation,
    })
    await state.update_data(questions=questions)

    from bot.keyboards import confirm_kb
    await message.answer(
        f"✅ Вопрос сохранён! (всего: {len(questions)})\n\n"
        f"Хотите добавить ещё вопрос?",
        reply_markup=confirm_kb("add_another_question"),
    )


@router.callback_query(F.data == "confirm_add_another_question")
async def add_another_question(cb: CallbackQuery, state: FSMContext):
    await state.set_state(AddQuiz.question_text)
    await cb.message.edit_text("Введите текст следующего вопроса:")


@router.callback_query(F.data == "cancel")
async def cancel_add_question(cb: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    lesson_id = data.get("lesson_id")
    questions = data.get("questions", [])

    if questions:
        async with async_session() as session:
            for q in questions:
                question = Question(
                    lesson_id=lesson_id,
                    question_text=q["question_text"],
                    options=q["options"],
                    correct_answer=q["correct_answer"],
                    explanation=q.get("explanation", ""),
                )
                session.add(question)
            await session.commit()
        await cb.message.edit_text(
            f"✅ Добавлено вопросов: {len(questions)}",
            reply_markup=admin_menu_kb(),
        )
    else:
        await cb.message.edit_text("❌ Вопросы не добавлены.", reply_markup=admin_menu_kb())
    await state.clear()


@router.callback_query(F.data.startswith("admin_quiz_list_"))
async def admin_quiz_list(cb: CallbackQuery):
    uid = str(cb.from_user.id)
    if not is_admin(uid):
        return
    lesson_id = int(cb.data.split("_")[3])
    lesson = await get_lesson(lesson_id)
    questions = await get_questions(lesson_id)
    if not questions:
        await cb.message.edit_text(
            f"📝 Вопросы к уроку «{lesson.title}»:\n\nПока нет вопросов.",
            reply_markup=back_kb(f"admin_lesson_{lesson_id}"),
        )
        return
    text = f"📝 <b>Вопросы к уроку</b> «{lesson.title}»:\n\n"
    for i, q in enumerate(questions, 1):
        text += f"{i}. {q.question_text}\n"
        text += f"   ✅ Вариант {q.correct_answer}: {q.options[q.correct_answer] if q.correct_answer < len(q.options) else '?'}\n\n"
    await cb.message.edit_text(text.strip(), reply_markup=back_kb(f"admin_lesson_{lesson_id}"))


# ─── Cancel any FSM ───────────────────────────────────────────────

@router.message(Command("cancel"))
async def cancel_fsm(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚫 Действие отменено.", reply_markup=main_menu_kb(is_admin(str(message.from_user.id))))
