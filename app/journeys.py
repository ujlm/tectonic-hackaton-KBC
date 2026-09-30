"""Journey stages per key moment, and the help items Kate can offer at each stage.

Stages: exploring -> deciding -> doing -> after (cash squeeze: forecast -> short).
Help items per stage are ordered by preference: free information, a service action, a KBC product
(only from the deciding stage on; for cash squeeze only when short), an advisor handoff.
"""
import math
from dataclasses import dataclass, field
from typing import Callable

from .common import MOMENT_LABELS, MOMENTS

STAGES = {m: ["exploring", "deciding", "doing", "after"] for m in MOMENTS}
STAGES["cash_squeeze"] = ["forecast", "short"]
PRODUCT_FROM = {m: "deciding" for m in MOMENTS} | {"cash_squeeze": "short"}
KIND_ORDER = {"info": 0, "service": 1, "product": 2, "advisor": 3}
KIND_LABELS = {"info": "Free information", "service": "Service action", "product": "KBC product", "advisor": "Advisor"}
STAGE_WEIGHT = {"exploring": 0.6, "deciding": 1.0, "doing": 1.2, "after": 0.8, "forecast": 1.0, "short": 1.3}


class Facts:
    """Read-only view of one customer's values; missing numbers become NaN so comparisons are False."""

    def __init__(self, values: dict, probs: dict, declared: dict):
        self._v, self.p, self._declared = values, probs, declared

    def __getattr__(self, k):
        if k.startswith("_"):
            raise AttributeError(k)
        val = self._v.get(k)
        if val is None:
            return math.nan
        return val.item() if hasattr(val, "item") else val

    def planned(self, moment: str) -> bool:
        return bool(self._declared.get(moment, {}).get("month")) if moment in self._declared else False

    def not_planned(self, moment: str) -> bool:
        return moment in self._declared and not self._declared[moment].get("month")


# ------------------------------------------------------------------------------------------------
# Stage rules: for each moment, the first row that matches (top to bottom) sets the stage.
# ------------------------------------------------------------------------------------------------
STAGE_RULES: list[tuple[str, str, str, Callable[[Facts], bool]]] = [
    # moment            stage        rule, in plain English
    ("move_house",      "after",     "a new 3-year lease or a home purchase in the last 3 months",
     lambda x: (x.lease_end_months >= 34 or x.months_since_home_purchase <= 3) and not x.registered_email_to_landlord_90d >= 1),
    ("move_house",      "doing",     "you told us the month, or you gave notice to your landlord and moving is likely (≥ 40%)",
     lambda x: x.planned("move_house") or (x.registered_email_to_landlord_90d >= 1 and x.p["move_house"] >= 0.40)),
    ("move_house",      "deciding",  "moving is likely (≥ 25%) and you're taking steps: landlord e-mail, MyHome, parking elsewhere, lease ending",
     lambda x: x.p["move_house"] >= 0.25 and (x.registered_email_to_landlord_90d >= 1 or x.myhome_valuations_90d >= 1
                                              or x.parking_city_changed_90d is True or x.lease_end_months <= 6)),
    ("move_house",      "exploring", "moving is plausible (≥ 10%) or your lease ends within 6 months",
     lambda x: x.p["move_house"] >= 0.10 or x.lease_end_months <= 6),

    ("buy_car",         "after",     "you bought your current car in the last 3 months",
     lambda x: x.months_since_car_purchase <= 3),
    ("buy_car",         "doing",     "you told us when you're buying",
     lambda x: x.planned("buy_car")),
    ("buy_car",         "deciding",  "buying a car is likely (≥ 30%)",
     lambda x: x.p["buy_car"] >= 0.30),
    ("buy_car",         "exploring", "buying is plausible (≥ 8%), or you're preparing your driving licence or often use Cambio",
     lambda x: x.p["buy_car"] >= 0.08 or x.driving_licence_prep is True or x.cambio_bookings_12m >= 6),

    ("renovation",      "after",     "a big project earlier this year (≥ €3,000 at building suppliers) that has wound down",
     lambda x: x.diy_building_spend_12m >= 3000 and x.diy_building_spend_3m < 300),
    ("renovation",      "doing",     "works under way (≥ €1,500 at building suppliers since July) or you told us the month",
     lambda x: x.planned("renovation") or x.diy_building_spend_3m >= 1500),
    ("renovation",      "deciding",  "renovating is likely (≥ 25%) and you checked MyHome or bought your home in the last 2 years",
     lambda x: x.p["renovation"] >= 0.25 and (x.myhome_valuations_90d >= 1 or x.months_since_home_purchase <= 24)),
    ("renovation",      "exploring", "renovating is plausible (≥ 8%) or you checked your home's value in MyHome",
     lambda x: x.p["renovation"] >= 0.08 or (x.owns_home is True and x.myhome_valuations_90d >= 1)),

    ("start_investing", "after",     "you already invest and investing is on your mind (≥ 20%)",
     lambda x: x.investments_value > 0 and x.p["start_investing"] >= 0.20),
    ("start_investing", "doing",     "you told us when, or a term deposit matures within 2 months and investing is likely (≥ 40%)",
     lambda x: x.planned("start_investing") or (x.term_deposit_maturity_months <= 2 and x.p["start_investing"] >= 0.40)),
    ("start_investing", "deciding",  "investing is likely (≥ 30%) and you're reading up (≥ 5 Invest page visits or news articles)",
     lambda x: x.p["start_investing"] >= 0.30 and (x.invest_page_views_90d >= 5 or x.financial_news_reads_30d >= 5)),
    ("start_investing", "exploring", "investing is plausible (≥ 8%) or you read financial news regularly (≥ 3 articles a month)",
     lambda x: x.p["start_investing"] >= 0.08 or x.financial_news_reads_30d >= 3),

    ("cash_squeeze",    "short",     "already short: below zero on 15+ days this year and a squeeze is likely (≥ 50%)",
     lambda x: x.days_negative_12m >= 15 and x.p["cash_squeeze"] >= 0.50),
    ("cash_squeeze",    "forecast",  "a dip below zero is forecast in the next 12 months (≥ 25%)",
     lambda x: x.p["cash_squeeze"] >= 0.25),
]


# ------------------------------------------------------------------------------------------------
# Help items
# ------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Help:
    moment: str
    stage: str
    kind: str                       # info | service | product | advisor
    id: str
    title: str                      # may use {placeholders} from fmt_context()
    say: str                        # what Kate would say
    action: tuple | None = None     # (service, action, params)
    depends: tuple = ()             # assumptions the item is built on (suppressed if rejected)
    when: Callable[[Facts], bool] | None = None
    deadline: Callable[[Facts], str | None] | None = None   # -> text if a deadline applies (push)
    critical: Callable[[Facts], str | None] | None = None   # -> text if time-critical (may exceed budget)


def _renting(x): return x.renting is True
def _owner(x): return x.owns_home is True
def _billit(x): return x.billit_overdue_invoices >= 1
def _lease_deadline(x): return f"notice period: lease ends {x.fmt('lease_month')}" if x.lease_end_months <= 4 else None
def _dip(x): return "predicted dip below zero" if x.p["cash_squeeze"] >= 0.5 else None
def _td_deadline(x): return f"term deposit matures {x.fmt('td_month')}" if x.term_deposit_maturity_months <= 2 else None


HELP_ITEMS = [
    # --- Moving house ---
    Help("move_house", "exploring", "info", "move_lease_info", "Your lease ends {lease_month}: know your notice period",
         "Your lease ends {lease_month}. Want a reminder before the notice period starts, and a note on getting your rental guarantee back?",
         depends=("lease_end_months", "renting"), when=_renting, deadline=_lease_deadline),
    Help("move_house", "exploring", "info", "move_guarantee_info", "How your rental guarantee is released",
         "When you move out, your rental guarantee is released once you and your landlord sign off the inspection. Here's how.",
         depends=("renting",), when=_renting),
    Help("move_house", "exploring", "service", "move_myhome_explore", "What is your home worth today?",
         "Thinking about a move? MyHome can estimate what your current home is worth.",
         action=("myhome", "estimate_value", {}), depends=("owns_home",), when=_owner),
    Help("move_house", "deciding", "info", "move_checklist", "Moving checklist: 8 weeks to go",
         "Here's a moving checklist, from giving notice to registering at your new municipality within 8 working days."),
    Help("move_house", "deciding", "service", "move_registered_email", "Registered e-mail to your landlord",
         "Want me to prepare the registered e-mail to your landlord? It's legally valid and I use the standard lease-termination template.",
         action=("registered_email", "send_template", {"template": "lease_termination"}),
         depends=("lease_end_months", "renting"), when=_renting, deadline=_lease_deadline),
    Help("move_house", "deciding", "service", "move_myhome_decide", "Value your home before you sell",
         "Before you decide, MyHome can estimate your home's value.",
         action=("myhome", "estimate_value", {}), depends=("owns_home",), when=_owner),
    Help("move_house", "deciding", "product", "move_home_loan", "Home loan simulation",
         "If you'd rather buy than rent next, I can run a home-loan simulation with you.",
         depends=("savings_balance", "renting"), when=lambda x: _renting(x) and x.savings_balance >= 20000),
    Help("move_house", "deciding", "advisor", "move_advisor", "Talk to a housing advisor", "Want to talk it through with a housing advisor?"),
    Help("move_house", "doing", "info", "move_address_change", "Change your address in one go",
         "Moving soon? Here's how to register at your new address (within 8 working days) and update it in KBC Mobile."),
    Help("move_house", "doing", "service", "move_commuter_pass", "Commuter pass for your new commute",
         "From {new_city} your commute changes. Shall I prepare an SNCB commuter pass {new_city} ↔ {work_city}?",
         action=("sncb", "buy_commuter_pass", {"origin": "@new_city", "destination": "@work_city"}),
         depends=("parking_city_changed_90d",), when=lambda x: x.employment_type in ("employee", "student")),
    Help("move_house", "after", "info", "move_settle_in", "Settling in: your new municipality's services",
         "Welcome to your new home! Here's what to arrange in your first month."),
    Help("move_house", "after", "product", "move_insurance", "Home or tenant insurance for your new address",
         "Is your new home insured? I can compare home or tenant insurance for your new address."),

    # --- Buying a car ---
    Help("buy_car", "exploring", "info", "car_true_cost", "What a car really costs per month",
         "A small car often costs €350–€500 a month once you count depreciation, insurance, tax, fuel and parking."),
    Help("buy_car", "exploring", "service", "car_cambio_compare", "Cambio vs. owning: which is cheaper for you?",
         "Before buying, want me to compare Cambio car sharing with owning a car at your mileage? It might tell you not to buy.",
         action=("cambio", "estimate_vs_owning", {})),
    Help("buy_car", "exploring", "service", "car_driving_lesson", "Book your next practical driving lesson",
         "Preparing for your licence? I can book your next practical lesson.",
         action=("driving_licence", "book_lesson", {}), depends=("driving_licence_prep",), when=lambda x: x.driving_licence_prep is True),
    Help("buy_car", "deciding", "info", "car_checklist", "New or second-hand: a checklist",
         "Here's a checklist for comparing new and second-hand cars, including the real running costs."),
    Help("buy_car", "deciding", "service", "car_cambio_compare_2", "Cambio vs. owning at your mileage",
         "Still worth a check: Cambio versus owning at your mileage.", action=("cambio", "estimate_vs_owning", {}),
         when=lambda x: x.has_car is not True),
    Help("buy_car", "deciding", "product", "car_loan", "Car loan", "I can show you what a car loan would cost per month.",
         depends=("car_repair_12m", "car_age_years")),
    Help("buy_car", "deciding", "product", "car_insurance", "Car insurance quote", "Want a car insurance quote for the model you're considering?"),
    Help("buy_car", "deciding", "advisor", "car_advisor", "Talk to an advisor about financing", "Prefer to discuss financing with an advisor?"),
    Help("buy_car", "doing", "info", "car_paperwork", "Before you drive off: registration and insurance",
         "Buying soon? Your car needs insurance before registration (DIV). Here's the order of steps."),
    Help("buy_car", "doing", "product", "car_loan_doing", "Car loan", "Want to finalise the car loan?"),
    Help("buy_car", "after", "service", "car_q8", "Link your plate to Q8 for automatic fuel payment",
         "New car! Shall I link {plate} to Q8 so you can fuel up without taking out your card?",
         action=("q8", "link_plate_fuel", {})),
    Help("buy_car", "after", "service", "car_qpark", "Link your plate to Q-Park", "And link {plate} to Q-Park so barriers open automatically?",
         action=("qpark", "link_plate", {})),
    Help("buy_car", "after", "product", "car_omnium", "Omnium cover for your new car", "Your new car may be worth covering with an omnium policy."),

    # --- Renovating ---
    Help("renovation", "exploring", "info", "reno_premiums", "Renovation premiums: {premium}",
         "Planning works? In {region} you may be entitled to {premium}. Here's what qualifies."),
    Help("renovation", "exploring", "service", "reno_checklist", "MyHome renovation checklist",
         "Want a MyHome checklist of the works that pay off most, with the premiums for your region?",
         action=("myhome", "renovation_checklist", {})),
    Help("renovation", "deciding", "info", "reno_epc", "Energy performance: which works pay off first",
         "Insulation and glazing usually improve your EPC the most per euro. Here's an overview."),
    Help("renovation", "deciding", "service", "reno_checklist_2", "MyHome renovation checklist",
         "MyHome can list your works and the matching premiums.", action=("myhome", "renovation_checklist", {})),
    Help("renovation", "deciding", "product", "reno_loan", "Energy renovation loan", "An energy renovation loan could spread the cost. Want a simulation?",
         depends=("diy_building_spend_3m", "months_since_home_purchase")),
    Help("renovation", "deciding", "advisor", "reno_advisor", "Talk to a renovation advisor", "Want to plan the budget with an advisor?"),
    Help("renovation", "doing", "info", "reno_invoices", "Keep your invoices for the premium",
         "Works under way? Keep every invoice: you'll need them for {premium}.", depends=("diy_building_spend_3m",)),
    Help("renovation", "doing", "product", "reno_loan_doing", "Energy renovation loan", "Costs higher than planned? An energy renovation loan can help.",
         depends=("diy_building_spend_3m",)),
    Help("renovation", "after", "service", "reno_value", "What did the renovation add?", "Curious what your renovation added? MyHome can re-estimate your home.",
         action=("myhome", "estimate_value", {})),
    Help("renovation", "after", "product", "reno_insurance", "Update your home insurance value",
         "After a renovation, your home insurance value may be too low. Want to update it?"),

    # --- Starting to invest ---
    Help("start_investing", "exploring", "info", "inv_explainer", "Investing explained in 3 minutes",
         "Curious about investing? Here's a 3-minute explainer on risk, return and spreading."),
    Help("start_investing", "exploring", "service", "inv_news", "Financial news: investing basics",
         "Want a few short reads on investing basics?", action=("financial_news", "read_articles", {"topic": "Investing basics"})),
    Help("start_investing", "deciding", "info", "inv_risk", "Risk and return: what to expect",
         "Before you invest, here's what to expect from different risk levels."),
    Help("start_investing", "deciding", "product", "inv_profile", "Your investor profile",
         "Ready to decide? Your investor profile shows which investments suit you.", depends=("invest_page_views_90d",)),
    Help("start_investing", "deciding", "advisor", "inv_advisor", "Talk to an investment advisor", "Prefer to talk it through with an advisor?"),
    Help("start_investing", "doing", "info", "inv_td", "Your term deposit matures {td_month}: what happens next",
         "Your term deposit matures {td_month}. Here are your options: renew, keep it as savings, or invest.",
         depends=("term_deposit_maturity_months",), when=lambda x: x.term_deposit_maturity_months >= 0, deadline=_td_deadline),
    Help("start_investing", "doing", "product", "inv_plan", "KBC Investment Plan", "Want to start a monthly investment plan, from €25 a month?"),
    Help("start_investing", "after", "service", "inv_markets", "Markets today", "Here's today's market news for your portfolio.",
         action=("financial_news", "read_articles", {"topic": "Markets today"})),
    Help("start_investing", "after", "advisor", "inv_checkin", "Portfolio check-in", "Time for a portfolio check-in with an advisor?"),

    # --- Cash squeeze ---
    Help("cash_squeeze", "forecast", "info", "cash_set_aside", "Automatic set-aside on payday",
         "Your balance may dip below zero in the coming months. Want to set aside a small buffer automatically on payday?",
         depends=("min_balance_12m", "income_volatility"), critical=_dip),
    Help("cash_squeeze", "forecast", "service", "cash_billit_reminder", "Send reminders for {overdue_n} overdue invoice(s)",
         "{overdue_n} of your invoices ({overdue_amt}) are overdue in Billit. Shall I prepare payment reminders?",
         action=("billit", "send_reminder", {}), depends=("billit_overdue_invoices",), when=_billit, critical=_dip),
    Help("cash_squeeze", "forecast", "service", "cash_gosolid", "Recover your largest unpaid invoice with Go Solid",
         "Your largest unpaid invoice could go to Go Solid for amicable collection, no cure no pay. Want me to prepare it?",
         action=("gosolid", "start_collection", {}), depends=("billit_overdue_invoices", "billit_overdue_amount"),
         when=lambda x: _billit(x) and x.billit_overdue_amount >= 1500, critical=_dip),
    Help("cash_squeeze", "forecast", "service", "cash_split", "Get back money you advanced",
         "Did you pay for others lately? A Split expenses request gets that money back.", action=("split_expenses", "request_repayment", {}),
         when=lambda x: x.employment_type != "self_employed"),
    Help("cash_squeeze", "forecast", "service", "cash_wero", "Ask a contact to pay you back with Wero",
         "Someone owes you money? I can prepare a Wero request.", action=("wero", "request_money", {})),
    Help("cash_squeeze", "short", "info", "cash_budget", "Where your money goes",
         "Money is tight right now. Here's where it goes each month and which costs you could pause.", critical=_dip),
    Help("cash_squeeze", "short", "service", "cash_gosolid_short", "Recover unpaid invoices with Go Solid",
         "First, let's recover what clients owe you: Go Solid can collect your largest unpaid invoice.",
         action=("gosolid", "start_collection", {}), depends=("billit_overdue_invoices",), when=_billit, critical=_dip),
    Help("cash_squeeze", "short", "service", "cash_wero_short", "Ask a contact to pay you back with Wero",
         "Someone owes you money? I can prepare a Wero request.", action=("wero", "request_money", {})),
    Help("cash_squeeze", "short", "product", "cash_credit", "Short-term credit", "If you still need a bridge, a short-term credit can help."),
    Help("cash_squeeze", "short", "advisor", "cash_advisor", "Talk to a budget advisor", "Want to go through your budget with an advisor?"),
]


def _check_table():
    """Products never come before the stage where they're allowed, and never before free info or service
    actions of the same moment and stage."""
    for h in HELP_ITEMS:
        stages = STAGES[h.moment]
        assert h.stage in stages, h.id
        if h.kind == "product":
            assert stages.index(h.stage) >= stages.index(PRODUCT_FROM[h.moment]), f"{h.id}: product too early"


_check_table()


def stage_of(moment: str, x: Facts) -> tuple[str | None, str]:
    if x.not_planned(moment):
        return None, "you told us it's not planned"
    for m, stage, rule, test in STAGE_RULES:
        if m == moment and test(x):
            return stage, rule
    return None, "no signals yet"


def fmt_context(values: dict, profile: dict, svc_ctx: dict) -> dict:
    from .assumptions import eur, shift_month  # local import: assumptions imports this module

    def month(v):
        return shift_month(v, True) if v is not None and not (isinstance(v, float) and math.isnan(v)) else "soon"

    premium = {"Flanders": "Mijn VerbouwPremie", "Wallonia": "the Primes Habitation", "Brussels": "the Renolution premiums"}
    return {
        "lease_month": month(values.get("lease_end_months")), "td_month": month(values.get("term_deposit_maturity_months")),
        "region": profile["region"], "premium": premium[profile["region"]], "city": profile["city"],
        "new_city": svc_ctx.get("new_city") or profile["city"], "work_city": svc_ctx.get("work_city") or profile["city"],
        "plate": svc_ctx.get("plate", ""), "overdue_n": int(values.get("billit_overdue_invoices") or 0),
        "overdue_amt": eur(values.get("billit_overdue_amount") or 0),
    }


def _format(template: str, ctx: dict) -> str:
    try:
        return template.format(**ctx)
    except (KeyError, ValueError):
        return template


def build(values: dict, probs: dict, declared: dict, profile: dict, svc_ctx: dict) -> list[dict]:
    """Stage and help items for every moment (plus the next stage's items, for the orchestrator)."""
    ctx = fmt_context(values, profile, svc_ctx)
    x = Facts(values, probs, declared)
    x.fmt = lambda k: ctx.get(k, "")  # noqa: used by deadline texts
    out = []
    for m in MOMENTS:
        stage, rule = stage_of(m, x)
        stages = STAGES[m]
        nxt = stages[stages.index(stage) + 1] if stage and stages.index(stage) + 1 < len(stages) else (stages[0] if stage is None else None)

        def items_for(st):
            chosen = [h for h in HELP_ITEMS if h.moment == m and h.stage == st and (h.when is None or h.when(x))]
            chosen.sort(key=lambda h: KIND_ORDER[h.kind])
            return [{
                "id": h.id, "moment": m, "stage": st, "kind": h.kind, "kind_label": KIND_LABELS[h.kind],
                "title": _format(h.title, ctx), "say": _format(h.say, ctx), "depends": list(h.depends),
                "action": {"service": h.action[0], "action": h.action[1], "params": h.action[2]} if h.action else None,
                "deadline": h.deadline(x) if h.deadline else None, "critical": h.critical(x) if h.critical else None,
            } for h in chosen]

        out.append({
            "moment": m, "label": MOMENT_LABELS[m], "stage": stage, "stages": stages, "rule": rule,
            "probability": probs[m], "items": items_for(stage) if stage else [],
            "next_stage": nxt, "next_items": items_for(nxt) if nxt else [],
        })
    return out
