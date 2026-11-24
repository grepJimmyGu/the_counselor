"""The two emails a password reset sends: the code, and the notice afterwards.

Both are transactional: they go out whatever the user's marketing choices
are, and carry no unsubscribe link. Neither links anywhere. The code is
typed into the app or the site the user already has open, so the email works
the same wherever it is read and gives a phishing copy nothing to imitate.
"""
from __future__ import annotations

from typing import Dict

from app.models.user import User
from app.services.password_reset import CODE_LIFETIME

_MINUTES = int(CODE_LIFETIME.total_seconds() // 60)


def _page(body_html: str) -> str:
    return (
        '<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;'
        'font-size:16px;line-height:1.5;color:#111;max-width:480px">'
        f"{body_html}"
        '<p style="color:#666;font-size:13px">Livermore Alpha</p></div>'
    )


def render_reset_code(user: User, code: str) -> Dict[str, str]:
    name = user.display_name or "there"
    text = f"""Hi {name},

Your Livermore password reset code is:

    {code}

Type it into the screen where you asked for it. It works for {_MINUTES} minutes and only once.

If you did not ask for this, ignore this email. Your password has not changed, and nobody can change it without this code.

Livermore Alpha
"""
    html = _page(
        f"<p>Hi {name},</p>"
        "<p>Your Livermore password reset code is:</p>"
        f'<p style="font-size:32px;font-weight:700;letter-spacing:6px;margin:16px 0">{code}</p>'
        f"<p>Type it into the screen where you asked for it. It works for {_MINUTES} minutes and only once.</p>"
        "<p>If you did not ask for this, ignore this email. Your password has not changed, "
        "and nobody can change it without this code.</p>"
    )
    return {"subject": "Your Livermore password reset code", "text": text, "html": html}


def render_password_changed(user: User) -> Dict[str, str]:
    name = user.display_name or "there"
    text = f"""Hi {name},

The password for your Livermore account was just changed, and the Livermore app has been signed out on every device.

If that was you, there is nothing to do.

If it was not, someone has access to this mailbox. Change your email password first, then reset your Livermore password again from the sign-in screen, and reply to this email so we can help.

Livermore Alpha
"""
    html = _page(
        f"<p>Hi {name},</p>"
        "<p>The password for your Livermore account was just changed, and the Livermore app "
        "has been signed out on every device.</p>"
        "<p>If that was you, there is nothing to do.</p>"
        "<p>If it was not, someone has access to this mailbox. Change your email password first, "
        "then reset your Livermore password again from the sign-in screen, and reply to this "
        "email so we can help.</p>"
    )
    return {"subject": "Your Livermore password was changed", "text": text, "html": html}
