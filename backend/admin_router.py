"""
admin_router.py  —  Heya AI Voice Analytics
Admin-only endpoints: user management, enhanced client overview.

Endpoints:
    GET    /admin/users              list all platform users
    POST   /admin/users              create a new user
    DELETE /admin/users/{user_id}    delete a user
    GET    /admin/clients/overview   clients with quality + queue + last activity
"""

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func

from sqlalchemy import text as sa_text

from auth import CurrentUser, get_current_user, hash_password
from database import Client, User, Call, AudioInsight, RAGQueryHistory, get_db
from typing import Optional

router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(user: CurrentUser) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")


# ── Models ────────────────────────────────────────────────────────────────────

class CreateUserRequest(BaseModel):
    email:     str
    password:  str
    role:      str            # 'client' | 'heya_admin'
    client_id: Optional[str] = None   # required when role='client'


# ── Users ─────────────────────────────────────────────────────────────────────

@router.get("/users")
def list_users(user: CurrentUser = Depends(get_current_user)):
    _require_admin(user)
    with get_db() as db:
        rows = (
            db.query(User, Client)
            .outerjoin(Client, User.client_id == Client.id)
            .order_by(User.created_at.desc())
            .all()
        )
        return {
            "total": len(rows),
            "users": [
                {
                    "user_id":     u.id,
                    "email":       u.email,
                    "role":        u.role,
                    "client_id":   u.client_id,
                    "client_name": c.name if c else None,
                    "created_at":  str(u.created_at),
                }
                for u, c in rows
            ],
        }


@router.post("/users", status_code=201)
def create_user(
    req:  CreateUserRequest,
    user: CurrentUser = Depends(get_current_user),
):
    _require_admin(user)

    if req.role not in ("client", "heya_admin"):
        raise HTTPException(400, "role must be 'client' or 'heya_admin'")
    if req.role == "client" and not req.client_id:
        raise HTTPException(400, "client_id is required for role='client'")
    if not req.email.strip() or not req.password:
        raise HTTPException(400, "email and password are required")

    with get_db() as db:
        if db.query(User).filter(User.email == req.email).first():
            raise HTTPException(409, f"User with email '{req.email}' already exists")

        if req.client_id:
            if not db.query(Client).filter(Client.id == req.client_id).first():
                raise HTTPException(404, f"Client '{req.client_id}' not found")

        new_user = User(
            id              = str(uuid.uuid4()),
            email           = req.email.strip().lower(),
            hashed_password = hash_password(req.password),
            role            = req.role,
            client_id       = req.client_id or None,
        )
        db.add(new_user)
        created_id    = new_user.id
        created_email = new_user.email

    return {"status": "created", "user_id": created_id, "email": created_email}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    user:    CurrentUser = Depends(get_current_user),
):
    _require_admin(user)
    if user_id == user.user_id:
        raise HTTPException(400, "Cannot delete your own account")

    with get_db() as db:
        target = db.query(User).filter(User.id == user_id).first()
        if not target:
            raise HTTPException(404, "User not found")
        db.delete(target)

    return {"status": "deleted", "user_id": user_id}


# ── Enhanced client overview ──────────────────────────────────────────────────

@router.get("/feed")
def platform_feed(
    limit: int = 50,
    user:  CurrentUser = Depends(get_current_user),
):
    """Recent calls across ALL clients — God View live feed."""
    _require_admin(user)
    limit = max(1, min(limit, 100))

    with get_db() as db:
        rows = db.execute(sa_text("""
            SELECT
                c.id             AS call_id,
                c.client_id,
                cl.name          AS client_name,
                c.direction,
                c.start_timstamp AS start_timestamp,
                c.duration_ms,
                c.processing_status,
                c.call_successful,
                ai.engagement_score,
                ai.conversation_flow,
                ai.dominant_emotion
            FROM calls c
            LEFT JOIN audio_insights ai ON ai.call_id = c.id
            LEFT JOIN clients cl ON cl.id = c.client_id
            ORDER BY c.start_timstamp DESC NULLS LAST, c.id DESC
            LIMIT :lim
        """), {"lim": limit}).fetchall()

    from quality import compute_quality_score, quality_grade

    result = []
    for r in rows:
        qs = qg = None
        if r.engagement_score is not None:
            qs = compute_quality_score(
                float(r.engagement_score), r.conversation_flow,
                r.call_successful, r.dominant_emotion,
            )
            qg = quality_grade(qs)
        result.append({
            "call_id":           r.call_id,
            "client_id":         r.client_id,
            "client_name":       r.client_name,
            "direction":         r.direction,
            "start_timestamp":   r.start_timestamp,
            "duration_ms":       r.duration_ms,
            "processing_status": r.processing_status,
            "call_successful":   r.call_successful,
            "engagement_score":  float(r.engagement_score) if r.engagement_score else None,
            "conversation_flow": r.conversation_flow,
            "dominant_emotion":  r.dominant_emotion,
            "quality_score":     qs,
            "quality_grade":     qg,
        })

    return {"count": len(result), "calls": result}


@router.get("/clients/overview")
def clients_overview(user: CurrentUser = Depends(get_current_user)):
    """
    All clients enriched with:
      - last_call_at      most recent call timestamp
      - pending_queue     calls waiting for audio pipeline
      - avg_quality       platform quality score average
    """
    _require_admin(user)

    with get_db() as db:
        clients = db.query(Client).order_by(Client.name).all()

        result = []
        for c in clients:
            total_calls = (
                db.query(func.count(Call.id))
                .filter(Call.client_id == c.id).scalar() or 0
            )
            processed = (
                db.query(func.count(AudioInsight.id))
                .join(Call, AudioInsight.call_id == Call.id)
                .filter(Call.client_id == c.id).scalar() or 0
            )
            successful = (
                db.query(func.count(Call.id))
                .filter(Call.client_id == c.id, Call.call_successful == True)
                .scalar() or 0
            )
            avg_eng = (
                db.query(func.avg(AudioInsight.engagement_score))
                .join(Call, AudioInsight.call_id == Call.id)
                .filter(Call.client_id == c.id).scalar()
            )
            avg_silence = (
                db.query(func.avg(AudioInsight.silence_ratio))
                .join(Call, AudioInsight.call_id == Call.id)
                .filter(Call.client_id == c.id).scalar()
            )
            last_call = (
                db.query(func.max(Call.start_timstamp))
                .filter(Call.client_id == c.id).scalar()
            )
            pending = (
                db.query(func.count(Call.id))
                .filter(Call.client_id == c.id,
                        Call.processing_status == "pending_audio").scalar() or 0
            )
            user_count = (
                db.query(func.count(User.id))
                .filter(User.client_id == c.id).scalar() or 0
            )

            result.append({
                "client_id":       c.id,
                "name":            c.name,
                "folder_name":     c.folder_name,
                "total_calls":     total_calls,
                "processed_calls": processed,
                "pending_queue":   pending,
                "success_rate":    round(successful / (total_calls or 1) * 100, 1),
                "avg_engagement":  round(float(avg_eng), 1) if avg_eng else None,
                "silence_ratio":   round(float(avg_silence), 4) if avg_silence else None,
                "last_call_at":    str(last_call) if last_call else None,
                "user_count":      user_count,
                "created_at":      str(c.created_at),
            })

        total_pending = sum(r["pending_queue"] for r in result)
        total_users   = db.query(func.count(User.id)).scalar() or 0

    return {
        "total_clients": len(result),
        "total_pending": total_pending,
        "total_users":   total_users,
        "clients":       result,
    }


@router.get("/query-analytics")
def query_analytics(
    days:      int           = 30,
    client_id: Optional[str] = None,
    user:      CurrentUser   = Depends(get_current_user),
):
    """RAG query intelligence — volume, routes, top questions, response times."""
    _require_admin(user)
    days = max(1, min(days, 90))

    with get_db() as db:
        params: dict = {"days": days}
        client_filter = "AND rqh.client_id = :cid" if client_id else ""
        if client_id:
            params["cid"] = client_id

        totals = db.execute(sa_text(f"""
            SELECT
                COUNT(*)                                    AS total_queries,
                COUNT(DISTINCT rqh.client_id)               AS active_clients,
                COUNT(DISTINCT rqh.user_id)                 AS unique_users,
                ROUND(AVG(rqh.response_time_ms)::numeric,0) AS avg_response_ms
            FROM rag_query_history rqh
            WHERE rqh.created_at > NOW() - ('{days} days')::interval
            {client_filter}
        """), params).fetchone()

        routes = db.execute(sa_text(f"""
            SELECT COALESCE(query_type,'unknown') AS route, COUNT(*) AS count
            FROM rag_query_history rqh
            WHERE rqh.created_at > NOW() - ('{days} days')::interval
            {client_filter}
            GROUP BY query_type ORDER BY count DESC
        """), params).fetchall()

        daily = db.execute(sa_text(f"""
            SELECT DATE(rqh.created_at) AS day, COUNT(*) AS queries
            FROM rag_query_history rqh
            WHERE rqh.created_at > NOW() - ('{days} days')::interval
            {client_filter}
            GROUP BY DATE(rqh.created_at) ORDER BY day ASC
        """), params).fetchall()

        top_questions = db.execute(sa_text(f"""
            SELECT rqh.query,
                   COUNT(*) AS frequency,
                   ROUND(AVG(rqh.response_time_ms)::numeric,0) AS avg_ms,
                   MAX(rqh.query_type) AS route
            FROM rag_query_history rqh
            WHERE rqh.created_at > NOW() - ('{days} days')::interval
            {client_filter}
            GROUP BY rqh.query
            ORDER BY frequency DESC
            LIMIT 15
        """), params).fetchall()

        per_client = db.execute(sa_text(f"""
            SELECT rqh.client_id,
                   cl.name                                      AS client_name,
                   COUNT(*)                                      AS total_queries,
                   ROUND(AVG(rqh.response_time_ms)::numeric, 0) AS avg_ms,
                   MAX(rqh.created_at)                          AS last_query_at,
                   (SELECT query_type FROM rag_query_history
                    WHERE client_id = rqh.client_id
                    GROUP BY query_type ORDER BY COUNT(*) DESC LIMIT 1) AS top_route
            FROM rag_query_history rqh
            LEFT JOIN clients cl ON cl.id = rqh.client_id
            WHERE rqh.created_at > NOW() - ('{days} days')::interval
            {client_filter}
            GROUP BY rqh.client_id, cl.name
            ORDER BY total_queries DESC
        """), params).fetchall()

    return {
        "days":               days,
        "client_id":          client_id,
        "totals": {
            "total_queries":  int(totals.total_queries  or 0),
            "active_clients": int(totals.active_clients or 0),
            "unique_users":   int(totals.unique_users   or 0),
            "avg_response_ms":int(totals.avg_response_ms or 0),
        },
        "route_distribution": [{"route": r.route, "count": int(r.count)} for r in routes],
        "daily_volume":       [{"day": str(r.day),  "queries": int(r.queries)} for r in daily],
        "top_questions":      [
            {"query": r.query, "frequency": int(r.frequency),
             "avg_ms": int(r.avg_ms or 0), "route": r.route}
            for r in top_questions
        ],
        "per_client":         [
            {
                "client_id":    r.client_id,
                "client_name":  r.client_name or r.client_id,
                "total_queries": int(r.total_queries),
                "avg_ms":       int(r.avg_ms or 0),
                "last_query_at":str(r.last_query_at) if r.last_query_at else None,
                "top_route":    r.top_route,
            }
            for r in per_client
        ],
    }


# ── Platform calls — filterable, full metrics ─────────────────────────────────

@router.get("/calls")
def admin_calls(
    client_id:  Optional[str] = None,
    agent_id:   Optional[str] = None,
    date_from:  Optional[int] = None,   # ms epoch
    date_to:    Optional[int] = None,   # ms epoch
    direction:  Optional[str] = None,
    flow:       Optional[str] = None,
    trajectory: Optional[str] = None,
    sentiment:  Optional[str] = None,
    topic:      Optional[str] = None,
    limit:      int           = 500,
    user:       CurrentUser   = Depends(get_current_user),
):
    """All calls across all clients with full audio metrics + filters."""
    _require_admin(user)
    limit = max(1, min(limit, 2000))

    clauses, params = [], {"limit": limit}

    if client_id:
        clauses.append("c.client_id = :client_id");   params["client_id"]  = client_id
    if agent_id:
        clauses.append("c.agent_id = :agent_id");     params["agent_id"]   = agent_id
    if date_from:
        clauses.append("c.start_timstamp >= :dfrom"); params["dfrom"]      = date_from
    if date_to:
        clauses.append("c.start_timstamp <= :dto");   params["dto"]        = date_to
    if direction:
        clauses.append("c.direction = :direction");   params["direction"]  = direction
    if flow:
        clauses.append("ai.conversation_flow = :flow"); params["flow"]     = flow
    if trajectory:
        clauses.append("ai.sentiment_trajectory = :traj"); params["traj"]  = trajectory
    if sentiment:
        clauses.append("c.user_sentiment = :sentiment"); params["sentiment"] = sentiment.capitalize()
    if topic:
        clauses.append("c.topic = :topic");           params["topic"]      = topic

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    sql = f"""
        SELECT
            c.id                      AS call_id,
            c.client_id,
            cl.name                   AS client_name,
            c.direction,
            c.start_timstamp          AS start_timestamp,
            c.duration_ms,
            c.processing_status,
            c.call_successful,
            c.user_sentiment,
            c.topic,
            ag.id                     AS agent_id,
            ag.persona_name           AS agent_name,
            ag.agent_role,
            ai.engagement_score,
            ai.conversation_flow,
            ai.sentiment_trajectory,
            ai.silence_ratio,
            ai.interruption_count,
            ai.hesitation_count,
            ai.dominant_emotion,
            ai.agent_talk_time_sec,
            ai.customer_talk_time_sec
        FROM calls c
        LEFT JOIN audio_insights ai ON ai.call_id = c.id
        LEFT JOIN clients cl         ON cl.id       = c.client_id
        LEFT JOIN agents ag          ON ag.id       = c.agent_id
        {where}
        ORDER BY c.start_timstamp DESC NULLS LAST, c.id DESC
        LIMIT :limit
    """

    with get_db() as db:
        rows = db.execute(sa_text(sql), params).fetchall()

    from quality import compute_quality_score, quality_grade as qg_fn

    result = []
    for r in rows:
        qs = qgrade = None
        if r.engagement_score is not None:
            qs     = compute_quality_score(float(r.engagement_score), r.conversation_flow, r.call_successful, r.dominant_emotion)
            qgrade = qg_fn(qs)
        result.append({
            "call_id":               r.call_id,
            "client_id":             r.client_id,
            "client_name":           r.client_name,
            "direction":             r.direction,
            "start_timestamp":       r.start_timestamp,
            "duration_ms":           r.duration_ms,
            "processing_status":     r.processing_status,
            "call_successful":       r.call_successful,
            "user_sentiment":        r.user_sentiment,
            "topic":                 r.topic,
            "agent_id":              r.agent_id,
            "agent_name":            r.agent_name,
            "agent_role":            r.agent_role,
            "engagement_score":      float(r.engagement_score)      if r.engagement_score      is not None else None,
            "conversation_flow":     r.conversation_flow,
            "sentiment_trajectory":  r.sentiment_trajectory,
            "silence_ratio":         float(r.silence_ratio)         if r.silence_ratio         is not None else None,
            "interruption_count":    r.interruption_count,
            "hesitation_count":      r.hesitation_count,
            "dominant_emotion":      r.dominant_emotion,
            "agent_talk_time_sec":   float(r.agent_talk_time_sec)   if r.agent_talk_time_sec   is not None else None,
            "customer_talk_time_sec":float(r.customer_talk_time_sec)if r.customer_talk_time_sec is not None else None,
            "quality_score":         qs,
            "quality_grade":         qgrade,
        })

    return {"count": len(result), "calls": result}


# ── Agents list — for admin feed agent-filter dropdown ────────────────────────

@router.get("/agents")
def admin_agents(
    client_id: Optional[str] = None,
    user:      CurrentUser   = Depends(get_current_user),
):
    """Return agents (non-test, named) optionally scoped to a client."""
    _require_admin(user)
    sql = """
        SELECT id, persona_name, agent_role, direction, client_id
        FROM agents
        WHERE agent_role != 'test' AND persona_name IS NOT NULL
    """
    params = {}
    if client_id:
        sql += " AND client_id = :cid"
        params["cid"] = client_id
    sql += " ORDER BY client_id, persona_name"

    with get_db() as db:
        rows = db.execute(sa_text(sql), params).fetchall()

    return {
        "agents": [
            {"id": r.id, "persona_name": r.persona_name,
             "agent_role": r.agent_role, "direction": r.direction, "client_id": r.client_id}
            for r in rows
        ]
    }
