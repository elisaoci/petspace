import json
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select

from app.api.deps import CurrentUser, DbSession, get_owned_pet
from app.config import get_settings
from app.models import ChatMessage, Pet
from app.schemas.chat import ChatRequest

router = APIRouter(prefix="/chat", tags=["chat"])

# Сколько последних сообщений диалога уходит в модель: ограничиваем окно контекста.
HISTORY_LIMIT = 20


def _user_pet_ids(user: CurrentUser, db: DbSession):
    return select(Pet.id).where(Pet.owner_id == user.id)


@router.get("/history/{conversation_id}")
def get_history(conversation_id: str, user: CurrentUser, db: DbSession):
    """История диалога доступна только по питомцам текущего владельца."""
    messages = db.scalars(
        select(ChatMessage)
        .join(Pet, Pet.id == ChatMessage.pet_id)
        .where(ChatMessage.conversation_id == conversation_id, Pet.owner_id == user.id)
        .order_by(ChatMessage.id)
    ).all()
    return [
        {
            "id": message.id,
            "role": message.role,
            "content": message.content,
            "created_at": message.created_at,
        }
        for message in messages
    ]


@router.delete("/history/{conversation_id}", status_code=204)
def clear_history(conversation_id: str, user: CurrentUser, db: DbSession):
    db.execute(
        delete(ChatMessage).where(
            ChatMessage.conversation_id == conversation_id,
            ChatMessage.pet_id.in_(_user_pet_ids(user, db)),
        )
    )
    db.commit()


@router.post("/stream")
async def stream_chat(payload: ChatRequest, user: CurrentUser, db: DbSession):
    pet = get_owned_pet(payload.pet_id, user, db)

    history = db.scalars(
        select(ChatMessage)
        .where(ChatMessage.conversation_id == payload.conversation_id, ChatMessage.pet_id == pet.id)
        .order_by(ChatMessage.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    history = list(reversed(history))

    db.add(ChatMessage(pet_id=pet.id, conversation_id=payload.conversation_id, role="user", content=payload.message))
    db.commit()

    pet_context = (
        f"Имя: {pet.name}; вид: {pet.species}; порода: {pet.breed or 'не указана'}; "
        f"рост: {pet.height_cm or 'не указан'} см; вес: {pet.weight_kg or 'не указан'} кг; "
        f"аллергии: {pet.allergies or 'не указаны'}; "
        f"хронические болезни: {pet.chronic_conditions or 'не указаны'}; "
        f"заметки владельца: {pet.owner_notes or 'нет'}."
    )
    system_prompt = (
        "Ты — осторожный ИИ-ассистент PetSpace. Отвечай по-русски, кратко и по делу, "
        "по уходу, кормлению, поведению и симптомам питомца. Учитывай контекст питомца ниже. "
        "Не ставь диагнозы и не назначай дозировки лекарств. Всегда напоминай, что ответ не заменяет "
        "ветеринара. При отравлении, судорогах, затруднённом дыхании или кровотечении сразу рекомендуй "
        "срочно ехать в клинику. Для кормления уточняй возраст, активность и тип корма, давай диапазон "
        "и советуй ориентироваться на таблицу упаковки.\n\n"
        f"Контекст питомца: {pet_context}"
    )
    messages = [{"role": "system", "content": system_prompt}] + [
        {"role": m.role, "content": m.content} for m in history
    ] + [{"role": "user", "content": payload.message}]
    settings = get_settings()

    async def generate() -> AsyncIterator[str]:
        answer = []
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={"model": settings.ollama_model, "messages": messages, "stream": True}) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line: continue
                        data = json.loads(line)
                        chunk = data.get("message", {}).get("content", "")
                        if chunk:
                            answer.append(chunk)
                            yield f"data: {json.dumps({'content': chunk}, ensure_ascii=False)}\n\n"
                        if data.get("done"): break
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            yield f"data: {json.dumps({'error': str(exc)})}\n\n"
        finally:
            if answer:
                db.add(ChatMessage(pet_id=pet.id, conversation_id=payload.conversation_id, role="assistant", content="".join(answer)))
                db.commit()
            yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
