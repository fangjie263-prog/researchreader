"""Configurable rule data for ArticleCleaner."""

NOISE_PATTERNS = [
    r"^we need your help$", r"^subscribe now$", r"^continue reading$",
    r"^advertisement$", r"^back to contents$", r"^return to top$",
    r"^related articles$", r"^read more$", r"^newsletter$", r"^podcast$",
    r"^listen$", r"^follow us$", r"^\.*$", r"^•+$", r"^-+$",
    r"^page\s+[A-Z]?\d+$", r"^[A-Z]\d+$",
]
EMAIL_PATTERN = r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}"
SECTION_HEADING_RULES = {"min_length": 3, "max_length": 80, "max_words": 10}
SECTION_HEADING_EXCLUSIONS = {"politics", "business", "opinion", "to the editor:"}
