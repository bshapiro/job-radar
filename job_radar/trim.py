"""Strip boilerplate from a job description before it is sent for review: equal-opportunity and
accommodation statements, benefits lines, recruiting-scam warnings, privacy notices and similar.
Works line by line, and never drops a line that mentions pay, years of experience or where and how
the job is worked. The stored description is untouched."""
import re

BOILERPLATE = re.compile(
    r"equal (employment )?opportunit|\beeo\b|without regard to|discriminat|reasonable accommodation|"
    r"protected veteran|disability status|e-verify|privacy (policy|notice|statement)|"
    r"recruiters? (will )?(only|never)|scam|phishing|fraudulent|"
    r"criminal histor|fair chance|arrest (and|or) conviction|lie detector|background (check|investigation)|"
    r"our credo|unsolicited (resumes|candidates)|agency (resumes|submissions)|"
    r"parental leave|paid (time off|holidays)|\bpto\b|dental|vision (insurance|coverage|benefits)|"
    r"life insurance|disability insurance|wellness (program|stipend)|commuter benefit|fertility|"
    r"employee (resource|network) groups?|award-winning|best places? to work|"
    r"candidates' ai usage|california resident|pay transparency (act|nondiscrimination)",
    re.I)

# Lines with these are kept even if they also look like boilerplate.
KEEP = re.compile(
    r"\$\s?\d|salary|base pay|compensation range|\b\d+\+? ?(\+|–|-|to)? ?\d*\+? ?years|years of|"
    r"hybrid|remote|on-?site|in[- ]office|days (a|per) week|located|location|relocat|#li-", re.I)


def trim(text):
    kept = [line for line in text.split("\n")
            if not BOILERPLATE.search(line) or KEEP.search(line)]
    return re.sub(r"\n\s*\n+", "\n\n", "\n".join(kept)).strip()
