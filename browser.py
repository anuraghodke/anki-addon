# Browse window: decks-only sidebar that behaves like a file tree, a lean
# card table, and a breadcrumb that says where you are.
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from aqt import gui_hooks
from aqt.browser import (
    Browser,
    SearchContext,
    SidebarItem,
    SidebarItemType,
    SidebarStage,
    SidebarTreeView,
)
from anki.consts import QUEUE_TYPE_SUSPENDED
from aqt.operations.deck import add_deck
from aqt.qt import (
    QAbstractItemView,
    QEvent,
    QHBoxLayout,
    QLabel,
    QMenu,
    QModelIndex,
    QObject,
    QPushButton,
    Qt,
    QTimer,
    QWidget,
    qconnect,
)
from aqt.utils import getOnlyText, tr

if TYPE_CHECKING:
    from aqt.main import AnkiQt

CARD_COLUMNS = ["noteFld", "noteTags", "deck"]
NOTE_COLUMNS = ["noteFld", "noteTags", "deck"]
# Bump when the default column set changes so existing installs pick it up.
COLUMNS_VERSION = 2
COLUMNS_FLAG = "browser_columns_version"

_mw: AnkiQt | None = None


def setup(mw: AnkiQt) -> None:
    global _mw
    _mw = mw
    _patch_sidebar_drag()
    _patch_sidebar_style()
    _patch_no_current_deck()
    gui_hooks.browser_will_build_tree.append(on_will_build_tree)
    gui_hooks.browser_will_show.append(on_browser_will_show)
    gui_hooks.browser_did_search.append(on_did_search)
    gui_hooks.browser_did_change_row.append(on_row_changed)
    gui_hooks.browser_did_fetch_row.append(on_fetch_row)
    gui_hooks.browser_sidebar_will_show_context_menu.append(on_sidebar_menu)
    gui_hooks.profile_did_open.append(apply_default_columns)
    if mw.col:
        apply_default_columns()


# Columns: show a lot less per card
######################################################################


def apply_default_columns() -> None:
    """Trim the table to sort field / tags / deck (re-applied when the set changes)."""
    assert _mw
    conf = _mw.addonManager.getConfig(__name__) or {}
    if conf.get(COLUMNS_FLAG, 0) >= COLUMNS_VERSION:
        return
    _mw.col.set_browser_card_columns(CARD_COLUMNS)
    _mw.col.set_browser_note_columns(NOTE_COLUMNS)
    conf[COLUMNS_FLAG] = COLUMNS_VERSION
    _mw.addonManager.writeConfig(__name__, conf)


# Sidebar: decks only
######################################################################


def on_will_build_tree(
    handled: bool, _root: SidebarItem, stage: SidebarStage, _browser: Browser
) -> bool:
    if handled:
        return True
    # Claim every stage except the deck tree so Anki skips building it.
    return stage not in (SidebarStage.ROOT, SidebarStage.DECKS)


def _patch_sidebar_style() -> None:
    """Anki re-applies its own sidebar style on theme change; layer ours on top.

    Patching the method (rather than hooking theme_did_change per window) avoids
    touching a sidebar that has already been destroyed with its Browse window.
    """
    orig = SidebarTreeView._setup_style

    def _setup_style(self: SidebarTreeView) -> None:
        orig(self)
        self.setStyleSheet(SIDEBAR_QSS)

    SidebarTreeView._setup_style = _setup_style  # type: ignore[method-assign]


def _patch_no_current_deck() -> None:
    """Never show the abstract "current deck" in Browse.

    - The sidebar's "Current Deck" entry is removed; the real decks are listed.
    - The default search names the selected deck explicitly instead of the
      opaque `deck:current`, so the search box and breadcrumb read naturally.
    """
    from anki.collection import SearchNode

    orig_tree = SidebarTreeView._deck_tree

    def _deck_tree(self: SidebarTreeView, root: SidebarItem) -> None:
        # Let Anki build "Decks > Current Deck, deck, deck..." then hoist the
        # decks to the top level and drop the header and "Current Deck".
        orig_tree(self, root)
        if not root.children or root.children[-1].item_type != SidebarItemType.DECK_ROOT:
            return
        section = root.children.pop()
        for child in section.children:
            if child.item_type != SidebarItemType.DECK_CURRENT:
                root.add_child(child)  # re-add so parent/row bookkeeping is right

    SidebarTreeView._deck_tree = _deck_tree  # type: ignore[method-assign]

    # Without the "Decks" header there is no row to drop onto for "move to top
    # level"; allow dropping into the empty area of the sidebar instead.
    from aqt.browser.sidebar import SidebarModel

    orig_flags = SidebarModel.flags

    def flags(self: SidebarModel, index: Any) -> Any:
        if not index.isValid():
            f = orig_flags(self, index)
            if SidebarItemType.DECK_ROOT in self.sidebar.valid_drop_types:
                from aqt.qt import Qt

                f |= Qt.ItemFlag.ItemIsDropEnabled
            return f
        return orig_flags(self, index)

    SidebarModel.flags = flags  # type: ignore[method-assign]

    orig_drop = SidebarTreeView.handle_drag_drop

    def handle_drag_drop(self: SidebarTreeView, sources: list[SidebarItem], target: Any) -> bool:
        if target is None or target.item_type == SidebarItemType.ROOT:
            top = SidebarItem("", "", item_type=SidebarItemType.DECK_ROOT, id=0)
            return self._handle_drag_drop_decks(sources, top)
        return orig_drop(self, sources, target)

    SidebarTreeView.handle_drag_drop = handle_drag_drop  # type: ignore[method-assign]

    orig_default = Browser._default_search

    def _default_search(self: Browser, card: Any = None) -> None:
        from anki.collection import Config

        if self.col.get_config_string(Config.String.DEFAULT_SEARCH_TEXT).strip():
            return orig_default(self, card)
        did = self.col.decks.get_current_id()
        name = self.col.decks.name_if_exists(did)
        # The empty "Default" deck is hidden from the deck list; prefer a real one.
        if name and did == 1 and not self.col.decks.cids(did, children=True):
            visible = self.col.decks.all_names_and_ids(skip_empty_default=True, include_filtered=False)
            if visible:
                name = visible[0].name
        if not name:
            return orig_default(self, card)
        search = self.col.build_search_string(SearchNode(deck=name))
        if card is not None:
            search = gui_hooks.default_search(search, card)
        self.search_for(search, "")

    Browser._default_search = _default_search  # type: ignore[method-assign]


def _patch_sidebar_drag() -> None:
    """Allow drag and drop in the default (search) tool as well."""
    prop = SidebarTreeView.tool
    assert isinstance(prop, property) and prop.fset

    def fset(self: SidebarTreeView, tool) -> None:  # type: ignore[no-untyped-def]
        prop.fset(self, tool)  # type: ignore[misc]
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        # With no root expander arrows, double-click is how groups open/close.
        self.setExpandsOnDoubleClick(True)

    SidebarTreeView.tool = property(prop.fget, fset)  # type: ignore[assignment]


SIDEBAR_QSS = """
QTreeView {
    border: 0;
    padding: 6px 4px 6px 2px;
    outline: 0;
    show-decoration-selected: 1;
}
QTreeView::item {
    padding: 5px 6px;
    border-radius: 6px;
    margin: 1px 4px 1px 0;
}
QTreeView::item:hover { background: palette(midlight); }
QTreeView::item:selected {
    background: palette(highlight);
    color: palette(highlighted-text);
}
QTreeView::branch { background: transparent; }
"""

TABLE_QSS = """
QTableView {
    border: 0;
    gridline-color: transparent;
    selection-background-color: palette(highlight);
    outline: 0;
}
QTableView::item { padding: 0 10px; border: 0; }
QHeaderView::section {
    padding: 7px 10px;
    border: 0;
    border-bottom: 1px solid palette(mid);
    background: palette(window);
    font-weight: 600;
}
"""

CRUMB_QSS = """
QLabel {
    padding: 6px 12px 4px;
    color: palette(mid);
    font-size: 12px;
}
"""

SUSPEND_BTN_QSS = """
QPushButton {
    padding: 3px 12px;
    border-radius: 11px;
    border: 1px solid palette(mid);
    background: transparent;
    color: palette(text);
    font-size: 12px;
    font-weight: 500;
}
QPushButton:hover { background: palette(midlight); }
QPushButton:checked {
    background: #f5d76e;
    border-color: #d8b84a;
    color: #3b2f00;
}
QPushButton:disabled { color: palette(mid); border-color: palette(midlight); }
"""


LAYOUT_FLAG = "browser_layout_version"
LAYOUT_VERSION = 2
# Fractions of the window width: sidebar / table / editor
LAYOUT = (0.20, 0.58, 0.22)


def on_browser_will_show(browser: Browser) -> None:
    _style_sidebar(browser)
    _style_search(browser)
    _style_table(browser)
    _add_breadcrumb(browser)
    # Anki restores its saved geometry after this hook, so apply ours afterwards;
    # the modal presenter may also resize the window shortly after, so run twice.
    QTimer.singleShot(80, lambda: _apply_layout(browser))
    QTimer.singleShot(600, lambda: _apply_layout(browser))


def _apply_layout(browser: Browser) -> None:
    """Give the panes sensible proportions the first time; keep the sidebar usable always."""
    assert _mw
    dock = browser.sidebarDockWidget
    splitter = browser.form.splitter
    total = browser.width()
    if total <= 0:
        return
    side, table, editor = (int(total * f) for f in LAYOUT)

    conf = _mw.addonManager.getConfig(__name__) or {}
    first_time = conf.get(LAYOUT_FLAG, 0) < LAYOUT_VERSION
    too_narrow = dock.width() < 180
    sizes = splitter.sizes()
    editor_squeezed = len(sizes) == 2 and (sizes[1] < 160 or sizes[0] < 240)

    if first_time or too_narrow:
        browser.resizeDocks([dock], [side], Qt.Orientation.Horizontal)
    if (first_time or editor_squeezed) and splitter.orientation() == Qt.Orientation.Horizontal:
        splitter.setSizes([table, editor])
    if first_time:
        conf[LAYOUT_FLAG] = LAYOUT_VERSION
        _mw.addonManager.writeConfig(__name__, conf)


def _style_sidebar(browser: Browser) -> None:
    sb = browser.sidebar
    sb.setIndentation(18)
    # No expander column at the root: top-level decks sit flush left. Groups
    # still expand via double-click or the keyboard; their children indent.
    sb.setRootIsDecorated(False)
    sb.setAnimated(True)
    sb.setStyleSheet(SIDEBAR_QSS)
    # Click a selected deck again to rename it, like a file manager.
    sb.setEditTriggers(
        QAbstractItemView.EditTrigger.EditKeyPressed
        | QAbstractItemView.EditTrigger.SelectedClicked
    )
    sb.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
    sb.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    sb.setDragEnabled(True)
    sb.setAcceptDrops(True)
    sb.setDropIndicatorShown(True)


def _style_search(browser: Browser) -> None:
    """Keep the search combo from sizing itself to its longest history entry.

    Anki stores searches like huge `nid:...` lists in the history; with Qt's
    default policy that makes the combo's minimum width enormous and the
    splitter can then never give the editor any room.
    """
    from aqt.qt import QComboBox

    se = browser.form.searchEdit
    se.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
    se.setMinimumContentsLength(12)


def _style_table(browser: Browser) -> None:
    view = browser.form.tableView
    view.setAlternatingRowColors(True)
    view.setShowGrid(False)
    view.setStyleSheet(TABLE_QSS)
    vh = view.verticalHeader()
    if vh:
        vh.setDefaultSectionSize(max(vh.defaultSectionSize(), 32))
    hh = view.horizontalHeader()
    if hh:
        hh.setStretchLastSection(False)
        hh.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hh.setMinimumSectionSize(90)
    # Keep columns proportional to the table, like a file manager.
    filt = _ResizeFilter(browser)
    view.installEventFilter(filt)
    browser._m_resize_filter = filt  # type: ignore[attr-defined]
    QTimer.singleShot(0, lambda: _fit_columns(browser))


class _ResizeFilter(QObject):
    def __init__(self, browser: Browser) -> None:
        super().__init__(browser)
        self._browser = browser

    def eventFilter(self, _obj: QObject | None, event: QEvent | None) -> bool:
        if event and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, lambda: _fit_columns(self._browser))
        return False


def _fit_columns(browser: Browser) -> None:
    """Split the visible width: 45% sort field, 20% middle columns, rest for the last.

    Anki keeps the last column stretched, so we only size the leading ones.
    """
    view = browser.form.tableView
    hh = view.horizontalHeader()
    viewport = view.viewport()
    if not hh or not viewport or hh.count() < 2:
        return
    width = viewport.width() or view.width()
    if width <= 0:
        return
    hh.resizeSection(hh.logicalIndex(0), int(width * 0.45))
    middle = hh.count() - 2
    if middle > 0:
        each = int(width * 0.2 / middle)
        for visual in range(1, hh.count() - 1):
            hh.resizeSection(hh.logicalIndex(visual), each)


# Breadcrumb above the table
######################################################################

_DECK_RE = re.compile(r'(?:^|\s)-?deck:(?:"([^"]+)"|(\S+))', re.IGNORECASE)


def _add_breadcrumb(browser: Browser) -> None:
    """Row above the table: breadcrumb on the left, suspend toggle on the right."""
    label = QLabel()
    label.setObjectName("m_crumb")
    label.setStyleSheet(CRUMB_QSS)
    label.setTextFormat(Qt.TextFormat.PlainText)

    btn = QPushButton("Suspend")
    btn.setCheckable(True)
    btn.setToolTip("Suspend or unsuspend the selected cards (Ctrl+J)")
    btn.setStyleSheet(SUSPEND_BTN_QSS)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setEnabled(False)
    # Route through Anki's own checkable action so selection/editor handling
    # and the menu state stay in sync.
    qconnect(btn.clicked, lambda _c: browser.form.actionToggle_Suspend.trigger())

    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(0, 0, 10, 0)
    h.setSpacing(8)
    h.addWidget(label, 1)
    h.addWidget(btn, 0)

    browser.form.verticalLayout_2.insertWidget(1, row)
    browser._m_crumb = label  # type: ignore[attr-defined]
    browser._m_suspend = btn  # type: ignore[attr-defined]


def on_row_changed(browser: Browser) -> None:
    btn: QPushButton | None = getattr(browser, "_m_suspend", None)
    if not btn:
        return
    card = browser.current_card
    has_sel = browser.table.len_selection() > 0
    suspended = bool(card and card.queue == QUEUE_TYPE_SUSPENDED)
    btn.setEnabled(has_sel)
    btn.blockSignals(True)
    btn.setChecked(suspended)
    btn.blockSignals(False)
    btn.setText("Suspended" if suspended else "Suspend")


# Suspended rows: a marker next to the field text, on top of Anki's row tint.
######################################################################

SUSPENDED_MARK = "\u23f8 "  # pause symbol


def on_fetch_row(card_or_note_id: Any, is_note: bool, row: Any, columns: Any) -> None:
    assert _mw
    try:
        if is_note:
            cards = _mw.col.card_ids_of_note(card_or_note_id)
            suspended = bool(cards) and all(
                _mw.col.get_card(c).queue == QUEUE_TYPE_SUSPENDED for c in cards
            )
        else:
            suspended = _mw.col.get_card(card_or_note_id).queue == QUEUE_TYPE_SUSPENDED
    except Exception:
        return
    if not suspended:
        return
    for i, key in enumerate(columns):
        if key == "noteFld" and i < len(row.cells):
            cell = row.cells[i]
            if not cell.text.startswith(SUSPENDED_MARK):
                cell.text = SUSPENDED_MARK + cell.text
            break


def _describe_search(search: str) -> str:
    search = search.strip()
    if not search or search in ("deck:*", "deck:_*", 'deck:"*"'):
        return "All decks"
    m = _DECK_RE.search(search)
    if m:
        name = m.group(1) or m.group(2)
        if name == "current":
            return "Current deck"
        crumbs = " › ".join(name.replace("\\:", ":").split("::"))
        rest = _DECK_RE.sub("", search).strip()
        return f"{crumbs}  ·  {rest}" if rest else crumbs
    return search


def on_did_search(context: SearchContext) -> None:
    browser = context.browser
    label: QLabel | None = getattr(browser, "_m_crumb", None)
    if not label:
        return
    n = len(context.ids) if context.ids is not None else browser.table.len()
    unit = "notes" if browser.table.is_notes_mode() else "cards"
    label.setText(f"{_describe_search(context.search)}  ·  {n:,} {unit}")


# Sidebar context menu: new subdeck
######################################################################


def on_sidebar_menu(
    sidebar: SidebarTreeView, menu: QMenu, item: SidebarItem, _index: QModelIndex
) -> None:
    if item.item_type not in (SidebarItemType.DECK, SidebarItemType.DECK_ROOT):
        return
    parent = item.full_name if item.item_type == SidebarItemType.DECK else ""

    def new_deck() -> None:
        name = getOnlyText(tr.decks_new_deck_name(), default="").strip()
        if not name:
            return
        full = f"{parent}::{name}" if parent else name
        add_deck(parent=sidebar, name=full).success(
            lambda _: sidebar.refresh()
        ).run_in_background()

    label = "New subdeck…" if parent else "New deck…"
    first = menu.actions()[0] if menu.actions() else None
    action = menu.addAction(label)
    qconnect(action.triggered, new_deck)
    if first:
        menu.removeAction(action)
        menu.insertAction(first, action)
