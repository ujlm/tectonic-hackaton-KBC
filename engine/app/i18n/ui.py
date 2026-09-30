"""Short customer-facing strings from the engine, in English, Dutch and French."""

TEXT = {
    "en": {
        "emp.employee": "an employee", "emp.self_employed": "self-employed", "emp.retired": "retired",
        "emp.student": "a student",
        "yes": "yes", "no": "no",
        "months.now": "now", "months.ahead": "in {n} ({month})", "months.this_month": "this month",
        "months.ago": "{n} ago ({month})", "years.lt1": "less than a year",
        "income_evidence.employee": "Average of 12 salary credits from {employer}",
        "income_evidence.self_employed": "Average of 12 months of business income",
        "income_evidence.retired": "Average of 12 pension payments",
        "income_evidence.student": "Average of 12 months of student-job income",
        "parking_evidence.changed": "4411 sessions paid in KBC Mobile: most of them in {parking_city}, not in {city} where you live",
        "parking_evidence.home": "4411 parking sessions paid in KBC Mobile, mostly in {parking_city}",
        "nothing_on_file": "Nothing on file",
        "declared.month": "Told by you: {month}", "declared.not_planned": "Told by you: not planned",
        "cohort": "aged {age}, household of {household}, {region}",
        "housing.owner": "owns their home", "housing.tenant": "rents", "housing.with_parents": "lives with their parents",
        "source.transactions": "inferred from transactions", "source.products": "from your products",
        "source.app": "from your app activity", "source.peers": "from similar customers", "source.told": "you told us",
        "source.services": "via your KBC Mobile services",
        "invoice.overdue": "{client} · {number} · {days} days overdue",
    },
    "nl": {
        "emp.employee": "werknemer", "emp.self_employed": "zelfstandige", "emp.retired": "gepensioneerd",
        "emp.student": "student",
        "yes": "ja", "no": "nee",
        "months.now": "nu", "months.ahead": "over {n} ({month})", "months.this_month": "deze maand",
        "months.ago": "{n} geleden ({month})", "years.lt1": "minder dan een jaar",
        "income_evidence.employee": "Gemiddelde van 12 loonstortingen van {employer}",
        "income_evidence.self_employed": "Gemiddelde van 12 maanden bedrijfsinkomsten",
        "income_evidence.retired": "Gemiddelde van 12 pensioenbetalingen",
        "income_evidence.student": "Gemiddelde van 12 maanden inkomsten uit studentenjobs",
        "parking_evidence.changed": "4411-sessies betaald in KBC Mobile: de meeste in {parking_city}, niet in {city} waar je woont",
        "parking_evidence.home": "4411-parkeersessies betaald in KBC Mobile, vooral in {parking_city}",
        "nothing_on_file": "Niets bekend",
        "declared.month": "Door jou gemeld: {month}", "declared.not_planned": "Door jou gemeld: niet gepland",
        "cohort": "{age} jaar, huishouden van {household}, {region}",
        "housing.owner": "eigenaar", "housing.tenant": "huurder", "housing.with_parents": "woont bij de ouders",
        "source.transactions": "afgeleid uit je verrichtingen", "source.products": "uit je producten",
        "source.app": "uit je gebruik van de app", "source.peers": "uit vergelijkbare klanten", "source.told": "door jou gemeld",
        "source.services": "via je diensten in KBC Mobile",
        "invoice.overdue": "{client} · {number} · {days} dagen te laat",
    },
    "fr": {
        "emp.employee": "salarié·e", "emp.self_employed": "indépendant·e", "emp.retired": "retraité·e",
        "emp.student": "étudiant·e",
        "yes": "oui", "no": "non",
        "months.now": "maintenant", "months.ahead": "dans {n} ({month})", "months.this_month": "ce mois-ci",
        "months.ago": "il y a {n} ({month})", "years.lt1": "moins d'un an",
        "income_evidence.employee": "Moyenne de 12 versements de salaire de {employer}",
        "income_evidence.self_employed": "Moyenne de 12 mois de revenus professionnels",
        "income_evidence.retired": "Moyenne de 12 versements de pension",
        "income_evidence.student": "Moyenne de 12 mois de revenus de jobs étudiants",
        "parking_evidence.changed": "Sessions 4411 payées dans KBC Mobile : la plupart à {parking_city}, pas à {city} où vous habitez",
        "parking_evidence.home": "Sessions de stationnement 4411 payées dans KBC Mobile, surtout à {parking_city}",
        "nothing_on_file": "Aucune donnée",
        "declared.month": "Indiqué par vous : {month}", "declared.not_planned": "Indiqué par vous : pas prévu",
        "cohort": "{age} ans, ménage de {household}, {region}",
        "housing.owner": "propriétaire", "housing.tenant": "locataire", "housing.with_parents": "vit chez ses parents",
        "source.transactions": "déduit de vos opérations", "source.products": "d'après vos produits",
        "source.app": "d'après votre utilisation de l'app", "source.peers": "d'après des clients similaires",
        "source.told": "indiqué par vous", "source.services": "via vos services dans KBC Mobile",
        "invoice.overdue": "{client} · {number} · {days} jours de retard",
    },
}

# (one, many) with {n}
PLURALS = {
    "en": {"payment": ("{n} payment", "{n} payments"), "month": ("{n} month", "{n} months"),
           "year": ("{n} year", "{n} years"), "person": ("{n} person", "{n} people")},
    "nl": {"payment": ("{n} betaling", "{n} betalingen"), "month": ("{n} maand", "{n} maanden"),
           "year": ("{n} jaar", "{n} jaar"), "person": ("{n} persoon", "{n} personen")},
    "fr": {"payment": ("{n} paiement", "{n} paiements"), "month": ("{n} mois", "{n} mois"),
           "year": ("{n} an", "{n} ans"), "person": ("{n} personne", "{n} personnes")},
}

REGIONS = {
    "en": {"Flanders": "Flanders", "Wallonia": "Wallonia", "Brussels": "Brussels"},
    "nl": {"Flanders": "Vlaanderen", "Wallonia": "Wallonië", "Brussels": "Brussel"},
    "fr": {"Flanders": "Flandre", "Wallonia": "Wallonie", "Brussels": "Bruxelles"},
}
HOUSEHOLD_BANDS = {
    "en": ["1 person", "2 people", "3–4 people", "5+ people"],
    "nl": ["1 persoon", "2 personen", "3–4 personen", "5+ personen"],
    "fr": ["1 personne", "2 personnes", "3–4 personnes", "5+ personnes"],
}

MOMENTS = {
    "en": {"move_house": "Moving house", "buy_car": "Buying a car", "renovation": "Renovating",
           "start_investing": "Starting to invest", "cash_squeeze": "A tight month", "birth": "A new baby"},
    "nl": {"move_house": "Verhuizen", "buy_car": "Een auto kopen", "renovation": "Verbouwen",
           "start_investing": "Beginnen met beleggen", "cash_squeeze": "Een krappe maand", "birth": "Een baby"},
    "fr": {"move_house": "Déménager", "buy_car": "Acheter une voiture", "renovation": "Rénover",
           "start_investing": "Commencer à investir", "cash_squeeze": "Un mois serré", "birth": "Un bébé"},
}
STAGES = {
    "en": {"exploring": "Exploring", "deciding": "Deciding", "doing": "Doing", "after": "After",
           "forecast": "Forecast", "short": "Short now"},
    "nl": {"exploring": "Verkennen", "deciding": "Beslissen", "doing": "Bezig", "after": "Achteraf",
           "forecast": "Voorspeld", "short": "Nu krap"},
    "fr": {"exploring": "Exploration", "deciding": "Décision", "doing": "En cours", "after": "Après",
           "forecast": "Prévu", "short": "Serré maintenant"},
}
KINDS = {
    "en": {"info": "Free information", "service": "Service", "product": "KBC product", "advisor": "Advisor"},
    "nl": {"info": "Gratis informatie", "service": "Dienst", "product": "KBC-product", "advisor": "Adviseur"},
    "fr": {"info": "Information gratuite", "service": "Service", "product": "Produit KBC", "advisor": "Conseiller"},
}

SIGNALS_NOT_USED = {
    "en": ["Health: payments to hospitals, doctors, pharmacies or health insurers",
           "Pregnancy or births (a birth can only be declared by you)",
           "Religion or donations to religious organisations", "Trade-union membership fees",
           "Ethnicity, nationality or origin", "Political opinions or party donations",
           "Sexual orientation or relationships", "Gender", "Your age, for how Kate talks to you",
           "Security checks on your payments (Guardian): used only to protect you, never for offers"],
    "nl": ["Gezondheid: betalingen aan ziekenhuizen, artsen, apotheken of ziekenfondsen",
           "Zwangerschap of geboortes (een geboorte kan alleen jij melden)",
           "Religie of giften aan religieuze organisaties", "Lidgeld van een vakbond",
           "Etnische afkomst, nationaliteit of herkomst", "Politieke voorkeur of giften aan partijen",
           "Seksuele geaardheid of relaties", "Gender", "Je leeftijd, voor hoe Kate met je praat",
           "Veiligheidscontroles op je betalingen (Guardian): alleen om je te beschermen, nooit voor aanbiedingen"],
    "fr": ["Santé : paiements aux hôpitaux, médecins, pharmacies ou mutuelles",
           "Grossesse ou naissances (seul·e vous pouvez déclarer une naissance)",
           "Religion ou dons à des organisations religieuses", "Cotisations syndicales",
           "Origine ethnique, nationalité ou origine", "Opinions politiques ou dons à des partis",
           "Orientation sexuelle ou relations", "Genre", "Votre âge, pour la manière dont Kate vous parle",
           "Contrôles de sécurité de vos paiements (Guardian) : uniquement pour vous protéger, jamais pour des offres"],
}
NOT_USED_SERVICE = {
    "en": "{name} ({what}): available in KBC Mobile, never used as a signal",
    "nl": "{name} ({what}): beschikbaar in KBC Mobile, nooit gebruikt als signaal",
    "fr": "{name} ({what}) : disponible dans KBC Mobile, jamais utilisé comme signal",
}
NOT_USED_WHAT = {
    "nl": {"helena": "medische gegevens", "charity": "giften en de doelen die je steunt",
           "digital_safe": "de inhoud van je digitale kluis", "ebox": "de inhoud van je eBox-documenten"},
    "fr": {"helena": "données médicales", "charity": "vos dons et les causes que vous soutenez",
           "digital_safe": "le contenu de votre coffre-fort numérique", "ebox": "le contenu de vos documents eBox"},
}
