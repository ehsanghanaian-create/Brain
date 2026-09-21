"""Site phone-number change: derive every form the number is stored in and render the operator runbook.

A WordPress site keeps the same phone in Latin and Persian digits, with and without separators, and — inside Elementor
data — as escaped Persian (`\\u06f2…`), which a plain search never finds. The operator supplies only the old and the new
number; everything below (the eight-digit blocks, the six literal variants, the escaped pair, the SQL) is derived here
so nothing is forgotten and the replacement keeps the string length of serialized data intact.

Nothing in this module touches a site: it produces text for a human or an agent with hosting access."""
from __future__ import annotations

import re
from typing import Any

from ...ai.prompts.library import render
from ...ai.prompts.runbooks import PHONE_CHANGE_TEMPLATE

FA_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
BLOCK = 4                      # the 8-digit tail is compared/replaced as two 4-digit halves around a separator
TABLES = (("posts", ("post_content", "post_excerpt", "post_title")), ("postmeta", ("meta_value",)), ("options", ("option_value",)))


class PhoneChangeError(ValueError):
    """The two numbers cannot be swapped safely (non-numeric, too short, different tail length, or identical)."""


def digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def to_fa(latin: str) -> str:
    return "".join(FA_DIGITS[int(c)] for c in latin)


def to_escaped(latin: str) -> str:
    """Persian digits the way Elementor stores them in JSON: ۲ → \\u06f2."""
    return "".join(f"\\u06f{c}" for c in latin)


def _pairs(old8: str, new8: str) -> list[tuple[str, str]]:
    """The six literal forms (Latin/Persian × no separator, space, dash), longest first so nested REPLACEs stay safe."""
    out: list[tuple[str, str]] = []
    for sep in ("", " ", "-"):
        out.append((f"{old8[:BLOCK]}{sep}{old8[BLOCK:]}", f"{new8[:BLOCK]}{sep}{new8[BLOCK:]}"))
    fa_old, fa_new = to_fa(old8), to_fa(new8)
    for sep in ("", " ", "-"):
        out.append((f"{fa_old[:BLOCK]}{sep}{fa_old[BLOCK:]}", f"{fa_new[:BLOCK]}{sep}{fa_new[BLOCK:]}"))
    return out


def _sql_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


def _nested_replace(column: str, pairs: list[tuple[str, str]]) -> str:
    expr = column
    for old, new in pairs:
        expr = f"REPLACE({expr}, '{_sql_escape(old)}', '{_sql_escape(new)}')"
    return expr


def plan(old_phone: str, new_phone: str, site: str = "", *, db_name: str = "", prefix: str = "wp_", site_url: str = "", template: str | None = None) -> dict[str, Any]:
    """Everything the runbook needs, derived from the two numbers. `template` lets the platform's edited version of the
    prompt (prompt library key `task.phone_change`) win over the built-in one. Raises PhoneChangeError on an unsafe pair."""
    old, new = digits(old_phone), digits(new_phone)
    if not old or not new:
        raise PhoneChangeError("شمارهٔ قدیمی و جدید باید رقم داشته باشند")
    if len(old) < BLOCK * 2 or len(new) < BLOCK * 2:
        raise PhoneChangeError(f"هر شماره باید حداقل {BLOCK * 2} رقم داشته باشد")
    old8, new8 = old[-BLOCK * 2:], new[-BLOCK * 2:]
    if len(old8) != len(new8):
        raise PhoneChangeError("طول بلوک هشت‌رقمی باید برابر باشد")
    if old8 == new8:
        raise PhoneChangeError("هشت رقم آخر شمارهٔ قدیمی و جدید یکی است — چیزی برای تغییر نیست")
    pairs = _pairs(old8, new8)
    esc_old, esc_new = to_escaped(old8), to_escaped(new8)
    prefix = (prefix or "wp_").strip()
    db_name = (db_name or "").strip() or "(نام دیتابیس از wp-config.php)"

    sql_text: list[str] = []
    for table, columns in TABLES:
        sets = ",\n    ".join(f"{col} = {_nested_replace(col, pairs)}" for col in columns)
        where = " OR ".join(f"{col} LIKE '%{old8[:BLOCK]}%' OR {col} LIKE '%{to_fa(old8)[:BLOCK]}%'" for col in columns)
        sql_text.append(f"UPDATE `{prefix}{table}`\nSET {sets}\nWHERE {where};")
    sql_escaped = (f"UPDATE `{prefix}postmeta`\nSET meta_value = REPLACE(meta_value, '{_sql_escape(esc_old)}', '{_sql_escape(esc_new)}')\n"
                   f"WHERE meta_value LIKE '%{_sql_escape(to_escaped(old8[:BLOCK]))}%';\n\n"
                   f"UPDATE `{prefix}posts`\nSET post_content = REPLACE(post_content, '{_sql_escape(esc_old)}', '{_sql_escape(esc_new)}')\n"
                   f"WHERE post_content LIKE '%{_sql_escape(to_escaped(old8[:BLOCK]))}%';")
    sql_cache = (f"DELETE FROM `{prefix}postmeta` WHERE meta_key = '_elementor_css';\n"
                 f"DELETE FROM `{prefix}options`  WHERE option_name LIKE '\\_transient\\_%' OR option_name LIKE '\\_site\\_transient\\_%';")
    counts = []
    for table, columns in TABLES:
        for col in columns:
            like = " OR ".join(f"{col} LIKE '%{_sql_escape(v)}%'" for v in (old8, to_fa(old8), esc_old))
            counts.append(f"SELECT '{table}.{col}' AS col, COUNT(*) AS old_left FROM `{prefix}{table}` WHERE {like}")
    sql_verify = "\nUNION ALL\n".join(counts) + ";"

    variables = {
        "site": site or "(دامنهٔ سایت)", "site_url": site_url or (f"https://{site}/" if site else "https://example.com/"),
        "old_phone": old_phone.strip(), "new_phone": new_phone.strip(), "len8": str(len(old8)),
        "old8": old8, "new8": new8,
        "old8_sp": pairs[1][0], "new8_sp": pairs[1][1], "old8_dash": pairs[2][0], "new8_dash": pairs[2][1],
        "old8_fa": pairs[3][0], "new8_fa": pairs[3][1], "old8_fa_sp": pairs[4][0], "new8_fa_sp": pairs[4][1],
        "old8_fa_dash": pairs[5][0], "new8_fa_dash": pairs[5][1],
        "old8_esc": esc_old, "new8_esc": esc_new,
        "db_name": db_name, "prefix": prefix,
        "sql_text": "\n\n".join(sql_text), "sql_escaped": sql_escaped, "sql_cache": sql_cache, "sql_verify": sql_verify
    }
    return {"variables": variables, "pairs": [{"old": o, "new": n} for o, n in pairs] + [{"old": esc_old, "new": esc_new}],
            "old8": old8, "new8": new8, "runbook": render(template or PHONE_CHANGE_TEMPLATE, variables)}
