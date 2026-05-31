from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import APP_URL


def main_menu_kb(is_admin: bool = False) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📚 Разделы", callback_data="sections")
    builder.button(text="📊 Мой прогресс", callback_data="my_progress")
    if is_admin:
        builder.button(text="⚙️ Админка", callback_data="admin")
    builder.adjust(1)
    return builder.as_markup()


def sections_kb(sections: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in sections:
        builder.button(text=f"{s.icon} {s.title}", callback_data=f"section_{s.id}")
    builder.button(text="◀️ Назад", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def lessons_kb(lessons: list, section_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for l in lessons:
        builder.button(text=l.title, callback_data=f"lesson_{l.id}")
    builder.button(text="◀️ Назад", callback_data="sections")
    builder.adjust(1)
    return builder.as_markup()


def lesson_actions_kb(lesson_id: int,
                      has_video_url: bool, has_video_file: bool,
                      has_quiz: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_video_url:
        builder.button(text="🎬 Смотреть видео",
                       web_app=WebAppInfo(url=f"{APP_URL}/webapp/player?lesson_id={lesson_id}"))
    if has_video_file:
        builder.button(text="🎬 Смотреть видео (файл)",
                       callback_data=f"lesson_video_{lesson_id}")
    if has_quiz:
        builder.button(text="📝 Пройти тест",
                       web_app=WebAppInfo(url=f"{APP_URL}/webapp/quiz?lesson_id={lesson_id}"))
    builder.button(text="◀️ Назад", callback_data="section_lessons_back")
    builder.adjust(1)
    return builder.as_markup()


def admin_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить раздел", callback_data="admin_add_section")
    builder.button(text="📋 Список разделов", callback_data="admin_list_sections")
    builder.button(text="◀️ Назад", callback_data="back_main")
    builder.adjust(1)
    return builder.as_markup()


def admin_sections_kb(sections: list) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for s in sections:
        builder.button(text=f"{s.icon} {s.title}", callback_data=f"admin_section_{s.id}")
    builder.button(text="◀️ Назад", callback_data="admin")
    builder.adjust(1)
    return builder.as_markup()


def admin_section_actions_kb(section_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить урок", callback_data=f"admin_add_lesson_{section_id}")
    builder.button(text="📋 Уроки раздела", callback_data=f"admin_section_lessons_{section_id}")
    builder.button(text="❌ Удалить раздел", callback_data=f"admin_del_section_{section_id}")
    builder.button(text="◀️ Назад", callback_data="admin_list_sections")
    builder.adjust(1)
    return builder.as_markup()


def admin_lessons_kb(lessons: list, section_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for l in lessons:
        builder.button(text=l.title, callback_data=f"admin_lesson_{l.id}")
    builder.button(text="➕ Добавить урок", callback_data=f"admin_add_lesson_{section_id}")
    builder.button(text="◀️ Назад", callback_data=f"admin_section_{section_id}")
    builder.adjust(1)
    return builder.as_markup()


def admin_lesson_actions_kb(lesson_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="➕ Добавить вопросы", callback_data=f"admin_add_quiz_{lesson_id}")
    builder.button(text="📝 Вопросы теста", callback_data=f"admin_quiz_list_{lesson_id}")
    builder.button(text="❌ Удалить урок", callback_data=f"admin_del_lesson_{lesson_id}")
    builder.button(text="◀️ Назад", callback_data="admin_list_sections")
    builder.adjust(1)
    return builder.as_markup()


def back_kb(callback_data: str = "back_main") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="◀️ Назад", callback_data=callback_data)
    return builder.as_markup()
