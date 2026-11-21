# "Med School" study presets, applied to a deck from the Deck Options page.
#
# Everything shared lives in BASE; the two variants only move the knobs that
# genuinely change between phases (new cards/day, maximum interval, ordering,
# Easy Days). See the research notes in the conversation for the rationale.
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from anki.decks import DeckId

if TYPE_CHECKING:
    from aqt.main import AnkiQt

_mw: AnkiQt | None = None

PRESET_PREFIX = "Med School"

# Deck-config JSON keys (schema 11). Enum values follow deck_config.proto.
BASE: dict[str, Any] = {
    "new": {
        "delays": [10.0, 60.0],  # learning steps: 10m 1h
        "order": 1,  # sequential (NewCardOrder.Due)
        "ignoreReviewLimit": True,
    },
    "rev": {"perDay": 9999},
    "lapse": {
        "delays": [10.0],  # relearning: 10m
        "leechFails": 8,
        "leechAction": 1,  # tag only
        "minInt": 1,
    },
    "buryNew": True,
    "buryReviews": True,
    "buryInterdayLearning": True,
    "newMix": 1,  # new cards after reviews
    "interdayLearningMix": 0,  # mix with reviews
    "reviewOrder": 0,  # due date, then random
    "newGatherPriority": 0,  # deck
    "maxTaken": 60,
    "timer": 0,
    "desiredRetention": 0.90,
}

NORMAL_WEEK = [1.0] * 7  # Monday..Sunday

VARIANTS: dict[str, dict[str, Any]] = {
    "preclinical": {
        "label": "Preclinical",
        "blurb": "Following lectures: 60 new/day, 1-year max interval, lighter weekends.",
        "new": {"perDay": 60},
        "rev": {"maxIvl": 365},
        "newMix": 1,
        "interdayLearningMix": 0,
        "easyDaysPercentages": [1.0, 1.0, 1.0, 1.0, 1.0, 0.5, 0.5],
    },
    "dedicated": {
        "label": "Dedicated",
        "blurb": "Board study: 10 new/day, 60-day max interval, relearned cards first.",
        "new": {"perDay": 10},
        "rev": {"maxIvl": 60},
        "newMix": 1,
        "interdayLearningMix": 2,  # learning before reviews
        "easyDaysPercentages": NORMAL_WEEK,
    },
}


def setup(mw: AnkiQt) -> None:
    global _mw
    _mw = mw


def _merge(conf: dict[str, Any], values: dict[str, Any]) -> None:
    for key, val in values.items():
        if key in ("label", "blurb"):
            continue
        if isinstance(val, dict) and isinstance(conf.get(key), dict):
            conf[key].update(val)
        else:
            conf[key] = val


def apply(deck_id: DeckId, variant: str) -> str | None:
    """Apply BASE + variant to the deck's preset. Returns the preset name used.

    If the deck is still on a preset shared with other decks (e.g. "Default"),
    a new "Med School · <Variant>" preset is cloned so we never silently
    rewrite settings for unrelated decks.
    """
    assert _mw
    col = _mw.col
    spec = VARIANTS.get(variant)
    if not spec:
        return None
    name = f"{PRESET_PREFIX} · {spec['label']}"

    deck = col.decks.get(deck_id)
    if not deck or deck.get("dyn"):
        return None
    conf = col.decks.config_dict_for_deck_id(deck_id)
    users = [d for d in col.decks.all() if d.get("conf") == conf["id"] and not d.get("dyn")]
    if not conf["name"].startswith(PRESET_PREFIX) and len(users) > 1:
        new_id = col.decks.add_config_returning_id(name, clone_from=conf)
        conf = col.decks.get_config(new_id)
        assert conf is not None
        deck["conf"] = new_id
        col.decks.save(deck)

    _merge(conf, BASE)
    _merge(conf, spec)
    conf["name"] = name
    col.decks.update_config(conf)

    # FSRS is collection-wide; the preset assumes it.
    if not col.get_config("fsrs", False):
        col.set_config("fsrs", True)
    return name


def on_cmd(message: str) -> bool:
    """Handle `m_preset:<variant>` from the Deck Options page."""
    assert _mw
    if not message.startswith("m_preset:"):
        return False
    variant = message.split(":", 1)[1]
    dialog = _current_options_dialog()
    if dialog is None:
        return True
    deck_id = DeckId(dialog._deck["id"])
    if apply(deck_id, variant):
        # Reload the page so it reflects the new values; the picker highlights
        # the active variant on load.
        dialog.web.load_sveltekit_page(f"deck-options/{int(deck_id)}")
    return True


def active_variant(deck_id: DeckId) -> str | None:
    """Which variant the deck's preset currently matches by name, if any."""
    assert _mw
    try:
        name = _mw.col.decks.config_dict_for_deck_id(deck_id)["name"]
    except Exception:
        return None
    for key, spec in VARIANTS.items():
        if name == f"{PRESET_PREFIX} · {spec['label']}":
            return key
    return None


def _current_options_dialog() -> Any:
    from aqt.deckoptions import DeckOptionsDialog
    from aqt.qt import QApplication

    for w in QApplication.topLevelWidgets():
        if isinstance(w, DeckOptionsDialog) and w.isVisible():
            return w
    return None
