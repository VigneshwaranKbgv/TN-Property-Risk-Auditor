"""
routers/chat.py
POST /api/chat — streaming follow-up Q&A with the property advisor LLM.
"""

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.llm_service import answer_followup

logger = logging.getLogger(__name__)
router = APIRouter()


# ── Request model ─────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str
    risk_metrics: dict
    history: list[dict] = []


# ── POST /api/chat ─────────────────────────────────────────────────────────────
@router.post("/chat")
async def chat(request: ChatRequest):
    """
    Streams a follow-up LLM response for a question about a property.

    Args:
        question:     User's plain-text question.
        risk_metrics: Risk dict from a previous /api/risk call (used as context).
        history:      Conversation history list of {role, content} dicts.

    Returns:
        StreamingResponse with text/event-stream content type.
        Each chunk is sent as a raw text string (SSE-compatible).
    """
    if not request.question.strip():
        async def empty_gen():
            yield "Please ask a question about the property."
        return StreamingResponse(empty_gen(), media_type="text/event-stream")

    def generate():
        """
        Generator that calls answer_followup() and yields SSE-formatted chunks.
        Each data chunk is prefixed with 'data: ' and terminated with '\n\n'
        to conform to the Server-Sent Events standard.
        """
        try:
            for token in answer_followup(
                question=request.question,
                risk_metrics=request.risk_metrics,
                history=request.history,
            ):
                # Escape any newlines in the token for SSE compliance
                safe_token = token.replace("\n", "\\n")
                yield f"data: {safe_token}\n\n"

            # Signal stream end
            yield "data: [DONE]\n\n"

        except Exception as e:
            logger.error(f"[Chat] Streaming generation error: {e}")
            yield f"data: Error generating response: {str(e)}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # Disable nginx buffering
        },
    )
