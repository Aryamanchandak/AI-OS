"""
Core configuration: thresholds, category list, merchant patterns.

Every magic number in core lives here. Module-level constants only.
"""

from pathlib import Path

# --- Paths -------------------------------------------------------------------

DATA_DIR = Path.home() / ".upi-agent"
DB_PATH = DATA_DIR / "data.db"
STORIES_DIR = DATA_DIR / "stories"
LOG_PATH = Path("/tmp/upi-agent.log")


# --- Categories --------------------------------------------------------------

CATEGORIES = [
    "Food", "Groceries", "Travel", "Transport", "Shopping",
    "Bills", "Rent", "Entertainment", "Health", "Personal",
    "Transfer", "Other",
]


# --- Classifier (auto ensemble) ----------------------------------------------

CONFIDENCE_THRESHOLD = 0.6

HISTORY_VPA_WEIGHT     = 0.9
HISTORY_VPA_MIN_HITS   = 3
HISTORY_TOKEN_WEIGHT   = 0.5
CALENDAR_WEIGHT        = 0.6
MERCHANT_WEIGHT        = 0.7
HEURISTIC_WEIGHT       = 0.3

# Heuristic classifier thresholds (formerly hardcoded in brain/classifier.py)
CLASSIFIER_MORNING_HOUR_START = 7
CLASSIFIER_MORNING_HOUR_END   = 11
CLASSIFIER_SMALL_AMOUNT_MIN   = 50
CLASSIFIER_SMALL_AMOUNT_MAX   = 400
CLASSIFIER_LARGE_AMOUNT_1     = 5_000
CLASSIFIER_LARGE_AMOUNT_2     = 10_000
CLASSIFIER_ROUND_AMOUNT_MOD   = 100

# Merchant pattern → category. Lowercased substring match against
# (counterparty_name + " " + counterparty_vpa). First match wins.
MERCHANT_PATTERNS = [
    # Food delivery
    ("swiggy", "Food"), ("zomato", "Food"), ("eatsure", "Food"),
    ("rebel foods", "Food"), ("faasos", "Food"), ("box8", "Food"),
    ("freshmenu", "Food"),
    # Quick commerce / groceries
    ("blinkit", "Groceries"), ("zepto", "Groceries"),
    ("instamart", "Groceries"), ("bigbasket", "Groceries"),
    ("dmart", "Groceries"), ("grofers", "Groceries"),
    ("jiomart", "Groceries"),
    # Travel
    ("irctc", "Travel"), ("ixigo", "Travel"),
    ("makemytrip", "Travel"), ("goibibo", "Travel"),
    ("redbus", "Travel"), ("cleartrip", "Travel"),
    ("yatra", "Travel"), ("airbnb", "Travel"), ("oyo", "Travel"),
    # Transport
    ("uber", "Transport"), ("ola", "Transport"),
    ("rapido", "Transport"), ("indrive", "Transport"),
    ("namma yatri", "Transport"),
    # Entertainment / subscriptions
    ("netflix", "Entertainment"), ("spotify", "Entertainment"),
    ("primevideo", "Entertainment"), ("hotstar", "Entertainment"),
    ("jiocinema", "Entertainment"), ("bookmyshow", "Entertainment"),
    ("pvr", "Entertainment"), ("inox", "Entertainment"),
    # Bills / utilities
    ("electricity", "Bills"), ("airtel", "Bills"),
    ("jio postpaid", "Bills"), ("vodafone", "Bills"),
    ("vi postpaid", "Bills"), ("tata power", "Bills"),
    ("mahanagar gas", "Bills"), ("bescom", "Bills"),
    ("adani electric", "Bills"),
    # Health
    ("apollo", "Health"), ("1mg", "Health"),
    ("pharmeasy", "Health"), ("netmeds", "Health"),
    ("practo", "Health"), ("cult.fit", "Health"),
    ("cultfit", "Health"),
    # Shopping
    ("amazon", "Shopping"), ("flipkart", "Shopping"),
    ("myntra", "Shopping"), ("ajio", "Shopping"),
    ("nykaa", "Shopping"), ("meesho", "Shopping"),
]


# Calendar keyword → category.
CALENDAR_KEYWORDS = [
    ("lunch|dinner|breakfast|brunch|cafe|coffee|restaurant|meal", "Food"),
    ("uber|taxi|cab|airport|flight|train|trip",                   "Travel"),
    ("doctor|dentist|hospital|appointment|gym|yoga|workout",      "Health"),
    ("movie|concert|show|gig|theatre|theater",                    "Entertainment"),
    ("groceries|shopping|errands|market",                         "Shopping"),
]


# Tokens too generic to learn from in name_token rules.
NAME_STOP_TOKENS = {
    "pvt", "ltd", "limited", "private", "llp", "inc", "co", "company",
    "store", "stores", "shop", "the", "and", "of", "for", "by",
    "mr", "mrs", "ms", "dr",
}


# --- Classifier (manual / tax UI) -------------------------------------------

# At or above: classify silently after ingest (no triage needed).
CONFIDENCE_AUTO_APPLY = 0.85
# Below: don't show a suggestion in the triage UI.
CONFIDENCE_TRIAGE = 0.40


# --- Anomaly detection -------------------------------------------------------

NEW_COUNTERPARTY_THRESHOLD = 3_000

Z_THRESHOLD       = 2.5
Z_HIGH_THRESHOLD  = 3.5
Z_MIN_HISTORY     = 10
Z_LOOKBACK_DAYS   = 60

ODD_HOUR_PERCENTILES   = (5, 95)
ODD_HOUR_MIN_AMOUNT    = 500
ODD_HOUR_MIN_HISTORY   = 30

VELOCITY_COUNT      = 5
VELOCITY_WINDOW_MIN = 10


# --- Recurring payment detector ----------------------------------------------

RECURRING_MIN_OCCURRENCES   = 3
RECURRING_CADENCE_TOLERANCE = 4
RECURRING_AMOUNT_TOLERANCE  = 0.10


# --- Goals -------------------------------------------------------------------

DEFAULT_BUDGET_WARN_PCT = 80


# --- Triage queue ------------------------------------------------------------

TRIAGE_CONFIDENCE_THRESHOLD = 0.7


# --- Narrator ----------------------------------------------------------------

# Minimum calendar-correlation gap to call out a spending pattern.
NARRATOR_CALENDAR_CORRELATION_GAP = 0.30


# --- Notifier ----------------------------------------------------------------

# Truncate notification body at this many characters (macOS osascript limit).
NOTIFIER_TRUNCATE_LEN = 240


# --- LLM narrator (optional) -------------------------------------------------

USE_LLM_NARRATOR = False
OPENAI_MODEL = "gpt-4o-mini"
