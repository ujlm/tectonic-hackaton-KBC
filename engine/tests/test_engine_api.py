"""The engine API: client-held sessions, languages, context packs, reference resolution and the offline parser.

Needs the generated bank and trained models (python -m app.generate && python -m app.train).
"""
import pytest

from app.common import DB_PATH, MODELS_DIR

pytestmark = pytest.mark.skipif(not (DB_PATH.exists() and (MODELS_DIR / "meta.json").exists()),
                                reason="generate and train first")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app import server
    return TestClient(server.app)


@pytest.fixture(scope="module")
def showcase(client):
    return {s["key"]: s["user_id"] for s in client.get("/engine/showcase").json()}


def post(client, path, **body):
    r = client.post(path, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_state_speaks_three_languages(client, showcase):
    uid = showcase["billit_overdue"]
    texts = {lang: post(client, "/engine/state", user_id=uid, lang=lang)["state"] for lang in ("en", "nl", "fr")}
    assert texts["nl"]["forecast"]["summary"] != texts["en"]["forecast"]["summary"]
    assert "€ " in texts["nl"]["forecast"]["summary"]          # € 3.200
    assert " €" in texts["fr"]["forecast"]["summary"]          # 3 200 €
    assert texts["fr"]["signals_not_used"][0].startswith("Santé")


def test_session_round_trip_and_isolation(client, showcase):
    uid, other = showcase["renovation"], showcase["driving_licence"]
    out = post(client, "/engine/op", user_id=uid, op="override", args={"feature": "diy_building_spend_3m", "value": 0})
    sess = out["session"]
    assert sess["user_id"] == uid and sess["overrides"]["diy_building_spend_3m"] == 0
    again = post(client, "/engine/state", user_id=uid, session=sess)["state"]
    assert any(o["feature"] == "diy_building_spend_3m" for o in again["overrides"])
    # A session for someone else is ignored, and nothing leaks between requests.
    assert post(client, "/engine/state", user_id=other, session=sess)["state"]["overrides"] == []
    assert post(client, "/engine/state", user_id=uid)["state"]["overrides"] == []


def test_tampered_session_values_are_revalidated(client, showcase):
    uid = showcase["renovation"]
    sess = {"v": 1, "user_id": uid, "overrides": {"net_income_monthly": 10_000_000, "age": 12},
            "plans": {"buffer_monthly": 99999}}
    st = post(client, "/engine/state", user_id=uid, session=sess)
    assert st["session"]["overrides"] == {} and st["session"]["plans"] == {}


def test_actions_are_prepared_then_only_executed_by_confirm(client, showcase):
    uid = showcase["billit_overdue"]
    prep = post(client, "/engine/op", user_id=uid, op="prepare_action", args={"service": "buffer", "action": "start"})
    card = prep["result"]["card"]
    assert card["status"] == "prepared" and prep["session"]["plans"] == {}
    done = post(client, "/engine/op", user_id=uid, session=prep["session"], op="confirm_action",
                args={"action_id": card["id"]})
    assert done["result"]["card"]["status"] == "done"
    assert done["session"]["plans"]["buffer_monthly"] == card["params"]["amount"]
    assert done["state"]["forecast"]["buffer"]["monthly"] == card["params"]["amount"]


def test_preparing_again_never_piles_up_drafts(client, showcase):
    uid = showcase["billit_overdue"]
    prep = lambda sess, service, action, params: post(  # noqa: E731
        client, "/engine/op", user_id=uid, session=sess, op="prepare_action",
        args={"service": service, "action": action, "params": params})
    first = prep(None, "buffer", "start", {"amount": 300})
    second = prep(first["session"], "buffer", "start", {"amount": 110})
    same = prep(second["session"], "billit", "send_reminder", {})
    again = prep(same["session"], "billit", "send_reminder", {})
    assert again["result"]["card"]["id"] == same["result"]["card"]["id"]
    pending = [(a["service"], a["params"].get("amount")) for a in again["state"]["actions"] if a["status"] == "prepared"]
    assert sorted(pending, key=str) == sorted([("buffer", 110), ("billit", None)], key=str)


def test_context_pack_has_ids_and_allowed_lists(client, showcase):
    uid = showcase["billit_overdue"]
    ctx = post(client, "/engine/context", user_id=uid, lang="en")["context"]
    ids = {f["id"] for f in ctx["facts"]}
    assert {"customer.first_name", "topic.chance", "forecast.tightest_month", "buffer.suggested"} <= ids
    assert "topic.chance_pct" not in ids, "simple depth has no percentages"
    assert ctx["allowed"]["forecast"] and "buffer.start" in ctx["allowed"]["services"]
    detailed = post(client, "/engine/context", user_id=uid, lang="en", depth="detailed")["context"]
    assert "topic.chance_pct" in {f["id"] for f in detailed["facts"]}


def test_resolve_drops_unknown_and_disallowed_refs(client, showcase):
    uid = showcase["driving_licence"]  # buying a car at the exploring stage
    ctx = post(client, "/engine/context", user_id=uid, lang="en", moment="buy_car")["context"]
    assert ctx["topic"]["stage"] == "exploring" and ctx["allowed"]["products"] == []
    res = post(client, "/engine/resolve", user_id=uid, refs=["product:car_loan", "peers:buy_car", "nonsense", "forecast"],
               allowed=ctx["allowed"])["resolved"]
    assert res["product:car_loan"] is None, "no product before the deciding stage"
    assert res["nonsense"] is None and res["forecast"] is None
    assert res["peers:buy_car"]["you"].startswith("about")


def test_whatif_leaves_the_session_alone(client, showcase):
    uid = showcase["volatile_income"]
    w = post(client, "/engine/whatif", user_id=uid, kind="feature", id="income_volatility", value=0.05)
    assert "session" not in w and any(d["moment"] == "cash_squeeze" for d in w["whatif"]["diff"])
    assert post(client, "/engine/state", user_id=uid)["state"]["overrides"] == []


def test_offline_parser_answers_in_the_customers_language(client, showcase):
    uid = showcase["volatile_income"]
    out = post(client, "/engine/parse", user_id=uid, lang="en", message="J'ai maintenant un CDI, mon revenu est stable")
    assert out["reply"]["lang"] == "fr" and out["reply"]["reply"].startswith("Mis à jour")
    assert out["session"]["overrides"]["income_volatility"] == 0.05


def test_opener_is_at_most_one_in_app_topic(client, showcase):
    st = post(client, "/engine/state", user_id=showcase["billit_overdue"])["state"]
    assert st["opener"]["moment"] == "cash_squeeze"
    assert all(c["channel"] == "in-app" for c in st["kate"]["passed"])
