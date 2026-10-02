"""Editor for the steps of the batch tool."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMenu, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

from . import icons, theme

ROLE_TOOL = Qt.ItemDataRole.UserRole


class PipelineEditor(QWidget):
    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from pdftoolbox.tools.batch import chainable_tools

        self.tools = {t.id: t for t in chainable_tools()}
        self.forms = {}

        self.list = QListWidget()
        self.list.setMaximumHeight(170)
        self.list.currentRowChanged.connect(self._select)
        self.stack = QStackedWidget()
        empty = QLabel("Add steps. Each file goes through them in order, top to bottom.")
        empty.setObjectName("Muted")
        empty.setWordWrap(True)
        self.stack.addWidget(empty)

        add = QPushButton("Add step")
        add.setIcon(icons.icon("add", theme.current["text"], 16))
        menu = QMenu(add)
        for tool in self.tools.values():
            action = menu.addAction(icons.icon(tool.icon, theme.current["text"], 16), tool.name)
            action.triggered.connect(lambda checked=False, t=tool.id: self.add_step(t))
        add.setMenu(menu)
        up = QPushButton("")
        up.setIcon(icons.icon("up", theme.current["text"], 16))
        up.clicked.connect(lambda: self._move(-1))
        down = QPushButton("")
        down.setIcon(icons.icon("down", theme.current["text"], 16))
        down.clicked.connect(lambda: self._move(1))
        remove = QPushButton("Remove")
        remove.clicked.connect(self._remove)
        bar = QHBoxLayout()
        for w in (add, up, down, remove):
            bar.addWidget(w)
        bar.addStretch(1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("<b>Steps</b>"))
        layout.addLayout(bar)
        layout.addWidget(self.list)
        self.step_title = QLabel("")
        self.step_title.setObjectName("SectionTitle")
        layout.addWidget(self.step_title)
        layout.addWidget(self.stack)

    def _form_for(self, tool_id, values=None):
        from .widgets import OptionsForm

        tool = self.tools[tool_id]
        form = OptionsForm(tool.options)
        if values:
            form.set_values(values)
        form.changed.connect(self.changed)
        self.stack.addWidget(form)
        return form

    def add_step(self, tool_id, values=None):
        if tool_id not in self.tools:
            return
        tool = self.tools[tool_id]
        item = QListWidgetItem(icons.icon(tool.icon, theme.current["text"], 18), tool.name)
        item.setData(ROLE_TOOL, tool_id)
        form = self._form_for(tool_id, values)
        self.forms[id(item)] = form
        self.list.addItem(item)
        self.list.setCurrentItem(item)
        self._renumber()
        self.changed.emit()

    def _renumber(self):
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setText(f"{i + 1}. {self.tools[item.data(ROLE_TOOL)].name}")

    def _select(self, row):
        if row < 0:
            self.stack.setCurrentIndex(0)
            self.step_title.setText("")
            return
        item = self.list.item(row)
        self.stack.setCurrentWidget(self.forms[id(item)])
        self.step_title.setText(f"Settings for step {row + 1}")

    def _move(self, delta):
        row = self.list.currentRow()
        new = row + delta
        if row < 0 or not 0 <= new < self.list.count():
            return
        item = self.list.takeItem(row)
        self.list.insertItem(new, item)
        self.list.setCurrentRow(new)
        self._renumber()
        self.changed.emit()

    def _remove(self):
        row = self.list.currentRow()
        if row < 0:
            return
        item = self.list.takeItem(row)
        form = self.forms.pop(id(item), None)
        if form:
            self.stack.removeWidget(form)
            form.deleteLater()
        self._renumber()
        self._select(self.list.currentRow())
        self.changed.emit()

    def value(self):
        steps = []
        for i in range(self.list.count()):
            item = self.list.item(i)
            steps.append({"tool": item.data(ROLE_TOOL), "options": self.forms[id(item)].values()})
        return steps

    def set_value(self, value):
        while self.list.count():
            self.list.setCurrentRow(0)
            self._remove()
        for step in value or []:
            self.add_step(step.get("tool"), step.get("options"))

    def problem(self):
        if not self.list.count():
            return "Add at least one step."
        for i in range(self.list.count()):
            form = self.forms[id(self.list.item(i))]
            issues = form.problems()
            if issues:
                return f"Step {i + 1}: {issues[0]}"
        return None
