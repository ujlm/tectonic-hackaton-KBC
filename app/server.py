"""Milestone 4: API (plus the Kate action layer with simulated KBC Mobile service integrations).

    uvicorn app.server:app --reload
"""
import os
import random
import threading
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

import numpy as np
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import orchestrator
from .assumptions import Engine, ValidationError
from .chat import DEFAULT_MODEL, chat
from .common import MOMENTS
from .services.registry import NOT_USED_SERVICES, catalogue

STATIC = Path(__file__).parent / "static"
_engine_lock = threading.Lock()


@lru_cache(maxsize=1)
def _engine() -> Engine:
    return Engine()


def engine() -> Engine:
    with _engine_lock:
        return _engine()


@asynccontextmanager
async def lifespan(_app):
    threading.Thread(target=lambda: (showcase(), scale()), daemon=True).start()  # warm models, showcase picks, scale view
    yield


app = FastAPI(title="Explainable prediction assumptions · Kate (synthetic data, simulated integrations)", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC), name="static")


# Each showcase: candidates from SQL, then the one where `feature` pushes `moment` up the most.
SHOWCASE = [
    ("renovation", "Renovation signal", "renovation", "diy_building_spend_3m", """
        SELECT s.user_id FROM scores s JOIN features f USING (user_id) JOIN profiles p USING (user_id)
        WHERE p.owns_home AND f.diy_building_spend_3m > 1500 AND s.p_cash_squeeze < 0.3
        ORDER BY s.p_renovation DESC LIMIT 300"""),
    ("volatile_income", "Volatile income", "cash_squeeze", "income_volatility", """
        SELECT s.user_id FROM scores s JOIN features f USING (user_id) JOIN profiles p USING (user_id)
        WHERE f.income_volatility > 0.3 AND p.employment_type = 'self_employed' AND f.days_negative_12m <= 10
          AND f.diy_building_spend_3m < 300 AND f.billit_overdue_invoices IS NULL AND s.p_renovation < 0.2
        ORDER BY s.p_cash_squeeze DESC LIMIT 300"""),
    ("retired_deposit", "Retired, deposit maturing", "start_investing", "term_deposit_maturity_months", """
        SELECT s.user_id FROM scores s JOIN features f USING (user_id) JOIN profiles p USING (user_id)
        WHERE p.employment_type = 'retired' AND f.term_deposit_maturity_months <= 2 AND s.p_start_investing >= 0.4
        ORDER BY s.p_start_investing DESC LIMIT 300"""),
    ("driving_licence", "Young driver, no car yet", "buy_car", "driving_licence_prep", """
        SELECT s.user_id FROM scores s JOIN features f USING (user_id) JOIN profiles p USING (user_id)
        WHERE p.age <= 26 AND f.driving_licence_prep AND NOT f.has_car AND s.p_buy_car BETWEEN 0.10 AND 0.29
        ORDER BY s.p_buy_car DESC LIMIT 300"""),
    ("landlord_email", "Renter moving out", "move_house", "registered_email_to_landlord_90d", """
        SELECT s.user_id FROM scores s JOIN features f USING (user_id) JOIN profiles p USING (user_id)
        WHERE p.renting AND f.registered_email_to_landlord_90d >= 1 AND f.parking_city_changed_90d
          AND p.employment_type = 'employee' AND s.p_move_house >= 0.45 AND s.p_cash_squeeze < 0.4
        ORDER BY s.p_move_house DESC LIMIT 300"""),
    ("billit_overdue", "Self-employed, unpaid invoices", "cash_squeeze", "billit_overdue_invoices", """
        SELECT s.user_id FROM scores s JOIN features f USING (user_id) JOIN profiles p USING (user_id)
        WHERE p.employment_type = 'self_employed' AND f.billit_overdue_invoices >= 2 AND f.billit_overdue_amount >= 3000
          AND f.days_negative_12m < 15 AND s.p_cash_squeeze BETWEEN 0.3 AND 0.85 AND s.p_renovation < 0.2
        ORDER BY s.p_cash_squeeze DESC LIMIT 300"""),
]

_showcase_lock = threading.Lock()


@lru_cache(maxsize=1)
def _showcase() -> list[dict]:
    e = engine()
    out = []
    for key, label, moment, feature, sql in SHOWCASE:
        with e.lock:
            ids = [int(r[0]) for r in e.con.cursor().execute(sql).fetchall()]
        if not ids:
            continue
        uid = ids[int(np.argmax(e.contribution_pts(ids, moment, feature)))]
        p = e.base(uid)["profile"]
        out.append({"key": key, "label": label, "user_id": uid, "first_name": p["first_name"], "age": p["age"]})
    return out


def showcase() -> list[dict]:
    with _showcase_lock:
        return _showcase()


_scale_lock = threading.Lock()


@lru_cache(maxsize=1)
def _scale() -> dict:
    e = engine()
    with e.lock:
        df = e.con.cursor().execute("""
            SELECT p.*, f.* EXCLUDE (user_id), s.* EXCLUDE (user_id)
            FROM profiles p JOIN features f USING (user_id) JOIN scores s USING (user_id)
            USING SAMPLE reservoir(5000 ROWS) REPEATABLE (7)""").fetchdf()
    rows = []
    for r in df.to_dict("records"):
        r = {k: (None if isinstance(x, float) and x != x else x) for k, x in r.items()}
        rows.append({"values": r, "profile": r, "probs": {m: float(r[f"p_{m}"]) for m in MOMENTS}})
    return orchestrator.scale_view(rows)


def scale() -> dict:
    with _scale_lock:
        return _scale()


def _uid(user_id: int) -> int:
    e = engine()
    if not 1 <= user_id <= e.n_customers:
        raise HTTPException(404, f"No customer {user_id}")
    return user_id


def _guard(fn, *args):
    try:
        return fn(*args)
    except ValidationError as err:
        raise HTTPException(422, str(err)) from None


class OverrideIn(BaseModel):
    feature: str
    value: object = None


class ConfirmIn(BaseModel):
    feature: str


class DeclareIn(BaseModel):
    event: str
    month: str | None = None


class ActionIn(BaseModel):
    service: str
    action: str
    params: dict = {}


class IgnoreIn(BaseModel):
    moment: str


class ChatIn(BaseModel):
    user_id: int
    message: str
    history: list[dict] = []


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.get("/api/meta")
def meta():
    e = engine()
    has_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    return {"chat_mode": "claude" if has_key else "offline",
            "model": (os.environ.get("ANTHROPIC_MODEL") or DEFAULT_MODEL) if has_key else None,
            "auc": e.meta["auc"], "n_customers": e.n_customers, "trained_at": e.meta["trained_at"]}


@app.get("/api/users/random")
def random_user():
    uid = random.randint(1, engine().n_customers)
    return engine().state(uid)


@app.get("/api/users/showcase")
def users_showcase():
    return showcase()


@app.get("/api/users/{user_id}")
def get_user(user_id: int):
    return engine().state(_uid(user_id))


@app.post("/api/users/{user_id}/override")
def override(user_id: int, body: OverrideIn):
    return _guard(engine().override, _uid(user_id), body.feature, body.value)


@app.post("/api/users/{user_id}/confirm")
def confirm(user_id: int, body: ConfirmIn):
    return _guard(engine().confirm, _uid(user_id), body.feature)


@app.post("/api/users/{user_id}/declare")
def declare(user_id: int, body: DeclareIn):
    return _guard(engine().declare, _uid(user_id), body.event, body.month)


@app.post("/api/users/{user_id}/reset")
def reset(user_id: int):
    return engine().reset(_uid(user_id))


# --- Kate action layer (simulated integrations) ------------------------------------------------------
@app.get("/api/services")
def services():
    logo_dir = STATIC / "logos"
    logos = {p.stem: f"/static/logos/{p.name}" for p in logo_dir.glob("*")
             if p.suffix in (".svg", ".png", ".jpg", ".webp")} if logo_dir.is_dir() else {}
    return {"services": [{**s, "logo": logos.get(s["id"])} for s in catalogue()],
            "not_used": [{"id": i, "name": n, "what": w} for i, n, w in NOT_USED_SERVICES], "simulated": True}


@app.post("/api/users/{user_id}/actions")
def prepare_action(user_id: int, body: ActionIn):
    """Prepares a confirmation card. Nothing is executed."""
    return _guard(engine().prepare_action, _uid(user_id), body.service, body.action, body.params)


@app.post("/api/users/{user_id}/actions/{action_id}/confirm")
def confirm_action(user_id: int, action_id: str):
    """Executes a prepared (simulated) action. Called only from the customer's tap in the UI."""
    return _guard(engine().confirm_action, _uid(user_id), action_id)


@app.post("/api/users/{user_id}/actions/{action_id}/cancel")
def cancel_action(user_id: int, action_id: str):
    return _guard(engine().cancel_action, _uid(user_id), action_id)


@app.post("/api/users/{user_id}/ignore")
def ignore(user_id: int, body: IgnoreIn):
    return _guard(engine().ignore_topic, _uid(user_id), body.moment)


@app.get("/api/scale")
def scale_endpoint():
    return scale()


@app.post("/api/chat")
def chat_endpoint(body: ChatIn):
    msg = body.message.strip()
    if not msg:
        raise HTTPException(422, "Empty message")
    return chat(engine(), _uid(body.user_id), msg[:2000], body.history)
