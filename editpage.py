# "Edit" page: a Quizlet-style list of a deck's cards inside the main window,
# editable in place, with inline add, suspend and delete.
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from anki.consts import QUEUE_TYPE_SUSPENDED
from anki.decks import DeckId
from anki.notes import NoteId
from aqt import gui_hooks
from aqt.operations.note import add_note, remove_notes, update_note
from aqt.operations.scheduling import suspend_cards, unsuspend_cards
from aqt.toolbar import BottomBar, Toolbar, TopToolbar
from aqt.utils import tooltip, tr

if TYPE_CHECKING:
    from aqt.main import AnkiQt

STATE = "m_edit"
_mw: AnkiQt | None = None
_pkg = ""


class EditPage:
    """Bridge context object for the page (also used to recognise our webview)."""

    def __init__(self, mw: AnkiQt) -> None:
        self.mw = mw
        self.deck_id: DeckId | None = None


_page: EditPage | None = None
_bottom = object()  # bridge context for the (empty) bottom bar on this screen


def setup(mw: AnkiQt) -> None:
    global _mw, _pkg, _page
    _mw = mw
    _pkg = mw.addonManager.addonFromModule(__name__)
    _page = EditPage(mw)
    # moveToState() looks up _<state>State on the main window.
    mw._m_editState = lambda _old, *_a: render()  # type: ignore[attr-defined]
    gui_hooks.top_toolbar_did_init_links.append(on_toolbar_links)
    gui_hooks.webview_did_receive_js_message.append(on_js_message)
    gui_hooks.operation_did_execute.append(on_op_executed)


# Entry points
######################################################################


def on_toolbar_links(links: list[str], _toolbar: Toolbar) -> None:
    for i, html_ in enumerate(links):
        if 'id="browse"' in html_:
            links[i] = html_.replace("pycmd('browse')", "pycmd('m_edit')")


def on_js_message(handled: tuple[bool, Any], message: str, context: Any) -> tuple[bool, Any]:
    if isinstance(context, TopToolbar) and message == "m_edit":
        show()
        return (True, None)
    return handled


def show(deck_id: DeckId | None = None) -> None:
    assert _mw and _page
    _page.deck_id = deck_id or _mw.col.decks.get_current_id()
    _mw.moveToState(STATE)  # type: ignore[arg-type]


def on_op_executed(changes: Any, handler: object | None) -> None:
    # Refresh the list when something else changed notes/decks while we're shown.
    if _mw and _mw.state == STATE and handler is not _page:
        if changes.note_text or changes.note or changes.card or changes.deck:
            push_data()


# Rendering
######################################################################

BODY = """
<div class="m-edit" id="m-edit">
  <header class="m-edit-head">
    <div class="m-deck-wrap">
      <select id="m-deck" class="m-deck-select" aria-label="Deck"></select>
    </div>
    <span class="m-count" id="m-count"></span>
    <input id="m-search" class="m-search" type="search" placeholder="Search cards" autocomplete="off">
    <a class="m-adv" href="#" onclick="return pycmd('m_edit:browser')" title="Open the full browser">Advanced</a>
    <button class="m-primary" onclick="pycmd('m_edit:study')">Study</button>
  </header>

  <section class="m-add" id="m-add">
    <div class="m-add-fields">
      <div class="m-field-wrap">
        <div class="m-field m-add-front" id="m-add-front" contenteditable="true" data-placeholder="Front"></div>
        <div class="m-label">Front</div>
      </div>
      <div class="m-field-wrap">
        <div class="m-field m-add-back" id="m-add-back" contenteditable="true" data-placeholder="Back"></div>
        <div class="m-label">Back</div>
      </div>
    </div>
    <button class="m-add-btn" id="m-add-btn" disabled>Add card</button>
  </section>

  <ol class="m-cards" id="m-cards"></ol>
  <div class="m-empty" id="m-empty" hidden>No cards yet. Add your first one above.</div>
</div>
"""


def render() -> None:
    assert _mw and _page
    web = _mw.web
    web.set_bridge_command(on_cmd, _page)
    web.stdHtml(
        BODY,
        css=[],
        js=["js/vendor/jquery.min.js"],
        context=_page,
    )
    # Empty bottom bar on this screen.
    BottomBar(_mw, _mw.bottomWeb).draw(buf="", web_context=_bottom, link_handler=lambda _l: False)
    push_data()


def _rows_for_deck(did: DeckId) -> list[dict[str, Any]]:
    """All notes with cards in `did` (and its subdecks) via one SQL query.

    Fields are stored in `notes.flds` separated by \x1f. A note counts as
    suspended when every one of its cards is suspended (queue -1 is the lowest
    queue value, so max(queue) == -1 means all cards are suspended).
    """
    assert _mw
    col = _mw.col
    dids = [int(did)] + [int(child_id) for _name, child_id in col.decks.children(did)]
    placeholders = ",".join("?" * len(dids))
    rows = col.db.all(
        f"""select n.id, n.flds, max(c.queue)
            from cards c join notes n on n.id = c.nid
            where c.did in ({placeholders})
            group by n.id order by n.id""",
        *dids,
    )
    out = []
    for nid, flds, max_queue in rows:
        fields = flds.split("\x1f")
        out.append(
            {
                "id": int(nid),
                "front": fields[0] if fields else "",
                "back": fields[1] if len(fields) > 1 else "",
                "extra": max(0, len(fields) - 2),
                "suspended": max_queue == QUEUE_TYPE_SUSPENDED,
            }
        )
    return out


def collect_data() -> dict[str, Any]:
    assert _mw and _page
    col = _mw.col
    decks = [
        {"id": d.id, "name": d.name}
        for d in col.decks.all_names_and_ids(skip_empty_default=True, include_filtered=False)
    ]
    did = _page.deck_id or col.decks.get_current_id()
    if not any(d["id"] == did for d in decks) and decks:
        did = DeckId(decks[0]["id"])
        _page.deck_id = did
    name = col.decks.name_if_exists(did) or ""
    rows = _rows_for_deck(did) if name else []
    return {"decks": decks, "deck": int(did), "deckName": name, "rows": rows}


def push_data() -> None:
    assert _mw
    _mw.web.eval(f"window.mEdit && mEdit.render({json.dumps(collect_data())});")


# Commands from the page
######################################################################


def on_cmd(cmd: str) -> Any:
    assert _mw and _page
    if not cmd.startswith("m_edit:"):
        return False
    _, action, *rest = cmd.split(":", 2)
    arg = rest[0] if rest else ""

    if action == "deck":
        _page.deck_id = DeckId(int(arg))
        _mw.col.decks.select(_page.deck_id)
        push_data()
    elif action == "save":
        data = json.loads(arg)
        note = _mw.col.get_note(NoteId(int(data["id"])))
        fields = list(note.fields)
        if fields:
            fields[0] = data["front"]
        if len(fields) > 1:
            fields[1] = data["back"]
        note.fields = fields
        update_note(parent=_mw, note=note).run_in_background(initiator=_page)
    elif action == "add":
        data = json.loads(arg)
        _add(data.get("front", ""), data.get("back", ""))
    elif action == "delete":
        remove_notes(parent=_mw, note_ids=[NoteId(int(arg))]).success(
            lambda _: push_data()
        ).run_in_background(initiator=_page)
    elif action == "suspend":
        nid = NoteId(int(arg))
        cids = _mw.col.card_ids_of_note(nid)
        if not cids:
            return True
        is_suspended = all(_mw.col.get_card(c).queue == QUEUE_TYPE_SUSPENDED for c in cids)
        op = unsuspend_cards if is_suspended else suspend_cards
        op(parent=_mw, card_ids=cids).success(lambda _: push_data()).run_in_background(
            initiator=_page
        )
    elif action == "study":
        if _page.deck_id:
            _mw.col.decks.select(_page.deck_id)
        _mw.moveToState("overview")
    elif action == "browser":
        import aqt
        from anki.collection import SearchNode

        did = _page.deck_id or _mw.col.decks.get_current_id()
        name = _mw.col.decks.name_if_exists(did)
        search = (SearchNode(deck=name),) if name else None
        aqt.dialogs.open("Browser", _mw, search=search)
    return True


def _add(front: str, back: str) -> None:
    assert _mw and _page
    col = _mw.col
    if not front.strip() and not back.strip():
        return
    did = _page.deck_id or col.decks.get_current_id()
    defaults = col.defaults_for_adding(current_review_card=None)
    notetype = col.models.get(defaults.notetype_id) or col.models.current()
    note = col.new_note(notetype)
    fields = list(note.fields)
    if fields:
        fields[0] = front
    if len(fields) > 1:
        fields[1] = back
    note.fields = fields

    def added(_out: Any) -> None:
        push_data()
        _mw.web.eval("window.mEdit && mEdit.addedOk();")

    add_note(parent=_mw, note=note, target_deck_id=did).success(added).run_in_background(
        initiator=_page
    )
