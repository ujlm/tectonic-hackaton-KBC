"""Registry of the third-party services in KBC Mobile (all integrations are simulated).

Each service lists the features it contributes to the models (`signals`) and the actions Kate can
prepare. Parameter defaults starting with "@" are filled from the customer's context (see mock.py).
Every action is prepared first and only executed after the customer taps to confirm.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Param:
    name: str
    type: str  # string | int | number | date | enum | plate
    default: object = None
    options: tuple = ()
    min: float | None = None
    max: float | None = None
    label: str = ""
    required: bool = True


@dataclass(frozen=True)
class Action:
    id: str
    name: str
    params: tuple = ()
    costs_money: bool = False
    sends: bool = False
    confirm: str = ""  # template shown on the confirmation card
    result: str = ""   # kind of mock confirmation object
    button: str = ""   # label of the confirm button (defaults by flags)


@dataclass(frozen=True)
class Service:
    id: str
    name: str
    category: str
    description: str
    color: str
    text: str = "#ffffff"
    signals: tuple = ()
    actions: tuple = field(default_factory=tuple)

    def action(self, action_id: str) -> Action | None:
        return next((a for a in self.actions if a.id == action_id), None)


P = Param
TODAY = "2026-10-01"

SERVICES: dict[str, Service] = {s.id: s for s in [
    # --- Mobility ---------------------------------------------------------------------------------
    Service("4411", "4411", "Mobility", "Pay for street parking by the minute in 300+ Belgian municipalities.",
            "#E4003A", signals=("parking_sessions_90d", "parking_city_changed_90d"), actions=(
                Action("start_parking", "Start a parking session",
                       (P("city", "string", "@city", label="City"), P("duration_min", "int", 60, min=15, max=600, label="Duration (minutes)"),
                        P("plate", "plate", "@plate", label="Number plate")),
                       costs_money=True, confirm="Start parking in {city} for {duration} with {plate}. You pay per minute.",
                       result="parking_session", button="Start parking"),
                Action("stop_parking", "Stop the running parking session", (P("session_id", "string", "@last_parking", label="Session"),),
                       confirm="Stop parking session {session_id}.", result="parking_stopped", button="Stop parking"),
            )),
    Service("qpark", "Q-Park", "Mobility", "Drive in and out of Q-Park car parks; parking is charged to your account.",
            "#FFD200", "#1a1a1a", actions=(
                Action("link_plate", "Link your number plate", (P("plate", "plate", "@plate", label="Number plate"),),
                       costs_money=True, confirm="Link {plate} to Q-Park. Barriers open automatically; each visit is charged to your KBC account.",
                       result="link", button="Link plate"),
            )),
    Service("sncb", "SNCB / NMBS", "Mobility", "Train tickets, 10-journey cards and commuter passes.",
            "#0069B4", signals=("sncb_tickets_90d", "has_commuter_pass"), actions=(
                Action("buy_ticket", "Buy a train ticket",
                       (P("origin", "string", "@city", label="From"), P("destination", "string", None, label="To"),
                        P("date", "date", TODAY, label="Date"), P("travel_class", "enum", "2nd", options=("2nd", "1st"), label="Class")),
                       costs_money=True, confirm="Train ticket {origin} → {destination} on {date}, {travel_class} class.", result="ticket"),
                Action("buy_multi", "Buy a 10-journey card",
                       (P("origin", "string", "@city", label="From"), P("destination", "string", None, label="To")),
                       costs_money=True, confirm="10-journey card {origin} ↔ {destination}.", result="ticket"),
                Action("buy_commuter_pass", "Buy a commuter pass",
                       (P("origin", "string", "@city", label="From"), P("destination", "string", "@work_city", label="To"),
                        P("months", "enum", 1, options=(1, 3, 12), label="Months")),
                       costs_money=True, confirm="Commuter pass {origin} ↔ {destination} for {months} month(s).", result="ticket"),
            )),
    Service("delijn", "De Lijn", "Mobility", "Bus and tram tickets in Flanders.", "#FFD800", "#1a1a1a", actions=(
        Action("buy_ticket", "Buy a De Lijn ticket", (P("ticket_type", "enum", "single", options=("single", "day pass"), label="Ticket"),),
               costs_money=True, confirm="De Lijn {ticket_type} ticket.", result="ticket"),
    )),
    Service("stib", "STIB-MIVB", "Mobility", "Metro, tram and bus tickets in Brussels.", "#E2001A", actions=(
        Action("buy_ticket", "Buy a STIB-MIVB ticket", (P("ticket_type", "enum", "single", options=("single", "24h"), label="Ticket"),),
               costs_money=True, confirm="STIB-MIVB {ticket_type} ticket.", result="ticket"),
    )),
    Service("shared_bike", "Shared bikes", "Mobility", "Day bikes from Mobit, Blue-bike and Velo Antwerpen.", "#0077C8", actions=(
        Action("rent_day_bike", "Rent a bike for the day",
               (P("provider", "enum", "@bike_provider", options=("Mobit", "Blue-bike", "Velo Antwerpen"), label="Provider"),
                P("city", "string", "@city", label="City")),
               costs_money=True, confirm="Rent a {provider} bike in {city} for 24 hours.", result="booking"),
    )),
    Service("cambio", "Cambio", "Mobility", "Car sharing: book a car by the hour, pay per hour and km.",
            "#F39200", signals=("cambio_bookings_12m",), actions=(
                Action("book_car", "Book a shared car",
                       (P("city", "string", "@city", label="City"), P("date", "date", "2026-10-03", label="Date"),
                        P("hours", "int", 3, min=1, max=72, label="Hours")),
                       costs_money=True, confirm="Book a Cambio car in {city} on {date} for {hours} h.", result="booking"),
                Action("estimate_vs_owning", "Compare Cambio with owning a car",
                       (P("km_per_year", "int", "@km_per_year", min=500, max=60000, label="km per year"),),
                       confirm="Compare the monthly cost of Cambio and of owning a car at {km_per_year} km a year.",
                       result="comparison", button="Show comparison"),
            )),
    Service("q8", "Q8", "Mobility", "Pay for fuel automatically at Q8 stations, recognised by your number plate.",
            "#00539F", signals=("fuel_spend_12m",), actions=(
                Action("link_plate_fuel", "Link your plate for automatic fuel payment", (P("plate", "plate", "@plate", label="Number plate"),),
                       costs_money=True, confirm="Link {plate} to Q8 easy fuelling. Fuel is charged to your KBC account.",
                       result="link", button="Link plate"),
            )),
    Service("movesmart", "Movesmart", "Mobility", "Manage your company lease car.", "#00A19A",
            signals=("has_lease_car_movesmart",), actions=(
                Action("lease_status", "Show your lease car status", (), confirm="Show your Movesmart lease contract.",
                       result="lease_status", button="Show status"),
            )),
    Service("driving_licence", "Driving licence", "Mobility", "Book theory exams and practical driving lessons.",
            "#5B6770", signals=("driving_licence_prep",), actions=(
                Action("book_lesson", "Book a practical driving lesson",
                       (P("date", "date", "2026-10-10", label="Date"), P("hours", "int", 1, min=1, max=2, label="Hours")),
                       costs_money=True, confirm="Practical driving lesson on {date}, {hours} h.", result="booking"),
            )),
    Service("brussels_airport", "Brussels Airport", "Mobility", "Fast Lane and lounge passes.", "#003E7E",
            signals=("airport_passes_12m",), actions=(
                Action("book_fast_lane", "Book a Fast Lane pass", (P("date", "date", "2026-11-14", label="Date"),),
                       costs_money=True, confirm="Fast Lane security pass for {date}.", result="booking"),
                Action("book_lounge", "Book a lounge pass", (P("date", "date", "2026-11-14", label="Date"),),
                       costs_money=True, confirm="Lounge pass for {date}.", result="booking"),
            )),
    # --- Household and payments ------------------------------------------------------------------
    Service("service_vouchers", "Service vouchers", "Household & payments", "Order service vouchers for household help.",
            "#7A3E9D", signals=("service_vouchers_monthly",), actions=(
                Action("order", "Order service vouchers", (P("count", "int", 10, min=1, max=40, label="Vouchers"),),
                       costs_money=True, confirm="Order {count} service vouchers.", result="order"),
            )),
    Service("split_expenses", "Split expenses", "Household & payments", "Share costs with friends and get paid back.",
            "#2BAE66", actions=(
                Action("create_group", "Create a group",
                       (P("name", "string", "Shared costs", label="Group name"), P("members", "string", "2 friends", label="Members")),
                       sends=True, confirm="Create the group '{name}' and invite {members}.", result="group", button="Create & invite"),
                Action("request_repayment", "Request repayment",
                       (P("group", "string", "Shared costs", label="Group"), P("amount", "number", None, min=1, max=10000, label="Amount (€)")),
                       sends=True, confirm="Ask the members of '{group}' to pay back {amount}.", result="payment_request", button="Send request"),
            )),
    Service("wero", "Wero", "Household & payments", "Request and send money to contacts instantly.", "#FFE600", "#1a1a1a", actions=(
        Action("request_money", "Request money from a contact",
               (P("contact", "string", None, label="Contact"), P("amount", "number", None, min=1, max=5000, label="Amount (€)"),
                P("note", "string", "", label="Note", required=False)),
               sends=True, confirm="Ask {contact} for {amount} via Wero{note_suffix}.", result="payment_request", button="Send request"),
    )),
    Service("buffer", "Automatic buffer", "Household & payments",
            "Set money aside on payday; it tops up your current account whenever it would go below zero. A free "
            "account feature, not a product.", "#2E7D6B", actions=(
                Action("start", "Start an automatic buffer",
                       (P("amount", "number", "@suggested_buffer", min=10, max=500, label="Amount per month (€)"),),
                       confirm="Set aside {amount} on payday, every month.", result="buffer"),
                Action("stop", "Stop the automatic buffer", (), confirm="Stop setting money aside.", result="buffer_stopped"),
            )),
    # --- Home ------------------------------------------------------------------------------------
    Service("myhome", "MyHome", "Home", "Estimate your home's value and plan renovations.", "#00AEEF",
            signals=("myhome_valuations_90d",), actions=(
                Action("estimate_value", "Estimate your home's value", (), confirm="Estimate the current value of your home.",
                       result="estimate", button="Show estimate"),
                Action("renovation_checklist", "Renovation checklist and premiums", (),
                       confirm="Open a renovation checklist with the premiums for your region.", result="checklist", button="Open checklist"),
            )),
    # --- Administration -----------------------------------------------------------------------------
    Service("registered_email", "Registered e-mail", "Administration",
            "Send legally valid registered e-mails from templates (only the recipient type is used as a signal, never the content).",
            "#37474F", signals=("registered_email_to_landlord_90d",), actions=(
                Action("send_template", "Send a registered e-mail from a template",
                       (P("template", "enum", "lease_termination", options=("lease_termination", "deposit_return", "repair_request"), label="Template"),
                        P("recipient", "string", "Your landlord", label="Recipient"),
                        P("move_out", "date", "@lease_end_date", label="Move-out date")),
                       costs_money=True, sends=True, confirm="Send the registered e-mail '{template_label}' to {recipient} (move-out {move_out}).",
                       result="registered_email", button="Send registered e-mail"),
            )),
    # --- Self-employed -------------------------------------------------------------------------------
    Service("billit", "Billit", "Self-employed", "Invoicing for the self-employed.", "#1FA2DB",
            signals=("billit_overdue_invoices", "billit_overdue_amount"), actions=(
                Action("list_overdue", "List overdue invoices", (), confirm="Show your overdue invoices in Billit.",
                       result="invoice_list", button="Show invoices"),
                Action("send_reminder", "Send payment reminders", (P("invoice", "string", "all overdue", label="Invoice"),),
                       sends=True, confirm="Send a payment reminder for {invoice} invoices.", result="reminder", button="Send reminders"),
            )),
    Service("gosolid", "Go Solid", "Self-employed", "Amicable collection of unpaid invoices, no cure no pay.", "#5B2D90", actions=(
        Action("start_collection", "Start collection of an unpaid invoice",
               (P("invoice", "string", "@largest_overdue", label="Invoice"), P("amount", "number", "@largest_overdue_amount", label="Amount (€)")),
               costs_money=True, sends=True,
               confirm="Hand invoice {invoice} ({amount}) to Go Solid for amicable collection. Fee: 12% of what is recovered, nothing if not.",
               result="collection", button="Start collection"),
    )),
    Service("expenses", "Expenses", "Self-employed", "Snap receipts and send them to your accountant.", "#8E6C3A", actions=(
        Action("submit_receipts", "Submit receipts to your accountant",
               (P("count", "int", 5, min=1, max=200, label="Receipts"), P("period", "string", "Q3 2026", label="Period")),
               sends=True, confirm="Send {count} receipts for {period} to your accountant.", result="submission", button="Send receipts"),
    )),
    # --- Info -----------------------------------------------------------------------------------------
    Service("financial_news", "Financial news", "Info", "Short articles on markets and personal finance.", "#003665",
            signals=("financial_news_reads_30d",), actions=(
                Action("read_articles", "Read articles",
                       (P("topic", "enum", "Investing basics", options=("Investing basics", "Markets today", "Interest rates"), label="Topic"),),
                       confirm="Open articles about {topic}.", result="articles", button="Open articles"),
            )),
]}

# Services in KBC Mobile that are never used as signals (and never read).
NOT_USED_SERVICES = [
    ("helena", "Helena", "medical data"),
    ("charity", "Charity donations", "donations and the causes you support"),
    ("digital_safe", "Digital safe", "the contents of your digital safe"),
    ("ebox", "eBox", "the contents of your eBox documents"),
]

# Executed actions feed back into the service-usage signals (live, for the current session).
SIGNAL_EFFECTS = {
    ("4411", "start_parking"): ("parking_sessions_90d", "inc", 1),
    ("sncb", "buy_ticket"): ("sncb_tickets_90d", "inc", 1),
    ("sncb", "buy_multi"): ("sncb_tickets_90d", "inc", 1),
    ("sncb", "buy_commuter_pass"): ("has_commuter_pass", "set", True),
    ("cambio", "book_car"): ("cambio_bookings_12m", "inc", 1),
    ("driving_licence", "book_lesson"): ("driving_licence_prep", "set", True),
    ("brussels_airport", "book_fast_lane"): ("airport_passes_12m", "inc", 1),
    ("brussels_airport", "book_lounge"): ("airport_passes_12m", "inc", 1),
    ("myhome", "estimate_value"): ("myhome_valuations_90d", "inc", 1),
    ("registered_email", "send_template"): ("registered_email_to_landlord_90d", "inc", 1),
    ("financial_news", "read_articles"): ("financial_news_reads_30d", "inc", 1),
}

TEMPLATE_LABELS = {"lease_termination": "Termination of the lease", "deposit_return": "Return of the rental guarantee",
                   "repair_request": "Request for repairs"}


def needs_confirmation(a: Action) -> bool:
    """Anything that costs money or sends something needs an explicit tap. (All actions do in this demo:
    Kate only ever prepares them.)"""
    return a.costs_money or a.sends


def catalogue() -> list[dict]:
    """JSON-friendly registry for the UI and for Kate's list_services tool."""
    return [{
        "id": s.id, "name": s.name, "category": s.category, "description": s.description, "color": s.color, "text": s.text,
        "signals": list(s.signals),
        "actions": [{"id": a.id, "name": a.name, "costs_money": a.costs_money, "sends": a.sends,
                     "params": [{"name": p.name, "type": p.type, "default": p.default, "options": list(p.options),
                                 "required": p.required} for p in a.params]} for a in s.actions],
    } for s in SERVICES.values()]
