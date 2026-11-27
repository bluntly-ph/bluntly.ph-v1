"""The Inbox and Messages (0076): a member and the Bluntly team.

Member (signed in; their own conversations only — 404 otherwise):

    GET  /conversations                     ?seller_id= &status=open|closed
    GET  /conversations/unread              ?seller_id=
    GET  /conversations/link-options        ?audience=seller|reviewer &seller_id=
    POST /conversations                     multipart: audience, topic, body, [seller_id,
                                            link_type, link_id, file]
    GET  /conversations/{id}                (marks it read for the member)
    POST /conversations/{id}/messages       multipart: body, [file]
    PATCH /conversations/{id}/messages/{mid}          {body}: edit your message (MQA-011)
    POST /conversations/{id}/messages/{mid}/unsend    take it back for everyone
    POST /conversations/{id}/messages/{mid}/hide      delete it for yourself
    POST /conversations/{id}/resolve
    POST /conversations/{id}/email-copy

Staff (Administrator or Super Admin):

    GET  /admin/inbox                       ?tab= &topic= &status= &handled= &q= &sort=
                                            &page= &size=
    GET  /admin/inbox/unread
    GET  /admin/inbox/staff
    GET  /admin/inbox/{id}                  (marks it read for the team)
    POST /admin/inbox/{id}/messages         multipart: body, [file]
    PATCH /admin/inbox/{id}/messages/{mid}  {body}; .../unsend; .../hide (as above)
    POST /admin/inbox/{id}/assign           {admin_id | null}
    POST /admin/inbox/{id}/status           {status}
    POST /admin/inbox/{id}/move-to-support

Either party (or staff): GET /conversations/{id}/messages/{mid}/attachment
answers {url}, a 5-minute signed URL to the private file.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.security import get_current_user, require_staff
from app.db.session import get_db
from app.models.enums import ConversationAudience, ConversationStatus, ConversationTopic
from app.models.user import User
from app.schemas.conversation import (
    ConversationAssign,
    ConversationDetailOut,
    ConversationMessageOut,
    ConversationStatusIn,
    InboxListOut,
    LinkOptionOut,
    MemberListOut,
    StaffOptionOut,
)
from app.services import conversation_service as svc

router = APIRouter(tags=["conversations"])


class UnreadOut(BaseModel):
    unread: int


class AttachmentUrlOut(BaseModel):
    url: str


async def _file(file: UploadFile | None) -> svc.Attachment | None:
    if file is None or not file.filename:
        return None
    data = await file.read()
    return svc.Attachment(data=data, name=file.filename) if data else None


# ------------------------------------------------------------------ member

@router.get("/conversations", response_model=MemberListOut,
            summary="Your conversations with the Bluntly team")
def my_conversations(seller_id: uuid.UUID | None = None,
                     status: Literal["open", "closed"] = "open",
                     db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> MemberListOut:
    return svc.list_mine(db, user, seller_id=seller_id, status=status)


@router.get("/conversations/unread", response_model=UnreadOut,
            summary="How many of your conversations have an unread reply")
def my_unread(seller_id: uuid.UUID | None = None, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> UnreadOut:
    return UnreadOut(unread=svc.unread_for_member(db, user, seller_id))


@router.get("/conversations/link-options", response_model=list[LinkOptionOut],
            summary="What a new conversation can be linked to (your own things)")
def link_options(audience: ConversationAudience, seller_id: uuid.UUID | None = None,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> list[LinkOptionOut]:
    return svc.link_options(db, user, audience=audience, seller_id=seller_id)


@router.post("/conversations", response_model=ConversationDetailOut, status_code=201,
             summary="Start a conversation with the Bluntly team")
async def start_conversation(
        audience: ConversationAudience = Form(...), topic: ConversationTopic = Form(...),
        body: str = Form(...), seller_id: uuid.UUID | None = Form(default=None),
        link_type: str | None = Form(default=None), link_id: uuid.UUID | None = Form(default=None),
        file: UploadFile | None = File(default=None), db: Session = Depends(get_db),
        user: User = Depends(get_current_user)) -> ConversationDetailOut:
    return svc.start(db, user, audience=audience, seller_id=seller_id, topic=topic,
                     link_type=link_type or None, link_id=link_id, body=body,
                     file=await _file(file))


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut,
            summary="One of your conversations, with its messages")
def my_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> ConversationDetailOut:
    return svc.get_mine(db, user, conversation_id)


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationMessageOut,
             status_code=201, summary="Reply in one of your conversations")
async def reply(conversation_id: uuid.UUID, body: str = Form(default=""),
                file: UploadFile | None = File(default=None), db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> ConversationMessageOut:
    return svc.reply_mine(db, user, conversation_id, body, await _file(file))


class MessageEditIn(BaseModel):
    body: str = Field(default="", max_length=svc.MAX_REPLY + 100)


@router.patch("/conversations/{conversation_id}/messages/{message_id}",
              response_model=ConversationMessageOut,
              summary="Edit a message you sent, within minutes of sending it")
def edit_mine(conversation_id: uuid.UUID, message_id: uuid.UUID, payload: MessageEditIn,
              db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> ConversationMessageOut:
    return svc.edit_message(db, user, conversation_id, message_id, payload.body, staff=False)


@router.post("/conversations/{conversation_id}/messages/{message_id}/unsend",
             response_model=ConversationMessageOut,
             summary="Unsend a message you sent, for everyone, within minutes of sending it")
def unsend_mine(conversation_id: uuid.UUID, message_id: uuid.UUID,
                db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> ConversationMessageOut:
    return svc.unsend_message(db, user, conversation_id, message_id, staff=False)


@router.post("/conversations/{conversation_id}/messages/{message_id}/hide", status_code=204,
             response_class=Response, summary="Delete a message for yourself")
def hide_mine(conversation_id: uuid.UUID, message_id: uuid.UUID,
              db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> Response:
    svc.hide_message(db, user, conversation_id, message_id, staff=False)
    return Response(status_code=204)


@router.post("/conversations/{conversation_id}/resolve", response_model=ConversationDetailOut,
             summary="Mark your conversation resolved (a reply opens it again)")
def resolve(conversation_id: uuid.UUID, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> ConversationDetailOut:
    return svc.resolve_mine(db, user, conversation_id)


@router.post("/conversations/{conversation_id}/email-copy", status_code=204,
             response_class=Response, summary="Email yourself a copy of the conversation")
def email_copy(conversation_id: uuid.UUID, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> Response:
    svc.email_copy(db, user, conversation_id)
    return Response(status_code=204)


@router.get("/conversations/{conversation_id}/messages/{message_id}/attachment",
            response_model=AttachmentUrlOut,
            summary="A short-lived link to a message's attachment (its parties and staff)")
def attachment(conversation_id: uuid.UUID, message_id: uuid.UUID,
               download: bool = Query(default=False), db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> AttachmentUrlOut:
    return AttachmentUrlOut(url=svc.attachment_url(db, user, conversation_id, message_id,
                                                   download=download))


# ------------------------------------------------------------------ staff

@router.get("/admin/inbox", response_model=InboxListOut, tags=["admin: inbox"],
            summary="The team's inbox")
def inbox(tab: Literal["all", "sellers", "reviewers", "closed"] = "all",
          topic: ConversationTopic | None = None, status: ConversationStatus | None = None,
          handled: Literal["unassigned", "me", "others"] | None = None,
          q: str | None = Query(default=None, max_length=120),
          sort: Literal["latest", "waiting", "unread"] = "latest",
          page: int = Query(default=1, ge=1), size: int = Query(default=25, ge=1, le=50),
          db: Session = Depends(get_db), staff: User = Depends(require_staff)) -> InboxListOut:
    return svc.inbox(db, staff, tab=tab, topic=topic, status=status, handled=handled, q=q,
                     sort=sort, page=page, size=size)


@router.get("/admin/inbox/unread", response_model=UnreadOut, tags=["admin: inbox"],
            summary="Open conversations the team has not read (the rail count)")
def inbox_unread(db: Session = Depends(get_db),
                 staff: User = Depends(require_staff)) -> UnreadOut:
    return UnreadOut(unread=svc.inbox_unread(db))


@router.get("/admin/inbox/staff", response_model=list[StaffOptionOut], tags=["admin: inbox"],
            summary="Who a conversation can be assigned to")
def inbox_staff(db: Session = Depends(get_db),
                staff: User = Depends(require_staff)) -> list[StaffOptionOut]:
    return svc.staff_options(db)


@router.get("/admin/inbox/{conversation_id}", response_model=ConversationDetailOut,
            tags=["admin: inbox"], summary="One conversation, with its messages")
def inbox_conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db),
                       staff: User = Depends(require_staff)) -> ConversationDetailOut:
    return svc.staff_get(db, staff, conversation_id)


@router.post("/admin/inbox/{conversation_id}/messages", response_model=ConversationMessageOut,
             status_code=201, tags=["admin: inbox"], summary="Reply as the Bluntly team")
async def inbox_reply(conversation_id: uuid.UUID, body: str = Form(default=""),
                      file: UploadFile | None = File(default=None),
                      db: Session = Depends(get_db),
                      staff: User = Depends(require_staff)) -> ConversationMessageOut:
    return svc.staff_reply(db, staff, conversation_id, body, await _file(file))


@router.patch("/admin/inbox/{conversation_id}/messages/{message_id}",
              response_model=ConversationMessageOut, tags=["admin: inbox"],
              summary="Edit a reply you sent, within minutes of sending it")
def inbox_edit(conversation_id: uuid.UUID, message_id: uuid.UUID, payload: MessageEditIn,
               db: Session = Depends(get_db),
               staff: User = Depends(require_staff)) -> ConversationMessageOut:
    return svc.edit_message(db, staff, conversation_id, message_id, payload.body, staff=True)


@router.post("/admin/inbox/{conversation_id}/messages/{message_id}/unsend",
             response_model=ConversationMessageOut, tags=["admin: inbox"],
             summary="Unsend a reply you sent, for everyone, within minutes of sending it")
def inbox_unsend(conversation_id: uuid.UUID, message_id: uuid.UUID,
                 db: Session = Depends(get_db),
                 staff: User = Depends(require_staff)) -> ConversationMessageOut:
    return svc.unsend_message(db, staff, conversation_id, message_id, staff=True)


@router.post("/admin/inbox/{conversation_id}/messages/{message_id}/hide", status_code=204,
             response_class=Response, tags=["admin: inbox"],
             summary="Delete a message for yourself")
def inbox_hide(conversation_id: uuid.UUID, message_id: uuid.UUID,
               db: Session = Depends(get_db), staff: User = Depends(require_staff)) -> Response:
    svc.hide_message(db, staff, conversation_id, message_id, staff=True)
    return Response(status_code=204)


@router.post("/admin/inbox/{conversation_id}/assign", response_model=ConversationDetailOut,
             tags=["admin: inbox"], summary="Assign the conversation (or unassign it)")
def inbox_assign(conversation_id: uuid.UUID, payload: ConversationAssign,
                 db: Session = Depends(get_db),
                 staff: User = Depends(require_staff)) -> ConversationDetailOut:
    return svc.assign(db, staff, conversation_id, payload.admin_id)


@router.post("/admin/inbox/{conversation_id}/status", response_model=ConversationDetailOut,
             tags=["admin: inbox"], summary="Open, waiting on them, or closed")
def inbox_status(conversation_id: uuid.UUID, payload: ConversationStatusIn,
                 db: Session = Depends(get_db),
                 staff: User = Depends(require_staff)) -> ConversationDetailOut:
    return svc.set_status(db, staff, conversation_id, payload.status)


@router.post("/admin/inbox/{conversation_id}/move-to-support",
             response_model=ConversationDetailOut, tags=["admin: inbox"],
             summary="Move a store's conversation to Queue → Support")
def inbox_move(conversation_id: uuid.UUID, db: Session = Depends(get_db),
               staff: User = Depends(require_staff)) -> ConversationDetailOut:
    return svc.move_to_support(db, staff, conversation_id)
