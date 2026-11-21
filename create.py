# "Create" replaces the top-bar Add link: one place to start a new deck or add
# cards to an existing one.
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from aqt import gui_hooks
from aqt.operations.deck import add_deck
from aqt.qt import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    Qt,
    QVBoxLayout,
    qconnect,
)
from aqt.toolbar import Toolbar, TopToolbar
from aqt.utils import disable_help_button, tooltip, tr

if TYPE_CHECKING:
    from aqt.main import AnkiQt

_mw: AnkiQt | None = None


def setup(mw: AnkiQt) -> None:
    global _mw
    _mw = mw
    gui_hooks.top_toolbar_did_init_links.append(on_toolbar_links)
    gui_hooks.webview_did_receive_js_message.append(on_js_message)
    _remove_bottom_create_deck()


def _remove_bottom_create_deck() -> None:
    """Deck creation and import live in the top-bar New dialog now."""
    from aqt.deckbrowser import DeckBrowser

    # Get Shared and Import File are reachable from the New dialog as well.
    DeckBrowser.drawLinks = []


def on_toolbar_links(links: list[str], _toolbar: Toolbar) -> None:
    for i, html_ in enumerate(links):
        if 'id="browse"' in html_:
            html_ = html_.replace(f">{tr.qt_misc_browse()}</a>", ">Edit</a>")
            html_ = html_.replace(f'aria-label="{tr.qt_misc_browse()}"', 'aria-label="Edit"')
            links[i] = html_
        if 'id="add"' in html_:
            html_ = html_.replace(f">{tr.actions_add()}</a>", ">New</a>")
            html_ = html_.replace("pycmd('add')", "pycmd('m_create')")
            html_ = html_.replace(f'aria-label="{tr.actions_add()}"', 'aria-label="New"')
            html_ = html_.replace('title="', 'title="New deck, add cards, or import. ', 1)
            links[i] = html_


def on_js_message(handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
    if isinstance(context, TopToolbar) and message == "m_create":
        show_create_dialog()
        return (True, None)
    return handled


# Dialog
######################################################################

from .qss import dialog_qss, present_modal


def show_create_dialog() -> None:
    assert _mw
    mw = _mw
    diag = QDialog(mw)
    diag.setWindowTitle("New")
    disable_help_button(diag)
    diag.setMinimumWidth(420)
    diag.setStyleSheet(dialog_qss())

    root = QVBoxLayout(diag)
    root.setContentsMargins(24, 22, 24, 20)
    root.setSpacing(10)

    # --- New deck -------------------------------------------------------
    h1 = QLabel("Create a new deck")
    h1.setObjectName("m_heading")
    name = QLineEdit()
    name.setPlaceholderText("Deck name")
    create_btn = QPushButton("Create deck")
    create_btn.setObjectName("m_primary")
    create_btn.setEnabled(False)
    create_btn.setDefault(True)
    row1 = QHBoxLayout()
    row1.addWidget(name, 1)
    row1.addWidget(create_btn)
    root.addWidget(h1)
    root.addLayout(row1)

    rule = QFrame()
    rule.setObjectName("m_rule")
    rule.setFixedHeight(1)
    root.addSpacing(10)
    root.addWidget(rule)
    root.addSpacing(10)

    # --- Import ---------------------------------------------------------
    h3 = QLabel("Import a deck")
    h3.setObjectName("m_heading")
    import_btn = QPushButton("Import file…")
    row3 = QHBoxLayout()
    row3.addWidget(h3, 1)
    row3.addWidget(import_btn)
    root.addLayout(row3)

    # --- Behaviour ------------------------------------------------------
    def do_import() -> None:
        diag.accept()
        mw.onImport()

    qconnect(import_btn.clicked, do_import)

    def on_name(text: str) -> None:
        create_btn.setEnabled(bool(text.strip()))

    def do_create() -> None:
        deck_name = name.text().strip()
        if not deck_name:
            return
        if mw.col.decks.id_for_name(deck_name):
            tooltip("A deck with that name already exists", parent=diag)
            return
        diag.accept()

        add_deck(parent=mw, name=deck_name).success(
            lambda _: tooltip(f"Created deck “{deck_name}”", parent=mw)
        ).run_in_background()

    qconnect(name.textChanged, on_name)
    qconnect(name.returnPressed, do_create)
    qconnect(create_btn.clicked, do_create)

    diag._m_adopted = True  # type: ignore[attr-defined]
    present_modal(diag)
    name.setFocus()
