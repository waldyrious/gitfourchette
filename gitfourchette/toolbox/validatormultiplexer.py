from contextlib import suppress
from dataclasses import dataclass
from gitfourchette.qt import *
from gitfourchette.toolbox.iconbank import stockIcon
from typing import Callable


def _showValidationToolTip(widget: QLineEdit, text: str):
    p = QPoint(0, widget.height() // 2)
    p = widget.mapToGlobal(p)
    QToolTip.showText(p, text)


class ValidatorMultiplexer(QObject):
    """
    Provides input validation in multiple QLineEdits and manages the enabled
    state of a set of so-called "gated widgets" depending on the validity of
    the inputs.

    Each QLineEdit is associated to a separate validator function that takes an
    input string (the contents of the QLineEdit) and returns an error string.
    If the validator function returns an empty error string, the QLineEdit is
    deemed to have valid input.

    When the input in a QLineEdit is invalid, all gated widgets are disabled.
    The user can continue entering text into the QLineEdit, but a warning icon
    will appear in it, along with a tooltip reporting the error returned by the
    validator function.

    The gated widgets are enabled only if all QLineEdits contain valid input.

    A typical use case of this class is to disable the OK button in a QDialog
    until all QLineEdits in it are valid.
    """

    @dataclass
    class Input:
        edit: QLineEdit
        validate: Callable[[str], str]
        showWarning: bool
        mustBeValid: bool
        inEditIcon: QAction | None = None

    gatedWidgets: list[QWidget]
    inputs: list[Input]
    timer: QTimer

    def __init__(self, parent):
        super().__init__(parent)
        from gitfourchette.settings import TEST_MODE
        self.gatedWidgets = []
        self.inputs = []
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(500 if not TEST_MODE else 0)

    def setGatedWidgets(self, *args: QWidget):
        self.gatedWidgets = list(args)

    def connectInput(
            self,
            edit: QLineEdit,
            validate: Callable[[str], str],
            showWarning: bool = True,
            mustBeValid: bool = True):
        assert isinstance(edit, QLineEdit)
        assert isinstance(validate, Callable)
        newInput = ValidatorMultiplexer.Input(edit, validate, showWarning, mustBeValid)
        self.inputs.append(newInput)
        edit.textChanged.connect(self.run)

    def run(self, silenceEmptyWarnings=False):
        # Run validator on inputs
        success = True
        errors: list[str] = []
        for input in self.inputs:
            if not input.edit.isEnabled():  # Skip disabled inputs
                newError = ""
            else:
                inputText = input.edit.text()
                newError = input.validate(inputText)
                if newError:
                    success &= not input.mustBeValid
                    if silenceEmptyWarnings and not inputText:
                        # Hide "cannot be empty" message, but do disable gated widgets if this input is required
                        newError = ""
            errors.append(newError)

        # Enable/disable gated widgets
        for w in self.gatedWidgets:
            w.setEnabled(success)

        # Disable error tooltip on success
        if success:
            with suppress(BaseException):
                self.timer.timeout.disconnect()
            self.timer.stop()
            QToolTip.hideText()

        # Set validation feedback
        for input, err in zip(self.inputs, errors):
            if not input.showWarning:
                continue

            if err:
                if not input.inEditIcon:
                    input.inEditIcon = input.edit.addAction(stockIcon("achtung"), QLineEdit.ActionPosition.TrailingPosition)
                    input.inEditIcon.triggered[bool].connect(  # [bool]: for PySide <6.7.0 (PYSIDE-2524)
                        lambda _: QToolTip.showText(QCursor.pos(), input.inEditIcon.toolTip(), input.edit))

                input.inEditIcon.setToolTip(err)

                if input.edit.hasFocus():
                    with suppress(BaseException):
                        self.timer.timeout.disconnect()
                    self.timer.stop()
                    self.timer.timeout.connect(lambda edit=input.edit, text=err: _showValidationToolTip(edit, text))
                    self.timer.start()

            elif not err and input.inEditIcon:
                input.edit.removeAction(input.inEditIcon)
                input.inEditIcon.deleteLater()
                input.inEditIcon = None
