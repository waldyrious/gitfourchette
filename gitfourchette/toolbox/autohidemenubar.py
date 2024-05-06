from contextlib import suppress

from gitfourchette import settings
from gitfourchette.qt import *


class AutoHideMenuBar(QObject):
    def __init__(self, menuBar: QMenuBar):
        super().__init__(menuBar)

        self.setObjectName("AutoHideMenuBar")

        self.menuBar = menuBar
        self.defaultMaximumHeight = self.menuBar.maximumHeight()
        self.sticky = False

        self.hideScheduler = QTimer(self)
        self.hideScheduler.setInterval(0)
        self.hideScheduler.setSingleShot(True)
        self.hideScheduler.timeout.connect(self.doScheduledHide)

        self.refreshPrefs()

    def refreshPrefs(self):
        self.hideScheduler.stop()

        # Show the menu bar if auto-hide is turned off, OR if the sticky bit
        # was set as the prefs were reset. That way, if our specific setting
        # wasn't updated, the menu bar will stay put.
        self.showMenuBar(not self.enabled or self.sticky)

        # Reinstall signal connections regardless.
        self.reconnectToMenus()

        # Reset sticky bit if auto-hide is turned off, so that the menubar
        # gets hidden right away next time auto-hide is reenabled.
        if not self.enabled:
            self.sticky = False

    def reconnectToMenus(self):
        menu: QMenu
        for menu in self.menuBar.findChildren(QMenu, options=Qt.FindChildOption.FindDirectChildrenOnly):
            # Disconnect any existing connections
            with suppress(RuntimeError, TypeError):  # PySide6, PyQt6
                menu.aboutToShow.disconnect(self.onMenuAboutToShow)
            with suppress(RuntimeError, TypeError):
                menu.aboutToHide.disconnect(self.onMenuAboutToHide)

            # Reconnect signals if auto-hide is enabled
            if self.enabled:
                menu.aboutToShow.connect(self.onMenuAboutToShow)
                menu.aboutToHide.connect(self.onMenuAboutToHide)

    @property
    def enabled(self):
        return not settings.prefs.showMenuBar

    @property
    def isHidden(self):
        return self.menuBar.maximumHeight() == 0

    def showMenuBar(self, show):
        if show:
            self.menuBar.setMaximumHeight(self.defaultMaximumHeight)
        else:
            self.menuBar.setMaximumHeight(0)

    def toggle(self):
        assert self.enabled, "did you forget to disconnect AutoHideMenuBar signals?"
        self.sticky = True
        self.showMenuBar(self.isHidden)

    def onMenuAboutToShow(self):
        assert self.enabled, "did you forget to disconnect AutoHideMenuBar signals?"
        self.hideScheduler.stop()
        if self.isHidden:
            self.showMenuBar(True)
            self.sticky = False

    def onMenuAboutToHide(self):
        assert self.enabled, "did you forget to disconnect AutoHideMenuBar signals?"
        self.hideScheduler.start()

    def doScheduledHide(self):
        assert self.enabled, "did you forget to disconnect AutoHideMenuBar signals?"
        if not self.isHidden and not self.sticky:
            self.showMenuBar(False)
