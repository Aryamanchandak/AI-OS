"""Quick test harness for the UPI parser."""
from core.parsers.sms import parse

# Realistic UPI SMS samples, sanitized and in the formats Indian banks actually send.
samples = [
    # HDFC debit
    ("VM-HDFCBK",
     "Sent Rs.450.00 From HDFC Bank A/C x1234 To JOHN DOE On 23-04-26 "
     "Ref 123456789012 Not You? Call 18002586161/SMS BLOCK UPI to 7308080808"),

    # HDFC debit with VPA
    ("VM-HDFCBK",
     "Rs.125.50 debited from a/c XX1234 on 24-04-26 to VPA merchant@okhdfcbank "
     "via UPI. UPI Ref No 234567890123. Not you? call 1800270..."),

    # SBI debit with name + VPA
    ("AX-SBIUPI",
     "Dear UPI user A/C X1234 debited by 500.0 on date 23Apr26 trf to RAMESH KUMAR "
     "VPA ramesh@oksbi Refno 345678901234. If not u? call 1800111109. -SBI"),

    # ICICI debit
    ("VM-ICICIB",
     "ICICI Bank Acct XX123 debited for Rs 1,200.00 on 23-Apr-26; "
     "grocery@paytm credited. UPI:456789012345. Call 18002662 for dispute."),

    # Axis debit
    ("JD-AXISBK",
     "INR 450.00 debited A/c no. XX1234 23-04-26 20:45:12 UPI/P2A/567890123456/"
     "PRIYA SHARMA. Call 18604195555 to report."),

    # Large amount with comma
    ("VM-HDFCBK",
     "Sent Rs.12,500.00 From HDFC Bank A/C x1234 To LANDLORD REALTY On 01-04-26 "
     "Ref 678901234567"),

    # Credit (received money)
    ("VM-HDFCBK",
     "Rs.2,000.00 credited to HDFC Bank A/c XX1234 on 20-04-26 from VPA friend@okaxis "
     "via UPI. UPI Ref No 789012345678."),

    # Kotak
    ("VM-KOTAKB",
     "Sent Rs. 89 from Kotak Bank AC X1234 to tea-stall@ybl on 22-04-26. "
     "UPI Ref: 890123456789. Not you, call 18602662666"),

    # OTP message — should NOT parse
    ("AD-HDFCBK",
     "234567 is your OTP for a transaction of Rs.500 on HDFC NetBanking. "
     "Valid for 10 min. Do not share. -HDFC"),

    # Promotional — should NOT parse
    ("AD-HDFCBK",
     "Dear Customer, get a personal loan up to Rs.40 lakh at attractive rates. "
     "Apply now at hdfcbank.com"),

    # Balance alert — should NOT parse (no UPI keyword)
    ("VM-ICICIB",
     "Dear Customer, your ICICI Bank A/c XX1234 balance is Rs.25,431.50 as on 24-Apr-26."),
]

print(f"{'#':<3} {'Bank':<8} {'Dir':<7} {'Amount':>10}  {'Counterparty':<30}  Parsed?")
print("-" * 90)

for i, (sender, text) in enumerate(samples, 1):
    result = parse(text, sender_id=sender)
    if result is None:
        print(f"{i:<3} {'-':<8} {'-':<7} {'-':>10}  {'(not UPI — correctly skipped)':<30}  SKIP")
        continue
    cp = result.counterparty_vpa or result.counterparty_name or "?"
    amt = f"Rs.{result.amount:,.2f}" if result.amount else "?"
    print(f"{i:<3} {result.bank or '?':<8} {result.direction or '?':<7} "
          f"{amt:>10}  {cp[:30]:<30}  conf={result.confidence:.2f}")
