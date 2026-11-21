# Modern Anki: a cleaner, more direct Anki desktop UI.
#
# Modules:
#   ui        - top/bottom bars, deck list, overview, reviewer card, theme toggle, login
#   browser   - Browse ("Advanced") window: decks-only sidebar, lean table, layout
#   create    - "New" modal (create / import a deck)
#   editpage  - "Edit" page: Quizlet-style card list with inline editing
#   importing - silent .apkg import, flattening imported deck hierarchies
#   presets   - Med School study presets for Deck Options
#   qss       - shared Qt styling and the overlay modal presenter
from aqt import mw

from . import browser, create, editpage, importing, presets, ui

ui.setup(mw)
browser.setup(mw)
create.setup(mw)
importing.setup(mw)
editpage.setup(mw)
presets.setup(mw)

from .qss import install_global_modals

install_global_modals(mw)


