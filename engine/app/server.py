"""Kate engine API (FastAPI). Private: only the web app's server calls it.

    uvicorn app.server:app --port 8000

Stateless: every request carries the customer's client-held session and gets the updated one back. Customer-facing
text comes in the requested language (en / nl / fr). No LLM is called here: the web app orchestrates Gemini and uses
these endpoints for data and tools. /engine/parse is the offline rule-based fallback for free text.
"""
import os
import random
import secrets
import threading
from contextlib import asynccontextmanager
from functools import lru_cache

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from . import facts, orchestrator, parser
from .assumptions import Engine, ValidationError
from .common import MOMENTS
from .services.registry import NOT_USED_SERVICES, catalogue

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


def require_token(x_engine_token: str | None = Header(default=None)):
    """Optional shared secret (ENGINE_TOKEN) for when the engine is hosted outside the private Vercel binding."""
    expected = os.environ.get("ENGINE_TOKEN")
    if expected and not (x_engine_token and secrets.compare_digest(x_engine_token, expected)):
        raise HTTPException(401, "Missing or wrong engine token")


app = FastAPI(title="Kate engine (synthetic data, simulated integrations)", lifespan=lifespan,
              dependencies=[Depends(require_token)])


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
        out.append({"key": key, "label": label, "moment": moment, "user_id": uid, "first_name": p["first_name"],
                    "age": p["age"], "region": p["region"]})
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
    if not 1 <= user_id <= engine().n_customers:
        raise HTTPException(404, f"No customer {user_id}")
    return user_id


def _call(uid: int, session, fn, with_state: bool = True, lang: str = "en") -> dict:
    """Run fn inside the customer's session; return its result, the new session and (optionally) the state."""
    e = engine()

    def work():
        out = fn()
        return out, (e.state(uid, lang) if with_state else None)

    try:
        (result, state), new_session = e.run(uid, session, work)
    except ValidationError as err:
        raise HTTPException(422, str(err)) from None
    return {"result": result, "session": new_session, **({"state": state} if with_state else {})}


class Req(BaseModel):
    user_id: int
    session: dict | None = None
    lang: str = "en"


class OpIn(Req):
    op: str
    args: dict = Field(default_factory=dict)


class ContextIn(Req):
    depth: str = "simple"
    purpose: str = "opener"
    moment: str | None = None
    event: dict | None = None


class ResolveIn(Req):
    refs: list[str]
    allowed: dict | None = None


class WhatIfIn(Req):
    kind: str
    id: str
    value: float | int | str | bool | None = None


class ParseIn(Req):
    message: str


@app.get("/engine/health")
def health():
    return {"ok": True}


@app.get("/engine/meta")
def meta():
    e = engine()
    return {"auc": e.meta["auc"], "n_customers": e.n_customers, "trained_at": e.meta["trained_at"], "llm": None}


@app.get("/engine/users/random")
def random_user():
    return {"user_id": random.randint(1, engine().n_customers)}


@app.get("/engine/showcase")
def users_showcase():
    return showcase()


@app.get("/engine/scale")
def scale_endpoint():
    return scale()


@app.get("/engine/services")
def services():
    return {"services": catalogue(), "not_used": [{"id": i, "name": n, "what": w} for i, n, w in NOT_USED_SERVICES],
            "simulated": True}


@app.post("/engine/state")
def state(body: Req):
    uid = _uid(body.user_id)
    out = _call(uid, body.session, lambda: None, lang=body.lang)
    return {"state": out["state"], "session": out["session"]}


OPS = {
    "confirm": lambda e, u, a, lang: e.confirm(u, a["feature"]),
    "override": lambda e, u, a, lang: e.override(u, a["feature"], a.get("value"), lang),
    "declare": lambda e, u, a, lang: e.declare(u, a["event"], a.get("month"), lang),
    "prepare_action": lambda e, u, a, lang: e.prepare_action(u, a["service"], a["action"], a.get("params") or {}, lang),
    "confirm_action": lambda e, u, a, lang: e.confirm_action(u, a["action_id"]),
    "cancel_action": lambda e, u, a, lang: e.cancel_action(u, a["action_id"]),
    "ignore": lambda e, u, a, lang: e.ignore_topic(u, a["moment"]),
    "reset": lambda e, u, a, lang: e.reset(u),
}


@app.post("/engine/op")
def op(body: OpIn):
    """One customer action. Service actions are only ever executed by `confirm_action`, i.e. the customer's tap."""
    uid = _uid(body.user_id)
    fn = OPS.get(body.op)
    if fn is None:
        raise HTTPException(400, f"Unknown op '{body.op}'. Ops: {', '.join(OPS)}")
    try:
        return _call(uid, body.session, lambda: fn(engine(), uid, body.args, body.lang), lang=body.lang)
    except KeyError as err:
        raise HTTPException(422, f"Missing argument {err}") from None


@app.post("/engine/context")
def context(body: ContextIn):
    uid = _uid(body.user_id)
    out = _call(uid, body.session, lambda: facts.context(engine(), uid, body.lang, body.depth, body.purpose, body.moment,
                                                          body.event), with_state=False)
    return {"context": out["result"], "session": out["session"]}


@app.post("/engine/resolve")
def resolve(body: ResolveIn):
    uid = _uid(body.user_id)
    out = _call(uid, body.session, lambda: facts.resolve(engine(), uid, body.lang, body.refs[:40], body.allowed),
                with_state=False)
    return {"resolved": out["result"], "session": out["session"]}


@app.post("/engine/whatif")
def whatif(body: WhatIfIn):
    """Live numbers for the what-if slider. The session is not changed (none is returned)."""
    uid = _uid(body.user_id)
    try:
        out = _call(uid, body.session, lambda: facts.whatif(engine(), uid, body.lang, body.kind, body.id, body.value),
                    with_state=False)
    except ValueError as err:
        raise HTTPException(422, str(err)) from None
    return {"whatif": out["result"]}


@app.post("/engine/parse")
def parse(body: ParseIn):
    """Offline fallback for free text (no LLM)."""
    msg = body.message.strip()
    if not msg:
        raise HTTPException(422, "Empty message")
    uid = _uid(body.user_id)
    out = _call(uid, body.session, lambda: parser.reply(engine(), uid, msg[:2000], body.lang), lang=body.lang)
    return {"reply": out["result"], "session": out["session"], "state": out["state"]}
