from pathlib import Path

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from config import APP_URL
from database import async_session, Section, Lesson, Question, UserProgress

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="English Learning WebApp")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─── Root & Health ──────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "app": "Winglish — English Learning Bot",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
            "bot": "https://t.me/bigwinglishbot",
            "webapp_player": "/webapp/player?lesson_id=X",
            "webapp_quiz": "/webapp/quiz?lesson_id=X",
            "api_sections": "/api/sections",
            "api_lessons": "/api/sections/{id}/lessons",
            "api_questions": "/api/lessons/{id}/questions",
            "health": "/ping",
        },
    }


@app.get("/ping")
async def ping():
    return {"ok": True}


# ─── API ─────────────────────────────────────────────────────────

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
        {
            "id": l.id,
            "title": l.title,
            "description": l.description,
            "completed": l.id in completed_ids,
        }
        for l in lessons
    ]


@app.get("/api/lessons/{lesson_id}")
async def api_lesson(lesson_id: int):
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
        if not lesson:
            return JSONResponse({"error": "Lesson not found"}, status_code=404)
        return {
            "id": lesson.id,
            "title": lesson.title,
            "description": lesson.description,
            "content_text": lesson.content_text,
            "video_url": lesson.video_url,
            "video_file_id": lesson.video_file_id,
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
            "id": q.id,
            "question_text": q.question_text,
            "options": q.options,
            "correct_answer": q.correct_answer,
            "explanation": q.explanation,
        }
        for q in questions
    ]


# ─── Auth Helper ─────────────────────────────────────────────────

def extract_user_id(request: Request) -> str:
    tg_data = request.headers.get("X-Telegram-User-Id", "")
    if tg_data:
        return tg_data
    return request.query_params.get("user_id", "")


# ─── WebApp Pages ────────────────────────────────────────────────

@app.get("/webapp/player")
async def webapp_player(lesson_id: int = Query(...), request: Request = None):
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
    if not lesson:
        return HTMLResponse("<h2>Lesson not found</h2>", status_code=404)

    html = (STATIC_DIR / "player.html").read_text(encoding="utf-8")
    html = html.replace("{{LESSON_TITLE}}", lesson.title or "")
    html = html.replace("{{VIDEO_URL}}", lesson.video_url or "")
    return HTMLResponse(html)


@app.get("/webapp/quiz")
async def webapp_quiz(lesson_id: int = Query(...), request: Request = None):
    async with async_session() as session:
        lesson = await session.get(Lesson, lesson_id)
    if not lesson:
        return HTMLResponse("<h2>Lesson not found</h2>", status_code=404)

    from sqlalchemy import select
    async with async_session() as session:
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
