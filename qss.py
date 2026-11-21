# Shared Qt stylesheet for the add-on's own dialogs (Create, Log in).
# Uses palette roles so it follows light/dark mode, plus the accent blues.
import os

_WEB = os.path.join(os.path.dirname(__file__), "web")


def dialog_qss() -> str:
    """Stylesheet for the current theme (picks the matching chevron icon)."""
    from aqt.theme import theme_manager

    icon = "chevron-dark.svg" if theme_manager.night_mode else "chevron-light.svg"
    path = os.path.join(_WEB, icon).replace("\\", "/")
    return DIALOG_QSS + f"""
QComboBox::down-arrow {{
    image: url("{path}");
    width: 14px;
    height: 14px;
}}
"""

ACCENT = "#2597E2"
ACCENT_HOVER = "#1f86c9"
ACCENT_LIGHT = "#7ABEED"

DIALOG_QSS = f"""
QDialog {{
    background: palette(window);
}}
QLabel {{
    color: palette(window-text);
    background: transparent;
}}
QLabel#m_heading {{
    font-size: 14px;
    font-weight: 600;
}}
QLabel#m_hint {{
    color: palette(placeholder-text);
    font-size: 12px;
}}
QLineEdit, QComboBox {{
    min-height: 22px;
    padding: 5px 10px;
    border-radius: 8px;
    border: 1px solid palette(mid);
    background: palette(base);
    color: palette(text);
    selection-background-color: {ACCENT};
}}
QLineEdit:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    border: 0;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background: palette(base);
    color: palette(text);
    selection-background-color: {ACCENT};
    selection-color: white;
    border: 1px solid palette(mid);
}}
QPushButton {{
    min-height: 22px;
    padding: 5px 16px;
    border-radius: 15px;
    border: 1px solid palette(mid);
    background: transparent;
    color: palette(window-text);
    font-weight: 500;
}}
QPushButton:hover {{
    background: palette(midlight);
}}
QPushButton:disabled {{
    color: palette(placeholder-text);
    border-color: palette(midlight);
}}
QPushButton#m_primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: white;
    font-weight: 600;
}}
QPushButton#m_primary:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#m_primary:disabled {{
    background: transparent;
    border: 1px dashed palette(mid);
    color: palette(placeholder-text);
}}
QPushButton#m_link {{
    border: 0;
    padding: 0;
    min-height: 0;
    color: {ACCENT};
    background: transparent;
    text-align: left;
    font-weight: 500;
}}
QPushButton#m_link:hover {{
    text-decoration: underline;
    background: transparent;
}}
QFrame#m_rule {{
    background: palette(midlight);
    max-height: 1px;
    border: 0;
}}
"""


# In-window modal: dim the main window and centre the panel on top. Clicking
# the dimmed area or pressing Esc closes it; only the top-most modal reacts.
######################################################################


_ACTIVE: list[dict] = []  # currently presented modals, bottom to top


def present_modal(dialog) -> None:  # type: ignore[no-untyped-def]
    from aqt.qt import (
        QColor,
        QEasingCurve,
        QEvent,
        QGraphicsOpacityEffect,
        QObject,
        QPainter,
        QPoint,
        Qt,
        QVariantAnimation,
        QWidget,
    )

    parent = dialog.parentWidget()
    if parent is not None:
        host = parent.window()
    else:
        # Anki's Browser is created without a parent; host it on the main window.
        import aqt

        host = aqt.mw
        if host is None:
            dialog.show()
            return
    animate = True  # brief (≤200ms) fades; kept on even with "reduce motion"
    DIM = 110
    RADIUS = 14  # keep in sync with MODAL_QSS border-radius
    IN_MS, OUT_MS, RISE = 200, 150, 18

    # Web views don't survive being re-parented into another window (they go
    # blank on screen), so dialogs containing one stay top-level. Any modal
    # opened while a floating one is active must float too, or it would end
    # up hidden underneath it.
    try:
        from aqt.qt import QWebEngineView

        has_web = dialog.findChild(QWebEngineView) is not None
    except Exception:
        has_web = False
    floating = has_web or any(m["floating"] for m in _ACTIVE)
    record = {"dialog": dialog, "floating": floating}
    _ACTIVE.append(record)

    def _dismiss() -> None:
        """Cancel like Esc: reject() for dialogs, close() for main windows."""
        if hasattr(dialog, "reject"):
            dialog.reject()
        else:
            dialog.close()

    def _host_global_rect():  # type: ignore[no-untyped-def]
        from aqt.qt import QRect

        return QRect(host.mapToGlobal(host.rect().topLeft()), host.size())

    class Overlay(QWidget):
        def __init__(self) -> None:
            if floating:
                # A translucent tool window covering the main window, so it
                # dims whatever is below it, including an earlier floating modal.
                super().__init__(host)
                self.setWindowFlags(
                    Qt.WindowType.Tool
                    | Qt.WindowType.FramelessWindowHint
                    | Qt.WindowType.NoDropShadowWindowHint
                )
                self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
                self.setGeometry(_host_global_rect())
            else:
                super().__init__(host)
                self.setGeometry(host.rect())
            self.alpha = 0
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        def paintEvent(self, _e) -> None:  # type: ignore[no-untyped-def]
            p = QPainter(self)
            p.fillRect(self.rect(), QColor(0, 0, 0, self.alpha))

        def mousePressEvent(self, e) -> None:  # type: ignore[no-untyped-def]
            if not dialog.geometry().contains(e.position().toPoint()):
                _dismiss()

        def keyPressEvent(self, e) -> None:  # type: ignore[no-untyped-def]
            if e.key() == Qt.Key.Key_Escape:
                _dismiss()
            else:
                super().keyPressEvent(e)

        def resizeEvent(self, _e) -> None:  # type: ignore[no-untyped-def]
            _center()

    overlay = Overlay()

    from aqt.qt import QToolButton

    close_btn = QToolButton(overlay)
    close_btn.setObjectName("m_close")
    close_btn.setText("\u2715")
    close_btn.setToolTip("Close (Esc)")
    close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    close_btn.setFixedSize(28, 28)
    close_btn.setStyleSheet(CLOSE_QSS)
    close_btn.clicked.connect(lambda: _dismiss())

    def _place_close() -> None:
        g = dialog.geometry()
        if floating:
            g.moveTopLeft(overlay.mapFromGlobal(g.topLeft()))
        if floating:
            # overlay-level widgets would be hidden under the floating window;
            # put the close button inside the dialog instead.
            close_btn.setParent(dialog)
            close_btn.move(dialog.width() - 28 - 10, 10)
        else:
            close_btn.move(g.right() - 28 - 10, g.top() + 10)
        close_btn.raise_()

    class HostWatch(QObject):
        def eventFilter(self, _o, e):  # type: ignore[no-untyped-def]
            if e is not None and e.type() in (QEvent.Type.Resize, QEvent.Type.Move):
                overlay.setGeometry(_host_global_rect() if floating else host.rect())
                _center()
            return False

    watch = HostWatch(overlay)
    host.installEventFilter(watch)

    def _fit() -> None:
        # Natural size, respecting minimums; keep a larger size the dialog
        # already chose (e.g. restored geometry); cap to the overlay.
        want = dialog.sizeHint().expandedTo(dialog.minimumSize())
        if getattr(dialog, "_m_keep_size", False):
            want = want.expandedTo(dialog.size())
        margin = 48
        want.setWidth(min(want.width(), overlay.width() - margin))
        want.setHeight(min(want.height(), overlay.height() - margin))
        dialog.resize(want)

    def _target_pos() -> QPoint:
        _fit()
        size = dialog.size()
        return QPoint(
            (overlay.width() - size.width()) // 2,
            max(20, (overlay.height() - size.height()) // 2),
        )

    def _center() -> None:
        if not state["animating"]:
            dialog.move(_to_screen(_target_pos()))
            _place_close()

    state = {"animating": False, "closing": False, "anims": []}

    def _teardown() -> None:
        if record in _ACTIVE:
            _ACTIVE.remove(record)
        host.removeEventFilter(watch)
        overlay.hide()
        overlay.deleteLater()

    dialog.setObjectName("m_modal")
    dialog.setStyleSheet(dialog.styleSheet() + MODAL_QSS)
    if floating:
        # Parent to the overlay window so the panel always stacks above it.
        dialog.setParent(overlay)
        dialog.setWindowFlags(
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.NoDropShadowWindowHint
        )
        dialog.setWindowModality(Qt.WindowModality.NonModal)
        fx = None

        # Rounded corners for a real window: clip its shape with a mask, which
        # works for web views too (translucent backgrounds do not).
        from aqt.qt import QPainterPath, QRegion, QRectF

        def _apply_mask() -> None:
            path = QPainterPath()
            path.addRoundedRect(QRectF(dialog.rect()), RADIUS, RADIUS)
            dialog.setMask(QRegion(path.toFillPolygon().toPolygon()))

        class MaskWatch(QObject):
            def eventFilter(self, _o, e):  # type: ignore[no-untyped-def]
                if e is not None and e.type() == QEvent.Type.Resize:
                    _apply_mask()
                return False

        dialog.installEventFilter(MaskWatch(dialog))
    else:
        # Embed the dialog in the overlay as a plain child widget.
        dialog.setParent(overlay)
        dialog.setWindowFlags(Qt.WindowType.Widget)
        fx = QGraphicsOpacityEffect(dialog)
        dialog.setGraphicsEffect(fx)

    def _to_screen(p: QPoint) -> QPoint:
        return overlay.mapToGlobal(p) if floating else p

    def _apply(t: float, opening: bool) -> None:
        """Apply progress t in [0,1] of the open (or close) transition."""
        k = t if opening else 1.0 - t
        overlay.alpha = int(DIM * k)
        overlay.update()
        if fx is not None:
            fx.setOpacity(k)
        else:
            dialog.setWindowOpacity(k)
        rise = RISE if opening else RISE // 2
        dialog.move(_to_screen(_target_pos() + QPoint(0, int(rise * (1.0 - k)))))

    def _run(opening: bool, ms: int, on_done) -> None:  # type: ignore[no-untyped-def]
        """One QVariantAnimation drives dim, opacity and position together."""
        state["animating"] = True
        anim = QVariantAnimation(overlay)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setDuration(ms)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(lambda v: _apply(float(v), opening))

        def finished() -> None:
            _apply(1.0, opening)
            state["animating"] = False
            on_done()

        anim.finished.connect(finished)
        state["anims"] = [anim]
        anim.start()

    if not hasattr(dialog, "done"):
        # QMainWindow (Browser): no done(); tear the overlay down when it hides.
        class HideWatch(QObject):
            def eventFilter(self, _o, e):  # type: ignore[no-untyped-def]
                if e is not None and e.type() == QEvent.Type.Hide and not state["closing"]:
                    state["closing"] = True
                    _teardown()
                return False

        dialog.installEventFilter(HideWatch(dialog))

    # Closing: animate out, then run QDialog's real done().
    orig_done = getattr(dialog, "done", None)

    def done(result: int) -> None:
        if state["closing"]:
            return
        state["closing"] = True
        if not animate:
            orig_done(result)
            _teardown()
            return
        close_btn.hide()
        _run(False, OUT_MS, lambda: (orig_done(result), _teardown()))

    if orig_done is not None:
        dialog.done = done  # type: ignore[method-assign]

    overlay.show()
    overlay.raise_()
    dialog.show()
    _fit()
    dialog.raise_()
    if floating:
        dialog.activateWindow()
        _apply_mask()
    dialog.setFocus()

    close_btn.hide()
    if animate:
        if fx is not None:
            fx.setOpacity(0.0)
        else:
            dialog.setWindowOpacity(0.0)
        dialog.move(_to_screen(_target_pos() + QPoint(0, RISE)))
        _run(True, IN_MS, lambda: (_place_close(), close_btn.show()))
    else:
        overlay.alpha = DIM
        overlay.update()
        dialog.move(_to_screen(_target_pos()))
        _place_close()
        close_btn.show()


CLOSE_QSS = """
QToolButton#m_close {
    border: 0;
    border-radius: 14px;
    background: transparent;
    color: palette(placeholder-text);
    font-size: 14px;
    font-weight: 600;
}
QToolButton#m_close:hover {
    background: palette(midlight);
    color: palette(window-text);
}
"""

MODAL_QSS = """
QDialog#m_modal {
    background: palette(window);
    border: 1px solid palette(mid);
    border-radius: 14px;
}
"""


# Adopt Anki's own dialogs (Stats, Deck Options, Preferences, ...) into the
# same overlay modal, so every pop-up looks and behaves the same way.
######################################################################

# Native/system style dialogs and transient ones that must stay as windows.
_SKIP_CLASSES = {
    "QMessageBox",
    "QFileDialog",
    "QInputDialog",
    "QColorDialog",
    "QFontDialog",
    "QErrorMessage",
    "QProgressDialog",
    "ProgressDialog",
    "QWizard",
    "QPrintDialog",
}


def install_global_modals(mw) -> None:  # type: ignore[no-untyped-def]
    from aqt.qt import QApplication, QDialog, QEvent, QObject, QTimer

    app = QApplication.instance()
    if app is None:
        return

    def _should_adopt(w) -> bool:  # type: ignore[no-untyped-def]
        is_browser = type(w).__name__ == "Browser"  # QMainWindow, Anki's card browser
        if not (isinstance(w, QDialog) or is_browser) or not w.isWindow():
            return False
        if getattr(w, "_m_adopted", False):
            return False
        for cls in type(w).__mro__:
            if cls.__name__ in _SKIP_CLASSES:
                return False
        parent = w.parentWidget()
        if parent is None:
            return is_browser
        return parent.window() is mw

    class Adopter(QObject):
        def eventFilter(self, obj, event):  # type: ignore[no-untyped-def]
            if event is not None and event.type() == QEvent.Type.Show and _should_adopt(obj):
                obj._m_adopted = True
                obj._m_keep_size = True
                # Finish the native show first, then re-present inside the overlay.
                QTimer.singleShot(0, lambda d=obj: _adopt(d))
            return False

    def _adopt(dialog) -> None:  # type: ignore[no-untyped-def]
        if not dialog.isVisible():
            return
        dialog.hide()
        dialog.setStyleSheet(dialog.styleSheet() + dialog_qss())
        present_modal(dialog)

    adopter = Adopter(mw)
    app.installEventFilter(adopter)
    mw._m_modal_adopter = adopter
