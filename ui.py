# Hook wiring and HTML for the restyled main window.
from __future__ import annotations

import html
import json
import os
import re
from typing import TYPE_CHECKING, Any

from aqt import gui_hooks
from aqt.deckbrowser import DeckBrowser, DeckBrowserBottomBar, DeckBrowserContent
from aqt.editor import Editor
from aqt.overview import Overview, OverviewBottomBar
from aqt.reviewer import Reviewer, ReviewerBottomBar
from aqt.toolbar import BottomToolbar, Toolbar, TopToolbar
from aqt.webview import AnkiWebView, AnkiWebViewKind, WebContent

from . import stats

if TYPE_CHECKING:
    from aqt.main import AnkiQt

_mw: AnkiQt | None = None
_pkg = ""


def setup(mw: AnkiQt) -> None:
    global _mw, _pkg
    _mw = mw
    _pkg = mw.addonManager.addonFromModule(__name__)
    mw.addonManager.setWebExports(__name__, r"web/.*\.(css|js|svg)")

    gui_hooks.webview_will_set_content.append(on_webview_will_set_content)
    gui_hooks.deck_browser_will_render_content.append(on_deck_browser_content)
    gui_hooks.top_toolbar_did_redraw.append(on_toolbar_redraw)
    gui_hooks.state_did_change.append(on_state_change)
    gui_hooks.webview_did_inject_style_into_page.append(on_style_injected)
    gui_hooks.webview_did_receive_js_message.append(on_js_message)
    gui_hooks.deck_browser_will_show_options_menu.append(on_deck_menu)
    gui_hooks.top_toolbar_did_init_links.append(on_toolbar_links)
    gui_hooks.overview_will_render_bottom.append(on_overview_bottom)
    gui_hooks.overview_will_render_content.append(on_overview_content)
    gui_hooks.top_toolbar_will_set_right_tray_content.append(on_right_tray)
    _patch_login_dialog()


def _css(name: str) -> str:
    return f"/_addons/{_pkg}/web/{name}.css"


# Stylesheets per screen
######################################################################

BOTTOM_CONTEXTS = (BottomToolbar, DeckBrowserBottomBar, OverviewBottomBar, ReviewerBottomBar)


def on_webview_will_set_content(web_content: WebContent, context: Any) -> None:
    web_content.css.append(_css("base"))
    if isinstance(context, TopToolbar):
        web_content.css.append(_css("top"))
    elif isinstance(context, BOTTOM_CONTEXTS):
        web_content.css.append(_css("bottom"))
        if isinstance(context, ReviewerBottomBar):
            web_content.css.append(_css("reviewer-bottom"))
    elif isinstance(context, DeckBrowser):
        web_content.css.append(_css("decks"))
    elif isinstance(context, Overview):
        web_content.css.append(_css("overview"))
    elif isinstance(context, Reviewer):
        web_content.css.append(_css("reviewer"))
        web_content.js.append(f"/_addons/{_pkg}/web/reviewer.js")
    elif isinstance(context, Editor):
        web_content.css.append(_css("editor"))
        web_content.js.append(f"/_addons/{_pkg}/web/editor.js")
    elif type(context).__name__ == "EditPage":
        web_content.css.append(_css("editpage"))
        web_content.js.append(f"/_addons/{_pkg}/web/editpage.js")


# Svelte pages: one shared stylesheet for every settings-style webview
######################################################################

STYLED_KINDS = frozenset(
    {
        AnkiWebViewKind.DECK_OPTIONS,
        AnkiWebViewKind.DECK_STATS,
        AnkiWebViewKind.CHANGE_NOTETYPE,
        AnkiWebViewKind.IMPORT_CSV,
        AnkiWebViewKind.IMPORT_ANKI_PACKAGE,
        AnkiWebViewKind.IMPORT_LOG,
        AnkiWebViewKind.BROWSER_CARD_INFO,
        AnkiWebViewKind.PREFERENCES,
    }
)


def _inject(webview: AnkiWebView, css_name: str, js_name: str | None = None) -> None:
    web = os.path.join(os.path.dirname(__file__), "web")
    try:
        stamp = int(os.path.getmtime(os.path.join(web, f"{css_name}.css")))
        script = ""
        if js_name:
            with open(os.path.join(web, f"{js_name}.js"), encoding="utf-8") as f:
                script = f.read()
    except OSError:
        return
    webview.eval(
        f"""
(function() {{
  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "/_addons/{_pkg}/web/{css_name}.css?v={stamp}";
  document.head.appendChild(link);
}})();
{script}
"""
    )


def on_style_injected(webview: AnkiWebView) -> None:
    if webview.kind == AnkiWebViewKind.DECK_OPTIONS:
        # Tell the page which Med School variant (if any) this deck is on.
        from . import presets

        active = None
        dialog = webview.window()
        deck = getattr(dialog, "_deck", None)
        if deck:
            from anki.decks import DeckId

            active = presets.active_variant(DeckId(deck["id"]))
        webview.eval(f"window.mPresetActive = {json.dumps(active)};")
        _inject(webview, "pages", "deck-options")
    elif webview.kind in STYLED_KINDS:
        _inject(webview, "pages")
    elif webview.kind == AnkiWebViewKind.EDITOR:
        _inject(webview, "editor", "editor")


# Active state on the top nav
######################################################################

_STATE_TO_LINK = {"deckBrowser": "decks", "overview": "decks", "m_edit": "browse"}


def _mark_active(state: str) -> None:
    assert _mw
    link = _STATE_TO_LINK.get(state, "")
    _mw.toolbar.web.eval(
        "document.querySelectorAll('.hitem.m-active')"
        ".forEach(e => e.classList.remove('m-active'));"
        f"document.getElementById({link!r})?.classList.add('m-active');"
    )


def on_toolbar_redraw(_toolbar: Toolbar) -> None:
    assert _mw
    _mark_active(_mw.state)


def on_state_change(new_state: str, _old_state: str) -> None:
    _mark_active(new_state)


# Deck browser: today strip
######################################################################


_OPTS_CELL = re.compile(
    r"""<td align=center class=opts><a onclick='return pycmd\("opts:(\d+)"\);'>"""
    r"""<img src='/_anki/imgs/gears.svg' class=gears></a></td>"""
)


def _opts_cell(m: re.Match[str]) -> str:
    did = m.group(1)
    return (
        f'<td align=center class="opts m-opts">'
        f"""<a title="Edit cards" onclick='return pycmd("m_editdeck:{did}");'>"""
        f"<img src='/_addons/{_pkg}/web/pencil.svg' class='gears m-pencil'></a>"
        f"""<a title="Deck options" onclick='return pycmd("m_opts:{did}");'>"""
        f"<img src='/_anki/imgs/gears.svg' class=gears></a>"
        f"""<a title="More" onclick='return pycmd("opts:{did}");'>"""
        f"<img src='/_addons/{_pkg}/web/more.svg' class='gears m-more'></a></td>"
    )


OVERVIEW_HIDDEN_LINKS = {"description", "opts", "studymore"}


def on_overview_bottom(link_handler: Any, links: list[list[str]]) -> Any:
    """Options / Custom Study / Description moved off the overview's bottom bar.

    Options is reached from the gear next to the deck title; Custom Study lives
    inside the options page.
    """
    links[:] = [link for link in links if link[1] not in OVERVIEW_HIDDEN_LINKS]
    return link_handler


def on_overview_content(_overview: Any, content: Any) -> None:
    """Gear icon next to the deck title that opens this deck's options.

    The title slot is escaped by Anki, so the gear is emitted into the
    share-link slot (raw HTML) and moved into the heading by a tiny script.
    """
    content.shareLink = (
        content.shareLink
        + """<a class="m-gear" title="Deck options" onclick="return pycmd('m_opts')">"""
        "<img src='/_anki/imgs/gears.svg'></a>"
        "<script>(function(){var h=document.querySelector('h3'),g=document.querySelector('.m-gear');"
        "if(h&&g){h.appendChild(g);}})();</script>"
    )


# Light / dark toggle in the top bar
######################################################################

SUN = (
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4"/>'
    '<path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2'
    'M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
)
MOON = (
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>'
)


_sync_link_html = ""


def on_toolbar_links(links: list[str], _toolbar: Toolbar) -> None:
    """Pull Anki's sync link out of the centre; it is re-homed in the right tray."""
    global _sync_link_html
    for i, html_ in enumerate(links):
        if 'id="sync"' in html_:
            _sync_link_html = links.pop(i)
            break


def _login_link() -> str:
    """Anki's own sync anchor (keeps #sync/#sync-spinner so its JS still works),
    relabelled to Log in until an AnkiWeb account is connected."""
    assert _mw
    html_ = _sync_link_html
    if not html_:
        return ""
    from aqt.utils import tr

    # The toolbar is first drawn before any profile is open.
    profile = _mw.pm.profile
    logged_in = bool(profile and _mw.pm.sync_auth())
    label = "Sync" if logged_in else "Log in"
    user = (profile or {}).get("syncUser") or ""
    tip = f"Sync with AnkiWeb ({user})" if logged_in and user else (
        "Sync with AnkiWeb" if logged_in else "Log in to AnkiWeb"
    )
    html_ = html_.replace(f">{tr.qt_misc_sync()}<img", f">{label}<img")
    html_ = re.sub(r'title="[^"]*"', f'title="{tip}"', html_, count=1)
    html_ = html_.replace("class=hitem", 'class="hitem m-login"', 1)
    return html_


def on_right_tray(content: list[str], _toolbar: Toolbar) -> None:
    from aqt.theme import theme_manager

    content.append(_login_link())

    dark = theme_manager.night_mode
    icon = SUN if dark else MOON
    tip = "Switch to light mode" if dark else "Switch to dark mode"
    content.append(
        f'<a class="m-theme" href="#" title="{tip}" aria-label="{tip}" '
        f"""onclick="return pycmd('m_theme')">{icon}</a>"""
    )


# AnkiWeb login dialog: plain email/password form with a sign-up link
######################################################################

SIGNUP_URL = "https://ankiweb.net/account/signup"


def _patch_login_dialog() -> None:
    import aqt.sync as sync_mod

    def get_id_and_pass_from_user(
        mw: Any, callback: Any, username: str = "", password: str = ""
    ) -> None:
        from aqt.qt import (
            QDialog,
            QDialogButtonBox,
            QFormLayout,
            QLabel,
            QLineEdit,
            QPushButton,
            Qt,
            QVBoxLayout,
            qconnect,
        )
        from aqt.utils import disable_help_button, openLink

        diag = QDialog(mw)
        diag.setWindowTitle("Log in to AnkiWeb")
        disable_help_button(diag)
        diag.setMinimumWidth(380)
        from .qss import dialog_qss, present_modal

        diag.setStyleSheet(dialog_qss())

        vbox = QVBoxLayout(diag)
        vbox.setSpacing(14)
        vbox.setContentsMargins(24, 22, 24, 20)

        heading = QLabel("Log in to AnkiWeb")
        heading.setObjectName("m_heading")
        vbox.addWidget(heading)

        form = QFormLayout()
        form.setSpacing(10)
        user = QLineEdit(username)
        user.setPlaceholderText("you@example.com")
        passwd = QLineEdit(password)
        passwd.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Email", user)
        form.addRow("Password", passwd)
        vbox.addLayout(form)

        signup = QPushButton("Don't have an account? Sign up")
        signup.setObjectName("m_link")
        signup.setFlat(True)
        signup.setCursor(Qt.CursorShape.PointingHandCursor)
        qconnect(signup.clicked, lambda: openLink(SIGNUP_URL))
        vbox.addWidget(signup, 0, Qt.AlignmentFlag.AlignLeft)

        bb = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok = bb.button(QDialogButtonBox.StandardButton.Ok)
        assert ok is not None
        ok.setText("Log in")
        ok.setObjectName("m_primary")
        ok.setAutoDefault(True)
        qconnect(bb.accepted, diag.accept)
        qconnect(bb.rejected, diag.reject)
        vbox.addWidget(bb)

        def on_finished(result: int) -> None:
            if result == QDialog.DialogCode.Rejected:
                callback("", "")
            else:
                callback(user.text().strip(), passwd.text())

        qconnect(diag.finished, on_finished)
        diag._m_adopted = True  # type: ignore[attr-defined]
        present_modal(diag)
        user.setFocus()

    sync_mod.get_id_and_pass_from_user = get_id_and_pass_from_user  # type: ignore[assignment]


def toggle_theme() -> None:
    from aqt.theme import Theme, theme_manager

    assert _mw
    _mw.set_theme(Theme.LIGHT if theme_manager.night_mode else Theme.DARK)
    # The top bar is drawn once at startup; redraw so the icon reflects the mode.
    _mw.toolbar.draw()
    _mark_active(_mw.state)


def on_js_message(handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
    if isinstance(context, TopToolbar) and message == "m_theme":
        toggle_theme()
        return (True, None)
    if isinstance(context, Overview) and message == "m_opts":
        from aqt.deckoptions import display_options_for_deck

        assert _mw
        display_options_for_deck(_mw.col.decks.current())
        return (True, None)
    if message.startswith("m_preset:"):
        from . import presets

        presets.on_cmd(message)
        return (True, None)
    if message == "m_custom_study":
        import aqt.customstudy

        assert _mw
        aqt.customstudy.CustomStudy.fetch_data_and_show(_mw)
        return (True, None)
    if isinstance(context, DeckBrowser) and message.startswith("m_opts:"):
        from anki.decks import DeckId
        from aqt.deckoptions import display_options_for_deck_id

        display_options_for_deck_id(DeckId(int(message.split(":", 1)[1])))
        return (True, None)
    if isinstance(context, DeckBrowser) and message.startswith("m_editdeck:"):
        from anki.decks import DeckId

        from . import editpage

        editpage.show(DeckId(int(message.split(":", 1)[1])))
        return (True, None)
    return handled


def on_deck_menu(menu: Any, _deck_id: int) -> None:
    # The gear on the row opens options, so drop the duplicate menu entry.
    from aqt.utils import tr

    for action in menu.actions():
        if action.text() == tr.actions_options():
            menu.removeAction(action)
            break


def on_deck_browser_content(browser: DeckBrowser, content: DeckBrowserContent) -> None:
    # Row icons: pencil = edit cards, gear = deck options, dots = the rest.
    content.tree = _OPTS_CELL.sub(_opts_cell, content.tree)
    try:
        today = stats.collect(browser.mw.col)
    except Exception:
        # Never break the deck list because of a stats problem.
        return
    content.stats = render_today(today)


def _tile(value: str, label: str, klass: str = "") -> str:
    return (
        f'<div class="m-tile {klass}"><div class="m-value">{value}</div>'
        f'<div class="m-label">{html.escape(label)}</div></div>'
    )


def render_today(t: stats.TodayStats) -> str:
    if t.cards:
        headline = f"{t.cards} card{'s' if t.cards != 1 else ''} today"
        sub = f"{stats.fmt_duration(t.seconds)} studied"
        if t.cards and t.seconds:
            sub += f" · {t.seconds / t.cards:.1f}s per card"
        mood = "done" if not t.due else ""
    elif t.due:
        headline = "Nothing reviewed yet"
        sub = f"{t.due} card{'s' if t.due != 1 else ''} waiting for you"
        mood = "nudge"
    else:
        headline = "All caught up"
        sub = "Nothing due right now"
        mood = "done"

    if t.streak >= 2:
        streak_val = f"{t.streak}"
        streak_label = "day streak" if t.cards else "day streak · at risk"
        streak_klass = "hot" if t.cards else "warm"
    elif t.studied_yesterday or t.cards:
        streak_val = "1"
        streak_label = "day streak"
        streak_klass = "warm"
    else:
        streak_val = "0"
        streak_label = "day streak"
        streak_klass = ""

    tiles = "".join(
        [
            _tile(str(t.cards), "reviewed today", "today"),
            _tile(stats.fmt_duration(t.seconds), "time today", "time"),
            _tile(streak_val, streak_label, f"streak {streak_klass}"),
            _tile(str(t.due), "due now", "due" if t.due else "due zero"),
        ]
    )
    return f"""
<div id="studiedToday" class="m-today {mood}">
  <div class="m-headline">{html.escape(headline)}</div>
  <div class="m-sub">{html.escape(sub)}</div>
  <div class="m-tiles">{tiles}</div>
</div>"""
