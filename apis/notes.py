from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status as fast_status
from pydantic import BaseModel, Field

from apis.base import error_response, success_response
from core.auth import get_current_user
from core.db import DB
from core.models.article import ArticleBase
from core.models.article_note import ArticleNote
from core.config import cfg


router = APIRouter(prefix="/notes", tags=["笔记"])


def _get_user_id(current_user: dict) -> str:
    u = current_user.get("original_user")
    return str(getattr(u, "id", "")) or current_user.get("username", "")


class NoteCreate(BaseModel):
    article_id: str = Field(..., description="文章ID")
    content: str = Field(..., min_length=1, description="笔记内容(纯文本/Markdown)")


class NoteUpdate(BaseModel):
    content: str = Field(..., min_length=1, description="笔记内容(纯文本/Markdown)")


class NoteRewriteOptions(BaseModel):
    save: bool = Field(False, description="是否覆盖保存到原笔记")
    style: str = Field("markdown", description="输出风格(当前仅markdown)")


@router.get("", summary="获取笔记列表")
async def list_notes(
    article_id: str | None = Query(None),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)

    q = session.query(ArticleNote).filter(ArticleNote.user_id == user_id)
    if article_id:
        q = q.filter(ArticleNote.article_id == article_id)
    q = q.order_by(ArticleNote.updated_at.desc(), ArticleNote.id.desc())

    total = q.count()
    notes = q.offset(offset).limit(limit).all()
    items = []
    for n in notes:
        d = n.__dict__.copy()
        d.pop("_sa_instance_state", None)
        items.append(d)
    return success_response({"list": items, "total": total})


@router.post("", summary="创建笔记")
async def create_note(
    payload: NoteCreate,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)
    article = session.query(ArticleBase.id).filter(ArticleBase.id == payload.article_id).first()
    if not article:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="文章不存在"),
        )

    now = datetime.now()
    note = ArticleNote(
        user_id=user_id,
        article_id=payload.article_id,
        content=payload.content,
        created_at=now,
        updated_at=now,
    )
    session.add(note)
    session.commit()
    session.refresh(note)
    d = note.__dict__.copy()
    d.pop("_sa_instance_state", None)
    return success_response(d)


@router.put("/{note_id}", summary="更新笔记")
async def update_note(
    note_id: int,
    payload: NoteUpdate,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)
    note = (
        session.query(ArticleNote)
        .filter(ArticleNote.id == note_id, ArticleNote.user_id == user_id)
        .first()
    )
    if not note:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="笔记不存在"),
        )
    note.content = payload.content
    note.updated_at = datetime.now()
    session.add(note)
    session.commit()
    session.refresh(note)
    d = note.__dict__.copy()
    d.pop("_sa_instance_state", None)
    return success_response(d)


@router.delete("/{note_id}", summary="删除笔记")
async def delete_note(
    note_id: int,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)
    deleted = (
        session.query(ArticleNote)
        .filter(ArticleNote.id == note_id, ArticleNote.user_id == user_id)
        .delete(synchronize_session=False)
    )
    session.commit()
    if not deleted:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="笔记不存在"),
        )
    return success_response({"deleted": True, "id": note_id})


@router.post("/{note_id}/rewrite", summary="笔记转写/润色(LLM，可选)")
async def rewrite_note(
    note_id: int,
    payload: NoteRewriteOptions,
    current_user: dict = Depends(get_current_user),
):
    session = DB.get_session()
    user_id = _get_user_id(current_user)
    note = (
        session.query(ArticleNote)
        .filter(ArticleNote.id == note_id, ArticleNote.user_id == user_id)
        .first()
    )
    if not note:
        raise HTTPException(
            status_code=fast_status.HTTP_404_NOT_FOUND,
            detail=error_response(code=40401, message="笔记不存在"),
        )

    from core.llm.siliconflow import siliconflow_chat_text

    system = (
        "你是一个笔记转写助手。将用户的原始笔记润色为更清晰的Markdown笔记。"
        "只输出Markdown正文，不要输出任何额外说明。"
    )
    user = (
        "请将以下笔记转写为结构化Markdown：\n"
        "- 保留原意，纠正错别字\n"
        "- 自动分段，必要时用标题/列表\n"
        "- 生成一个简短的「要点」列表\n\n"
        f"原始笔记：\n{note.content}"
    )

    rewritten = await siliconflow_chat_text(
        model=cfg.get("llm.siliconflow.model", ""),
        api_url=cfg.get("llm.siliconflow.api_url", ""),
        api_key=cfg.get("llm.siliconflow.api_key", ""),
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user[: int(cfg.get('llm.max_chars', 24000))]},
        ],
        timeout=float(cfg.get("llm.timeout", 60)),
    )

    if payload.save:
        note.content = rewritten
        note.updated_at = datetime.now()
        session.add(note)
        session.commit()

    return success_response({"id": note_id, "rewritten": rewritten, "saved": bool(payload.save)})
