from __future__ import annotations

import gitfourchette.application
from pytestqt.qtbot import QtBot
from typing import TYPE_CHECKING
import pytest
import tempfile
import os

if TYPE_CHECKING:
    # For '-> MainWindow' type annotation, without pulling in MainWindow in the actual fixture
    from gitfourchette.mainwindow import MainWindow


@pytest.fixture(scope="session")
def qapp_args():
    mainPyPath = os.path.join(os.path.dirname(__file__), "..", "gitfourchette", "__main__.py")
    mainPyPath = os.path.normpath(mainPyPath)
    return [mainPyPath, "--test-mode", "--no-threads", "--debug"]


@pytest.fixture(scope="session")
def qapp_cls():
    from gitfourchette.application import GFApplication
    yield GFApplication


@pytest.fixture
def tempDir() -> tempfile.TemporaryDirectory:
    td = tempfile.TemporaryDirectory(prefix="gitfourchettetest-")
    yield td
    td.cleanup()


@pytest.fixture
def mainWindow(qtbot: QtBot) -> MainWindow:
    from gitfourchette import settings, qt, trash
    from gitfourchette.application import GFApplication

    # Turn on test mode: Prevent loading/saving prefs; disable multithreaded work queue
    assert settings.TEST_MODE
    assert settings.SYNC_TASKS

    # Prevent unit tests from reading actual user settings.
    # (The prefs and the trash should use a temp folder with TEST_MODE,
    # so this is just an extra safety precaution.)
    qt.QStandardPaths.setTestModeEnabled(True)

    # Boot the UI
    app = GFApplication.instance()
    assert app.mainWindow is None
    app.bootUi()
    mw = app.mainWindow
    assert mw is not None

    # Don't let window linger in memory after this test
    mw.setAttribute(qt.Qt.WidgetAttribute.WA_DeleteOnClose)

    # Let qtbot track the window and close it at the end of the test
    qtbot.addWidget(mw)

    yield mw

    # Qt 5 may need a breather to collect the window
    qt.QTest.qWait(0)

    # The main window must be gone after this test
    assert app.mainWindow is None

    # Clear temp trash after this test
    trash.Trash.instance().clear()

    # Clean up the app without destroying it completely.
    # This will reset the temp settings folder.
    app.onAboutToQuit()
