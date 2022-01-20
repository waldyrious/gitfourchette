from allqt import *
from util import excMessageBox
import signal
import sys


def excepthook(exctype, value, tb):
    sys.__excepthook__(exctype, value, tb)  # run default excepthook
    excMessageBox(value, printExc=False)


if __name__ == "__main__":
    # allow interrupting with Control-C
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # inject our own exception hook to show an error dialog in case of unhandled exceptions
    sys.excepthook = excepthook

    # initialize Qt before importing app modules so fonts are loaded correctly
    app = QApplication(sys.argv)

    import assets_rc

    app.setApplicationName("GitFourchette")  # used by QStandardPaths
    # Don't use app.setOrganizationName because it changes QStandardPaths.
    app.setApplicationVersion("1.0.0")
    app.setWindowIcon(QIcon(":/gitfourchette.png"))

    styleSheetFile = QFile(":/style.qss")
    if styleSheetFile.open(QFile.ReadOnly):
        styleSheet = styleSheetFile.readAll().data().decode("utf-8")
        app.setStyleSheet(styleSheet)
        styleSheetFile.close()

    # Hack so we don't get out-of-place Tahoma on Windows.
    # TODO: Check whether Qt 6 has made this unnecessary (when it comes out).
    if QSysInfo.productType() == "windows":
        # Get QMenu's font (which is correct) instead of using raw Segoe UI,
        # because some locales might use a different font than Segoe.
        sysFont = QApplication.font("QMenu")
        QApplication.setFont(sysFont)

    import settings
    settings.prefs.load()
    settings.history.load()
    if settings.prefs.qtStyle:
        app.setStyle(settings.prefs.qtStyle)

    from widgets import mainwindow

    window = mainwindow.MainWindow()
    window.show()
    window.tryLoadSession()
    app.exec_()
