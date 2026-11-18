"""The rules a new password must pass.

The same rules run on the phone (`PasswordPolicy.swift`) so the form can tick
them off as the user types; this is the copy that decides. Keep the two in
step: a rule added here and not there shows up to the user as a rejection the
form never warned about.

Length, character classes and the repeat and run limits are what Jimmy asked
for on 2026-11-17. The upper bound, the byte limit and the breach check follow
NIST SP 800-63B-4 sec. 3.1.1, which asks for at least 64 characters to be
allowed, for nothing to be truncated, and for a comparison against
known-compromised passwords. NIST itself advises against character-class
rules; they are here by choice.
"""
from __future__ import annotations

import re
from typing import List, Optional

MIN_LENGTH = 12
MAX_LENGTH = 64
# bcrypt reads no further than this, so a longer password would be accepted
# with its tail ignored.
MAX_BYTES = 72
MAX_REPEAT = 2
MAX_RUN = 3
SERVICE_NAME = "livermore"
# A shorter name or email handle appears inside ordinary words by accident.
MIN_PERSONAL_LENGTH = 4

MESSAGES = {
    "length": "Use %d to %d characters." % (MIN_LENGTH, MAX_LENGTH),
    "lowercase": "Add a lowercase letter.",
    "uppercase": "Add an uppercase letter.",
    "number": "Add a number.",
    "symbol": "Add a symbol, such as ! or -.",
    "repeat": "Don't repeat a character three times in a row.",
    "sequence": "Don't use a run of four such as 1234 or abcd.",
    "personal": "Leave out your name, your email and the word Livermore.",
}


def _has_repeat(password: str) -> bool:
    streak = 1
    for previous, current in zip(password, password[1:]):
        streak = streak + 1 if current == previous else 1
        if streak > MAX_REPEAT:
            return True
    return False


def _has_run(password: str) -> bool:
    """Four neighbours in a row, up or down: 1234, dcba, WXYZ."""
    lowered = password.lower()
    streak, direction = 1, 0
    for previous, current in zip(lowered, lowered[1:]):
        step = ord(current) - ord(previous)
        same_kind = (
            previous.isascii() and current.isascii()
            and ((previous.isdigit() and current.isdigit()) or (previous.isalpha() and current.isalpha()))
        )
        if same_kind and step in (1, -1):
            streak = streak + 1 if step == direction else 2
            direction = step
        else:
            streak, direction = 1, 0
        if streak > MAX_RUN:
            return True
    return False


def _personal_words(email: Optional[str], display_name: Optional[str]) -> List[str]:
    words = [SERVICE_NAME]
    if email:
        # "jordan.lee@..." names both the whole handle and each part of it.
        handle = email.split("@", 1)[0]
        words.append(handle)
        words.extend(re.split(r"[^0-9A-Za-z]+", handle))
    if display_name:
        words.extend(display_name.split())
    return [word.lower() for word in words if len(word) >= MIN_PERSONAL_LENGTH]


def violations(
    password: str,
    email: Optional[str] = None,
    display_name: Optional[str] = None,
) -> List[str]:
    """The codes of the rules `password` breaks, in the order they are shown."""
    failed = []
    if not (MIN_LENGTH <= len(password) <= MAX_LENGTH) or len(password.encode("utf-8")) > MAX_BYTES:
        failed.append("length")
    if not any(char.islower() for char in password):
        failed.append("lowercase")
    if not any(char.isupper() for char in password):
        failed.append("uppercase")
    if not any(char in "0123456789" for char in password):
        failed.append("number")
    if not any(not char.isalnum() and not char.isspace() for char in password):
        failed.append("symbol")
    if _has_repeat(password):
        failed.append("repeat")
    if _has_run(password):
        failed.append("sequence")
    lowered = password.lower()
    if any(word in lowered for word in _personal_words(email, display_name)):
        failed.append("personal")
    return failed
