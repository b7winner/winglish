import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import MenuButtonWebApp, WebAppInfo
from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import APP_URL, ADMIN_ID, BOT_TOKEN
from database import async_session, init_db, Section, Lesson, Question, UserProgress

logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"

# ─── Bot setup ───────────────────────────────────────────────────

_bot: Bot | None = None
_polling_task: asyncio.Task | None = None


async def start_bot():
    global _bot, _polling_task
    _bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    from bot.handlers import router
    dp.include_router(router)
    logger.info("Starting bot polling...")
    _polling_task = asyncio.create_task(dp.start_polling(_bot))
    await asyncio.sleep(1)
    try:
        await _bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(text="📚 Winglish", web_app=WebAppInfo(url=f"{APP_URL}/webapp/app"))
        )
        logger.info("Menu button set")
    except Exception as e:
        logger.warning(f"Failed to set menu button: {e}")


async def stop_bot():
    global _bot, _polling_task
    if _polling_task:
        _polling_task.cancel()
        try:
            await _polling_task
        except asyncio.CancelledError:
            pass
    if _bot:
        await _bot.session.close()
    logger.info("Bot stopped.")


# ─── Lifespan ────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    asyncio.create_task(start_bot())
    yield
    await stop_bot()


# ─── FastAPI app ─────────────────────────────────────────────────

app = FastAPI(title="Winglish — English Learning", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─── Root & Health ──────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "app": "Winglish — English Learning Bot",
        "status": "running",
        "bot": "https://t.me/bigwinglishbot",
        "webapp": "/webapp/app",
    }


@app.get("/ping")
async def ping():
    return {"ok": True}


# ─── Auth Helper ─────────────────────────────────────────────────

def get_user_id(request: Request) -> str:
    return request.query_params.get("user_id") or request.headers.get("X-User-Id", "")


# ─── Public API ──────────────────────────────────────────────────

@app.get("/api/sections")
async def api_sections():
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(select(Section).order_by(Section.order, Section.id))
        sections = result.scalars().all()
    return [
        {"id": s.id, "title": s.title, "description": s.description, "icon": s.icon}
        for s in sections
    ]


@app.get("/api/sections/{section_id}/lessons")
async def api_lessons(section_id: int, user_id: str = Query("")):
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(Lesson).where(Lesson.section_id == section_id).order_by(Lesson.order, Lesson.id)
        )
        lessons = result.scalars().all()
        completed_ids = set()
        if user_id:
            prog_result = await session.execute(
                select(UserProgress).where(
                    UserProgress.user_id == user_id,
                    UserProgress.completed == True,
                )
            )
            completed_ids = {p.lesson_id for p in prog_result.scalars().all()}
    return [
        {"id": l.id, "title": l.title, "description": l.description,
         "completed": l.id in completed_ids, "has_quiz": len(l.questions) > 0}
        for l in lessons
    ]


@app.get("/api/lessons/{lesson_id}")
async def api_lesson(lesson_id: int):
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson:
            return JSONResponse({"error": "Lesson not found"}, status_code=404)
        return {
            "id": lesson.id, "title": lesson.title,
            "description": lesson.description, "content_text": lesson.content_text,
            "video_url": lesson.video_url, "video_file_id": lesson.video_file_id,
            "questions_count": len(lesson.questions),
        }


@app.get("/api/lessons/{lesson_id}/questions")
async def api_questions(lesson_id: int):
    from sqlalchemy import select
    async with async_session() as session:
        result = await session.execute(
            select(Question).where(Question.lesson_id == lesson_id).order_by(Question.id)
        )
        questions = result.scalars().all()
    return [
        {
            "id": q.id, "question_text": q.question_text,
            "options": q.options, "correct_answer": q.correct_answer,
            "explanation": q.explanation,
        }
        for q in questions
    ]


@app.get("/api/progress")
async def api_progress(user_id: str = Query("")):
    if not user_id:
        return {"error": "user_id required"}, 400
    from sqlalchemy import select, func
    async with async_session() as session:
        total_lessons = (await session.execute(select(func.count(Lesson.id)))).scalar() or 0
        completed = (await session.execute(
            select(func.count(UserProgress.id))
            .where(UserProgress.user_id == user_id, UserProgress.completed == True)
        )).scalar() or 0
        total_score = (await session.execute(
            select(func.coalesce(func.sum(UserProgress.score), 0))
            .where(UserProgress.user_id == user_id)
        )).scalar() or 0
        return {"total_lessons": total_lessons, "completed": completed, "total_score": total_score}


# ─── Admin API ───────────────────────────────────────────────────

@app.post("/api/admin/sections")
async def admin_create_section(request: Request):
    uid = get_user_id(request)
    if uid != ADMIN_ID:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    body = await request.json()
    async with async_session() as session:
        section = Section(title=body["title"], description=body.get("description", ""), icon=body.get("icon", "📚"))
        session.add(section)
        await session.commit()
        return {"id": section.id, "title": section.title, "icon": section.icon}


@app.put("/api/admin/sections/{section_id}")
async def admin_update_section(section_id: int, request: Request):
    uid = get_user_id(request)
    if uid != ADMIN_ID:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    body = await request.json()
    async with async_session() as session:
        section = await session.get(Section, section_id)
        if not section:
            return JSONResponse({"error": "Not found"}, status_code=404)
        for field in ("title", "description", "icon"):
            if field in body:
                setattr(section, field, body[field])
        await session.commit()
        return {"id": section.id, "title": section.title, "icon": section.icon}


@app.delete("/api/admin/sections/{section_id}")
async def admin_delete_section(section_id: int, request: Request):
    uid = get_user_id(request)
    if uid != ADMIN_ID:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    async with async_session() as session:
        section = await session.get(Section, section_id)
        if section:
            await session.delete(section)
            await session.commit()
    return {"ok": True}


@app.post("/api/admin/lessons")
async def admin_create_lesson(request: Request):
    uid = get_user_id(request)
    if uid != ADMIN_ID:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    body = await request.json()
    async with async_session() as session:
        lesson = Lesson(
            section_id=body["section_id"], title=body["title"],
            description=body.get("description", ""), content_text=body.get("content_text", ""),
            video_url=body.get("video_url", ""), video_file_id=body.get("video_file_id", ""),
        )
        session.add(lesson)
        await session.commit()
        return {"id": lesson.id, "title": lesson.title}


@app.put("/api/admin/lessons/{lesson_id}")
async def admin_update_lesson(lesson_id: int, request: Request):
    uid = get_user_id(request)
    if uid != ADMIN_ID:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    body = await request.json()
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson:
            return JSONResponse({"error": "Not found"}, status_code=404)
        for field in ("title", "description", "content_text", "video_url", "video_file_id"):
            if field in body:
                setattr(lesson, field, body[field])
        await session.commit()
        return {"id": lesson.id, "title": lesson.title}


@app.delete("/api/admin/lessons/{lesson_id}")
async def admin_delete_lesson(lesson_id: int, request: Request):
    uid = get_user_id(request)
    if uid != ADMIN_ID:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if lesson:
            await session.delete(lesson)
            await session.commit()
    return {"ok": True}


@app.post("/api/admin/questions")
async def admin_create_question(request: Request):
    uid = get_user_id(request)
    if uid != ADMIN_ID:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    body = await request.json()
    async with async_session() as session:
        q = Question(
            lesson_id=body["lesson_id"], question_text=body["question_text"],
            options=body["options"], correct_answer=body["correct_answer"],
            explanation=body.get("explanation", ""),
        )
        session.add(q)
        await session.commit()
        return {"id": q.id}


@app.delete("/api/admin/questions/{question_id}")
async def admin_delete_question(question_id: int, request: Request):
    uid = get_user_id(request)
    if uid != ADMIN_ID:
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    async with async_session() as session:
        q = await session.get(Question, question_id)
        if q:
            await session.delete(q)
            await session.commit()
    return {"ok": True}


# ─── WebApp Pages ────────────────────────────────────────────────

@app.get("/webapp/app")
async def webapp_app():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html)


@app.get("/webapp/player")
async def webapp_player(lesson_id: int = Query(...)):
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
    if not lesson:
        return HTMLResponse("<h2>Lesson not found</h2>", status_code=404)
    html = (STATIC_DIR / "player.html").read_text(encoding="utf-8")
    html = html.replace("{{LESSON_TITLE}}", lesson.title or "")
    html = html.replace("{{VIDEO_URL}}", lesson.video_url or "")
    return HTMLResponse(html)


@app.get("/webapp/quiz")
async def webapp_quiz(lesson_id: int = Query(...)):
    from sqlalchemy import select
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson:
            return HTMLResponse("<h2>Lesson not found</h2>", status_code=404)
        result = await session.execute(
            select(Question).where(Question.lesson_id == lesson_id).order_by(Question.id)
        )
        questions = result.scalars().all()
    if not questions:
        return HTMLResponse("<h2>No questions for this lesson</h2>", status_code=404)
    api_url = APP_URL.rstrip("/")
    html = (STATIC_DIR / "quiz.html").read_text(encoding="utf-8")
    html = html.replace("{{LESSON_ID}}", str(lesson_id))
    html = html.replace("{{LESSON_TITLE}}", lesson.title or "")
    html = html.replace("{{API_URL}}", api_url)
    return HTMLResponse(html)
