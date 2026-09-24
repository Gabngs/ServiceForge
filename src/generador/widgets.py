"""Widgets de Qt reutilizables por la GUI (sin lógica de la herramienta)."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QRect, Qt, QTimer
from PySide6.QtWidgets import QComboBox, QCompleter

_MIN_POPUP_WIDTH = 240
_MAX_POPUP_WIDTH = 640


class SearchableComboBox(QComboBox):
    """Combo que se abre con TODAS las opciones y se puede escribir para filtrar
    (como el `p-select` con filtro de PrimeNG): con listas largas -- las tablas
    de una BD con cientos de tablas -- buscar con el scroll es tedioso.

    - Un clic en el campo, en la flecha o la tecla Abajo abre la lista completa;
      al escribir se va filtrando, por coincidencia en cualquier parte del
      texto (no solo el prefijo) y sin distinguir mayúsculas.
    - Al entrar al campo se selecciona el valor actual: se puede escribir
      encima sin borrarlo antes.
    - Al confirmar (Enter, elegir del popup o salir del campo) el texto tiene
      que ser un ítem de la lista -- exacto, o el único que contiene lo escrito.
      Si no, vuelve al último valor válido, así el combo nunca queda con texto
      que no corresponde a nada (salvo `allow_free_text=True`, para campos donde
      escribir un valor que no está en la lista es legítimo).
    - `setCurrentText` selecciona el ítem igual que en un combo no editable,
      así `currentIndexChanged` sirve tanto para cambios del usuario como
      programáticos (en un combo editable `currentTextChanged`, en cambio, se
      dispara con cada tecla)."""

    def __init__(self, parent=None, *, allow_free_text: bool = False) -> None:
        super().__init__(parent)
        self._allow_free_text = allow_free_text
        self.setEditable(True)
        self.setInsertPolicy(QComboBox.NoInsert)
        self.setMaxVisibleItems(15)

        completer = QCompleter(self.model(), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        self.setCompleter(completer)

        self.lineEdit().editingFinished.connect(self._commit_typed_text)
        self._select_all_on_release = False
        self.lineEdit().installEventFilter(self)

    # ------------------------------------------------------------ popup
    def showPopup(self) -> None:  # noqa: N802 — override Qt
        """La lista desplegable ES el popup del completer, así abre con todas las
        opciones y sigue filtrando al escribir (el popup nativo de QComboBox no filtra)."""
        completer = self.completer()
        if completer is None or self.count() == 0:
            return
        completer.setCompletionPrefix("")
        # Los nombres largos (tablas, clases) no caben en el ancho del campo.
        widest = max((self.fontMetrics().horizontalAdvance(self.itemText(i)) for i in range(self.count())), default=0)
        width = min(max(self.width(), widest + 48, _MIN_POPUP_WIDTH), _MAX_POPUP_WIDTH)
        completer.complete(QRect(0, 0, width, self.lineEdit().height()))
        # No se preselecciona el ítem actual en el popup: resaltarlo hace que el
        # completer reescriba el texto del campo y se pierde la selección con la que
        # se entra (para poder escribir encima sin borrar).

    def _popup_visible(self) -> bool:
        completer = self.completer()
        return completer is not None and completer.popup().isVisible()

    # ----------------------------------------------------------- eventos
    def eventFilter(self, watched, event) -> bool:  # noqa: N802 — override Qt
        if watched is self.lineEdit():
            kind = event.type()
            if kind == QEvent.MouseButtonPress and not watched.hasFocus():
                # El clic que da el foco reposiciona el cursor: se selecciona al soltar.
                self._select_all_on_release = True
            elif kind == QEvent.MouseButtonRelease:
                # Cada clic que abre la lista deja el valor seleccionado, tenga o no ya el
                # foco: lo siguiente que se escribe reemplaza el valor, no se agrega en medio.
                opens_list = not self._popup_visible()
                if self._select_all_on_release or opens_list:
                    self._select_all_on_release = False
                    watched.selectAll()
                if opens_list:
                    QTimer.singleShot(0, self.showPopup)
            elif kind == QEvent.KeyPress and event.key() == Qt.Key_Down and not self._popup_visible():
                QTimer.singleShot(0, self.showPopup)
        return super().eventFilter(watched, event)

    def focusInEvent(self, event) -> None:  # noqa: N802 — override Qt
        # Entrada con Tab o al activarse la ventana (el clic se maneja arriba).
        # QComboBox reenvía este evento al QLineEdit sin pasar por el filtro.
        super().focusInEvent(event)
        if event.reason() not in (Qt.MouseFocusReason, Qt.PopupFocusReason):
            QTimer.singleShot(0, self.lineEdit().selectAll)

    # ------------------------------------------------------ selección
    def setCurrentText(self, text: str) -> None:  # noqa: N802 — override Qt
        index = self.findText(text, Qt.MatchExactly)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            super().setCurrentText(text)

    def _matching_index(self, text: str) -> int:
        index = self.findText(text, Qt.MatchFixedString)  # exacto, sin distinguir mayúsculas
        if index >= 0:
            return index
        needle = text.lower()
        contains = [i for i in range(self.count()) if needle in self.itemText(i).lower()]
        return contains[0] if len(contains) == 1 else -1

    def _commit_typed_text(self) -> None:
        if self._allow_free_text:
            return
        text = self.lineEdit().text().strip()
        index = self._matching_index(text) if text else -1
        if index >= 0:
            self.setCurrentIndex(index)
            self.lineEdit().setText(self.itemText(index))
        else:
            self.lineEdit().setText(self.itemText(self.currentIndex()) if self.currentIndex() >= 0 else "")
