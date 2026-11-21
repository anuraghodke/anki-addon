# Quiet .apkg import: no options dialog, no import log. The package is imported
# with the user's saved import presets and the deck list simply updates.
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from anki.collection import Collection, ImportAnkiPackageRequest, ImportLogWithChanges
from aqt.operations import CollectionOp
from aqt.utils import showWarning, tooltip

if TYPE_CHECKING:
    from aqt.main import AnkiQt

_mw: AnkiQt | None = None


def setup(mw: AnkiQt) -> None:
    global _mw
    _mw = mw
    from aqt.import_export import importing

    importing.ApkgImporter.do_import = staticmethod(quiet_import)  # type: ignore[method-assign]


def quiet_import(mw: AnkiQt, path: str) -> None:
    from aqt.import_export.importing import import_progress_update

    def op(col: Collection) -> ImportLogWithChanges:
        before = {d.id for d in col.decks.all_names_and_ids()}
        options = col._backend.get_import_anki_package_presets()
        result = col.import_anki_package(
            ImportAnkiPackageRequest(package_path=path, options=options)
        )
        _flatten_new_decks(col, before)
        return result

    def done(result: ImportLogWithChanges) -> None:
        log = result.log
        added = len(log.new)
        updated = len(log.updated)
        skipped = len(log.duplicate) + len(log.conflicting)
        parts = [f"{added} new note{'s' if added != 1 else ''}"]
        if updated:
            parts.append(f"{updated} updated")
        if skipped:
            parts.append(f"{skipped} already present")
        tooltip("Imported: " + ", ".join(parts), parent=mw, period=4000)

    def failed(err: Exception) -> None:
        showWarning(f"Import failed:\n{err}", parent=mw)

    (
        CollectionOp(parent=mw, op=op)
        .with_backend_progress(import_progress_update)
        .success(done)
        .failure(failed)
        .run_in_background()
    )


def _flatten_new_decks(col: Collection, before: set[int]) -> None:
    """Move decks the import created to the top level and drop empty parents.

    Shared packages often nest their deck under a wrapper like "Misc::Deck".
    We want every imported deck at the same level; users can group by dragging
    one deck onto another in the deck list.
    """
    created = [d for d in col.decks.all_names_and_ids() if d.id not in before]
    if not created:
        return
    # Deepest first so children are moved before their (soon empty) parents.
    created.sort(key=lambda d: d.name.count("::"), reverse=True)
    taken = {d.name.lower() for d in col.decks.all_names_and_ids()}
    for d in created:
        if "::" not in d.name:
            continue
        leaf = d.name.rsplit("::", 1)[1].strip() or d.name
        parent = d.name.rsplit("::", 1)[0].rsplit("::", 1)[-1]
        new_name = leaf
        if new_name.lower() in taken:
            new_name = f"{leaf} ({parent})"
        n = 2
        while new_name.lower() in taken:
            new_name = f"{leaf} ({parent} {n})"
            n += 1
        col.decks.rename(d.id, new_name)
        taken.add(new_name.lower())
    # Remove wrapper decks the import created that are now empty and childless.
    for d in sorted(created, key=lambda d: d.name.count("::"), reverse=True):
        deck = col.decks.get(d.id, default=False)
        if not deck or deck.get("dyn"):
            continue
        if col.decks.children(d.id) or col.decks.cids(d.id, children=True):
            continue
        col.decks.remove([d.id])
