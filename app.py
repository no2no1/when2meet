"""
Class Friendship Hub (מרכז החברות הכיתתי)
Streamlit app for coordinating play availability among ~30 classmates.
"""

from __future__ import annotations

# Windows/school networks often intercept HTTPS. Inject OS trust store before any API calls.
try:
    import truststore

    truststore.inject_into_ssl()
    _USING_SYSTEM_CERTS = True
except ImportError:
    try:
        import pip_system_certs.wrapt_requests  # noqa: F401

        _USING_SYSTEM_CERTS = True
    except ImportError:
        _USING_SYSTEM_CERTS = False

import hashlib
import html as html_lib
import os
import re
import ssl
from datetime import date, datetime, time

import certifi
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components


def configure_ssl_certificates() -> None:
    """
    Fallback when pip-system-certs is unavailable.
    Patches httplib2 and requests to use certifi's CA bundle.
    """
    if _USING_SYSTEM_CERTS:
        return
    ca_bundle = certifi.where()
    os.environ.setdefault("SSL_CERT_FILE", ca_bundle)
    os.environ.setdefault("REQUESTS_CA_BUNDLE", ca_bundle)

    try:
        ssl._create_default_https_context = ssl.create_default_context(cafile=ca_bundle)
    except Exception:
        pass

    try:
        import httplib2

        _original_http = httplib2.Http

        def http_with_certs(*args, **kwargs):
            kwargs.setdefault("ca_certs", ca_bundle)
            return _original_http(*args, **kwargs)

        httplib2.Http = http_with_certs  # type: ignore[misc, assignment]
    except Exception:
        pass

    try:
        import requests

        _original_request = requests.Session.request

        def request_with_certs(self, method, url, *args, **kwargs):
            if kwargs.get("verify", True) is True:
                kwargs["verify"] = ca_bundle
            return _original_request(self, method, url, *args, **kwargs)

        requests.Session.request = request_with_certs  # type: ignore[method-assign]
    except Exception:
        pass


configure_ssl_certificates()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

APP_TITLE = "מרכז החברות הכיתתי"
APP_SUBTITLE = "🎈 בואו נתאם מתי ואיפה כולנו פנויים לשחק! 🎈"
SEARCH_EVERYONE = "כולם"

LOCATION_OPTIONS = [
    "אצלי בבית 🏠",
    "בחוץ / בגינה 🌳",
    "לא אצלי בבית 🏃",
]

# 30 bright, distinct colors — one per classmate slot
CHILD_COLORS: list[str] = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7",
    "#DDA0DD", "#98D8C8", "#F7DC6F", "#BB8FCE", "#85C1E9",
    "#F8B500", "#00CED1", "#FF69B4", "#32CD32", "#FF4500",
    "#9370DB", "#20B2AA", "#FFD700", "#DC143C", "#00FA9A",
    "#1E90FF", "#FF1493", "#ADFF2F", "#FF6347", "#7B68EE",
    "#00BFFF", "#FFA07A", "#3CB371", "#BA55D3", "#FFDAB9",
]

SHEET_COLUMNS = ["name", "date", "time", "location"]

MOCK_SEED_DATA: list[dict[str, str]] = [
    {
        "name": "נועה",
        "date": "2026-06-28",
        "time": "16:00",
        "location": "אצלי בבית 🏠",
    },
    {
        "name": "איתי",
        "date": "2026-06-28",
        "time": "17:30",
        "location": "בחוץ / בגינה 🌳",
    },
    {
        "name": "מיה",
        "date": "2026-06-29",
        "time": "10:00",
        "location": "לא אצלי בבית 🏃",
    },
]

# ---------------------------------------------------------------------------
# Page config & global styling
# ---------------------------------------------------------------------------


def inject_rtl_css() -> None:
    """Inject kid-friendly RTL styling across the entire app."""
    st.markdown(
        """
        <style>
            /* Global RTL */
            html, body, [class*="css"] {
                direction: rtl;
                text-align: right;
            }

            /* Hide default Streamlit header clutter */
            #MainMenu { visibility: hidden; }
            footer { visibility: hidden; }

            /* Main container */
            .block-container {
                padding-top: 1.5rem;
                max-width: 960px;
            }

            /* Hero banner */
            .hero-banner {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
                border-radius: 24px;
                padding: 2rem 2.5rem;
                margin-bottom: 1.5rem;
                box-shadow: 0 12px 40px rgba(102, 126, 234, 0.35);
                text-align: center;
                color: white;
            }
            .hero-banner h1 {
                font-size: 2.4rem;
                font-weight: 800;
                margin: 0 0 0.5rem 0;
                text-shadow: 2px 2px 8px rgba(0,0,0,0.2);
            }
            .hero-banner p {
                font-size: 1.15rem;
                margin: 0;
                opacity: 0.95;
            }

            /* Section cards */
            .section-card {
                background: linear-gradient(180deg, #ffffff 0%, #f8f9ff 100%);
                border-radius: 20px;
                padding: 1.75rem;
                margin-bottom: 1.5rem;
                box-shadow: 0 8px 32px rgba(0, 0, 0, 0.08);
                border: 2px solid rgba(102, 126, 234, 0.15);
            }
            .section-title {
                font-size: 1.5rem;
                font-weight: 700;
                color: #4a4a8a;
                margin-bottom: 1rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
            }

            /* Schedule day block */
            .day-block {
                background: white;
                border-radius: 16px;
                padding: 1rem 1.25rem;
                margin-bottom: 1rem;
                border-right: 6px solid #667eea;
                box-shadow: 0 4px 16px rgba(0,0,0,0.06);
            }
            .day-header {
                font-size: 1.2rem;
                font-weight: 700;
                color: #333;
                margin-bottom: 0.75rem;
            }

            /* Time slot pill */
            .slot-row {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: 0.6rem;
                margin-bottom: 0.5rem;
                padding: 0.5rem 0;
            }
            .slot-time {
                font-weight: 700;
                font-size: 1rem;
                min-width: 4.5rem;
                color: #555;
            }
            .slot-badge {
                display: inline-block;
                padding: 0.35rem 0.9rem;
                border-radius: 999px;
                color: white;
                font-weight: 600;
                font-size: 0.95rem;
                box-shadow: 0 3px 10px rgba(0,0,0,0.15);
            }
            .slot-location {
                color: #666;
                font-size: 0.9rem;
            }

            /* Empty / info states */
            .info-box {
                background: linear-gradient(135deg, #e0f7fa 0%, #e8eaf6 100%);
                border-radius: 16px;
                padding: 1.5rem;
                text-align: center;
                color: #455a64;
                font-size: 1.05rem;
            }
            .warning-box {
                background: #fff3e0;
                border-radius: 16px;
                padding: 1rem 1.25rem;
                color: #e65100;
                border: 2px dashed #ffb74d;
            }

            /* Form styling */
            div[data-testid="stForm"] {
                background: linear-gradient(180deg, #fff9e6 0%, #ffe0f0 100%);
                border-radius: 20px;
                padding: 1.5rem;
                border: 3px solid #ff9a9e;
                box-shadow: 0 8px 28px rgba(255, 154, 158, 0.25);
            }

            /* Search bar highlight */
            div[data-testid="stTextInput"] input {
                border-radius: 16px !important;
                border: 2px solid #667eea !important;
                padding: 0.75rem 1rem !important;
                font-size: 1.1rem !important;
            }

            /* Submit button */
            div[data-testid="stForm"] button[kind="primaryFormSubmit"] {
                background: linear-gradient(90deg, #f093fb 0%, #f5576c 100%) !important;
                border: none !important;
                border-radius: 16px !important;
                font-size: 1.2rem !important;
                font-weight: 700 !important;
                padding: 0.75rem 2rem !important;
                box-shadow: 0 6px 20px rgba(245, 87, 108, 0.4) !important;
            }

            /* Mode badge */
            .mode-badge {
                display: inline-block;
                padding: 0.3rem 0.8rem;
                border-radius: 999px;
                font-size: 0.85rem;
                font-weight: 600;
                margin-bottom: 1rem;
            }
            .mode-live { background: #c8e6c9; color: #2e7d32; }
            .mode-demo { background: #fff9c4; color: #f57f17; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Color utilities
# ---------------------------------------------------------------------------


def get_color_for_name(name: str) -> str:
    """
    Deterministic color: the same name always maps to the same palette color.
    Uses MD5 so results are stable across runs and machines.
    """
    normalized = name.strip()
    if not normalized:
        return CHILD_COLORS[0]
    digest = hashlib.md5(normalized.encode("utf-8")).hexdigest()
    index = int(digest, 16) % len(CHILD_COLORS)
    return CHILD_COLORS[index]


def text_color_for_background(hex_color: str) -> str:
    """Pick white or dark text for readable contrast on colored badges."""
    hex_color = hex_color.lstrip("#")
    r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#1a1a1a" if luminance > 0.65 else "#ffffff"


# ---------------------------------------------------------------------------
# Google Sheets / data layer
# ---------------------------------------------------------------------------


def _secrets_available() -> bool:
    try:
        return (
            "gcp_service_account" in st.secrets
            and "spreadsheet_id" in st.secrets
            and get_spreadsheet_id()
        )
    except Exception:
        return False


def get_spreadsheet_id() -> str:
    """Return spreadsheet ID; accepts a full Google Sheets URL in secrets too."""
    raw = str(st.secrets["spreadsheet_id"]).strip()
    match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", raw)
    if match:
        return match.group(1)
    return raw.strip("/")


@st.cache_resource(show_spinner=False)
def get_gspread_client():
    """Build an authorized gspread client from st.secrets (cached)."""
    import gspread
    from google.oauth2.service_account import Credentials

    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = dict(st.secrets["gcp_service_account"])
    credentials = Credentials.from_service_account_info(creds_dict, scopes=scope)
    client = gspread.authorize(credentials)
    if not _USING_SYSTEM_CERTS:
        client.http_client.session.verify = certifi.where()
    return client


def _init_mock_data() -> None:
    if "availability_records" not in st.session_state:
        st.session_state.availability_records = list(MOCK_SEED_DATA)


def load_records() -> tuple[pd.DataFrame, str]:
    """
    Load availability records from Google Sheets or session-state fallback.
    Returns (dataframe, mode) where mode is 'live' or 'demo'.
    """
    if _secrets_available():
        try:
            client = get_gspread_client()
            spreadsheet_id = get_spreadsheet_id()
            worksheet_name = st.secrets.get("worksheet_name", "availability")
            spreadsheet = client.open_by_key(spreadsheet_id)
            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
            except Exception:
                worksheet = spreadsheet.sheet1

            rows = worksheet.get_all_records(expected_headers=SHEET_COLUMNS)
            df = pd.DataFrame(rows)
            if df.empty:
                df = pd.DataFrame(columns=SHEET_COLUMNS)
            return df, "live"
        except Exception as exc:
            get_gspread_client.clear()
            st.warning(f"⚠️ לא הצלחנו לטעון מ-Google Sheets: {exc}. עוברים למצב הדגמה.")
            _init_mock_data()
            df = pd.DataFrame(st.session_state.availability_records)
            return df, "demo"

    _init_mock_data()
    df = pd.DataFrame(st.session_state.availability_records)
    return df, "demo"


def append_record(record: dict[str, str]) -> tuple[bool, str]:
    """Persist one availability row. Returns (success, mode)."""
    if _secrets_available():
        try:
            client = get_gspread_client()
            spreadsheet_id = get_spreadsheet_id()
            worksheet_name = st.secrets.get("worksheet_name", "availability")
            spreadsheet = client.open_by_key(spreadsheet_id)
            try:
                worksheet = spreadsheet.worksheet(worksheet_name)
            except Exception:
                worksheet = spreadsheet.sheet1
                worksheet.update("A1:D1", [SHEET_COLUMNS])

            existing = worksheet.get_all_values()
            if not existing:
                worksheet.update("A1:D1", [SHEET_COLUMNS])

            worksheet.append_row(
                [record["name"], record["date"], record["time"], record["location"]],
                value_input_option="USER_ENTERED",
            )
            return True, "live"
        except Exception as exc:
            get_gspread_client.clear()
            st.warning(f"⚠️ שמירה ל-Google Sheets נכשלה: {exc}. שומרים במצב הדגמה.")
            _init_mock_data()
            st.session_state.availability_records.append(record)
            return True, "demo"

    _init_mock_data()
    st.session_state.availability_records.append(record)
    return True, "demo"


def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure consistent columns and sortable date/time fields."""
    if df.empty:
        return pd.DataFrame(columns=SHEET_COLUMNS)

    for col in SHEET_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df[SHEET_COLUMNS].copy()
    df["name"] = df["name"].astype(str).str.strip()
    df["date"] = df["date"].astype(str).str.strip()
    df["time"] = df["time"].astype(str).str.strip()
    df["location"] = df["location"].astype(str).str.strip()
    df = df[df["name"] != ""]
    return df


def filter_records(df: pd.DataFrame, query: str) -> pd.DataFrame:
    """Filter by child name or return all rows for 'כולם'."""
    query = query.strip()
    if not query:
        return df.iloc[0:0]

    if query == SEARCH_EVERYONE:
        return df.copy()

    mask = df["name"].str.contains(query, case=False, na=False, regex=False)
    return df[mask].copy()


def format_hebrew_date(date_str: str) -> str:
    """Turn ISO date into a friendly Hebrew-ish display string."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d").date()
        weekdays = ["שני", "שלישי", "רביעי", "חמישי", "שישי", "שבת", "ראשון"]
        weekday = weekdays[dt.weekday()]
        return f"{weekday}, {dt.strftime('%d/%m/%Y')}"
    except ValueError:
        return date_str


# CSS embedded in schedule iframes (bypasses Streamlit HTML sanitizer)
SCHEDULE_DAY_CSS = """
body {
    direction: rtl;
    text-align: right;
    margin: 0;
    padding: 0;
    font-family: "Source Sans Pro", sans-serif;
    background: transparent;
}
.day-block {
    background: white;
    border-radius: 16px;
    padding: 1rem 1.25rem;
    margin-bottom: 0.25rem;
    border-right: 6px solid #667eea;
    box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
.day-header {
    font-size: 1.2rem;
    font-weight: 700;
    color: #333;
    margin-bottom: 0.75rem;
}
.slot-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.5rem;
    padding: 0.5rem 0;
}
.slot-time {
    font-weight: 700;
    font-size: 1rem;
    min-width: 4.5rem;
    color: #555;
}
.slot-badge {
    display: inline-block;
    padding: 0.35rem 0.9rem;
    border-radius: 999px;
    font-weight: 600;
    font-size: 0.95rem;
    box-shadow: 0 3px 10px rgba(0,0,0,0.15);
}
.slot-location {
    color: #666;
    font-size: 0.9rem;
}
"""


def build_day_schedule_html(day_label: str, day_rows: pd.DataFrame) -> tuple[str, int]:
    """Build a self-contained HTML fragment for one day's slots."""
    slot_parts: list[str] = []
    for _, row in day_rows.iterrows():
        bg = get_color_for_name(row["name"])
        fg = text_color_for_background(bg)
        slot_parts.append(
            f'<div class="slot-row">'
            f'<span class="slot-time">🕐 {html_lib.escape(str(row["time"]))}</span>'
            f'<span class="slot-badge" style="background:{bg}; color:{fg};">'
            f'{html_lib.escape(str(row["name"]))}</span>'
            f'<span class="slot-location">{html_lib.escape(str(row["location"]))}</span>'
            f"</div>"
        )

    safe_label = html_lib.escape(day_label)
    body = (
        f'<div class="day-block">'
        f'<div class="day-header">📆 {safe_label}</div>'
        f'{"".join(slot_parts)}'
        f"</div>"
    )
    page = (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{SCHEDULE_DAY_CSS}</style></head><body>{body}</body></html>"
    )
    height = 88 + len(day_rows) * 52
    return page, height


# ---------------------------------------------------------------------------
# UI components
# ---------------------------------------------------------------------------


def render_hero() -> None:
    st.markdown(
        f"""
        <div class="hero-banner">
            <h1>🌈 {APP_TITLE} 🌈</h1>
            <p>{APP_SUBTITLE}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_mode_badge(mode: str) -> None:
    if mode == "live":
        st.markdown(
            '<span class="mode-badge mode-live">✅ מחובר ל-Google Sheets</span>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            '<span class="mode-badge mode-demo">🧪 מצב הדגמה — הנתונים נשמרים בזיכרון</span>',
            unsafe_allow_html=True,
        )


def render_schedule(df: pd.DataFrame, query: str) -> None:
    """Render filtered availability as a colorful day-by-day schedule."""
    with st.container(border=True):
        st.markdown(
            '<div class="section-title">📅 לוח זמנים — מי פנוי מתי?</div>',
            unsafe_allow_html=True,
        )

        if not query.strip():
            st.markdown(
                '<div class="info-box">🔍 הקלידו שם ילד/ה או את המילה <strong>כולם</strong> '
                "כדי לראות את לוח הזמנים!</div>",
                unsafe_allow_html=True,
            )
            return

        filtered = filter_records(df, query)

        if filtered.empty:
            safe_query = html_lib.escape(query)
            st.markdown(
                f'<div class="info-box">😕 לא נמצאו זמינויות עבור "<strong>{safe_query}</strong>". '
                "נסו שם אחר או הוסיפו זמינות בטופס למטה!</div>",
                unsafe_allow_html=True,
            )
            return

        # Sort by date then time
        filtered = filtered.copy()
        filtered["_sort_date"] = pd.to_datetime(filtered["date"], errors="coerce")
        filtered["_sort_time"] = pd.to_datetime(filtered["time"], format="%H:%M", errors="coerce")
        filtered = filtered.sort_values(["_sort_date", "_sort_time", "name"])

        grouped = filtered.groupby("date", sort=False)

        for day_value, day_rows in grouped:
            day_label = format_hebrew_date(str(day_value))
            day_html, iframe_height = build_day_schedule_html(day_label, day_rows)
            # components.html avoids Streamlit's sanitizer that breaks nested divs
            components.html(day_html, height=iframe_height, scrolling=False)

        if query == SEARCH_EVERYONE:
            st.caption(f"מציג {len(filtered)} זמינויות של כל הכיתה 🎉")
        else:
            st.caption(f"מציג {len(filtered)} זמינויות עבור {query} ✨")


def render_entry_form() -> None:
    """Bottom section: styled form for adding availability."""
    st.markdown(
        '<div class="section-card">'
        '<div class="section-title">✏️ הוסיפו את הזמינות שלכם!</div>',
        unsafe_allow_html=True,
    )

    with st.form("availability_form", clear_on_submit=True):
        name = st.text_input("👤 השם שלי", placeholder="לדוגמה: דני")
        col_date, col_time = st.columns(2)
        with col_date:
            picked_date = st.date_input(
                "📅 תאריך",
                value=date.today(),
                min_value=date.today(),
            )
        with col_time:
            picked_time = st.time_input("⏰ שעה", value=time(16, 0))

        location = st.radio(
            "📍 איפה?",
            options=LOCATION_OPTIONS,
            horizontal=False,
        )

        submitted = st.form_submit_button(
            "🚀 שמרו את הזמינות שלי!",
            type="primary",
            use_container_width=True,
        )

        if submitted:
            handle_form_submit(name, picked_date, picked_time, location)

    st.markdown("</div>", unsafe_allow_html=True)


def handle_form_submit(
    name: str,
    picked_date: date,
    picked_time: time,
    location: str,
) -> None:
    """Validate, save, celebrate."""
    clean_name = (name or "").strip()

    if not clean_name:
        st.error("❌ אופס! חובה להזין שם.")
        return

    if len(clean_name) > 40:
        st.error("❌ השם ארוך מדי — עד 40 תווים בבקשה.")
        return

    record = {
        "name": clean_name,
        "date": picked_date.isoformat(),
        "time": picked_time.strftime("%H:%M"),
        "location": location,
    }

    success, mode = append_record(record)
    if success:
        color = get_color_for_name(clean_name)
        st.session_state["data_version"] = st.session_state.get("data_version", 0) + 1
        st.success(
            f"🎉 יופי {clean_name}! הזמינות נשמרה בהצלחה "
            f"({picked_date.strftime('%d/%m/%Y')} בשעה {record['time']}). "
            f"הצבע שלך: {color}"
        )
        if mode == "demo":
            st.info("💡 במצב הדגמה הנתונים נשמרים רק בזמן שהאפליקציה פתוחה.")
        st.balloons()


@st.cache_data(ttl=30, show_spinner=False)
def cached_load_records(_cache_key: int) -> tuple[pd.DataFrame, str]:
    """Cached wrapper; _cache_key bumps after writes."""
    return load_records()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🤝",
        layout="centered",
        initial_sidebar_state="collapsed",
    )

    inject_rtl_css()
    render_hero()

    cache_key = st.session_state.get("data_version", 0)
    df_raw, mode = cached_load_records(cache_key)
    df = normalize_dataframe(df_raw)

    render_mode_badge(mode)

    # --- Top: search & schedule ---
    search_query = st.text_input(
        "🔍 חיפוש לפי שם",
        placeholder=f'הקלידו שם או "{SEARCH_EVERYONE}"',
        key="search_query",
    )

    render_schedule(df, search_query)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Bottom: data entry ---
    render_entry_form()


if __name__ == "__main__":
    main()
