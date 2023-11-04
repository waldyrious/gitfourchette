from gitfourchette.qt import *
_supportedImageFormats = None
_stockIconCache = {}


MultiShortcut = list[QKeySequence]


def setWindowModal(widget: QWidget, modality: Qt.WindowModality = Qt.WindowModality.WindowModal):
    """
    Sets the WindowModal modality on a widget unless we're in test mode.
    (On macOS, window-modal dialogs trigger an unskippable animation
    that wastes time in unit tests.)
    """

    from gitfourchette.settings import TEST_MODE
    if not TEST_MODE:
        widget.setWindowModality(modality)


def openFolder(path: str):
    QDesktopServices.openUrl(QUrl.fromLocalFile(path))


def showInFolder(path: str):
    """
    Show a file or folder with explorer/finder.
    Source for Windows & macOS: https://stackoverflow.com/a/46019091/3388962
    """
    path = os.path.abspath(path)
    isdir = os.path.isdir(path)

    if FREEDESKTOP and HAS_QTDBUS:
        # https://www.freedesktop.org/wiki/Specifications/file-manager-interface
        iface = QDBusInterface("org.freedesktop.FileManager1", "/org/freedesktop/FileManager1")
        if iface.isValid():
            if PYQT5 or PYQT6:
                # PyQt5/6 needs the array of strings to be spelled out explicitly.
                stringType = QMetaType.QString if PYQT5 else QMetaType.QString.value  # ugh...
                arg = QDBusArgument()
                arg.beginArray(stringType)
                arg.add(path)
                arg.endArray()
                iface.call("ShowItems", arg, "")
            else:
                # Thankfully, PySide6 is more pythonic here.
                iface.call("ShowItems", [path], "")
            iface.deleteLater()
            return

    elif WINDOWS:
        if not isdir:  # If it's a file, select it within the folder.
            args = ['/select,', path]
        else:
            args = [path]  # If it's a folder, open it.
        if QProcess.startDetached('explorer', args):
            return

    elif MACOS and not isdir:
        args = [
            '-e', 'tell application "Finder"',
            '-e', 'activate',
            '-e', F'select POSIX file "{path}"',
            '-e', 'end tell',
            '-e', 'return'
        ]
        if not QProcess.execute('/usr/bin/osascript', args):
            return

    # Fallback.
    dirPath = path if os.path.isdir(path) else os.path.dirname(path)
    openFolder(dirPath)


def onAppThread():
    appInstance = QApplication.instance()
    return bool(appInstance and appInstance.thread() is QThread.currentThread())


def isImageFormatSupported(filename: str):
    """
    Guesses whether an image is in a supported format from its filename.
    This is for when QImageReader.imageFormat(path) doesn't cut it (e.g. if the file doesn't exist on disk).
    """
    global _supportedImageFormats

    if _supportedImageFormats is None:
        _supportedImageFormats = [str(fmt, 'ascii') for fmt in QImageReader.supportedImageFormats()]

    ext = os.path.splitext(filename)[-1]
    ext = ext.removeprefix(".").lower()

    return ext in _supportedImageFormats


def tweakWidgetFont(widget: QWidget, relativeSize: int = 100, bold: bool = False):
    font: QFont = widget.font()
    font.setPointSize(font.pointSize() * relativeSize // 100)
    font.setBold(bold)
    widget.setFont(font)
    return font


def formatWidgetText(widget: QAbstractButton | QLabel, *args, **kwargs):
    text = widget.text()
    text = text.format(*args, **kwargs)
    widget.setText(text)
    return text


def formatWidgetTooltip(widget: QWidget, *args, **kwargs):
    text = widget.toolTip()
    text = text.format(*args, **kwargs)
    widget.setToolTip(text)
    return text


def addComboBoxItem(comboBox: QComboBox, caption: str, userData=None, isCurrent=False):
    if isCurrent:
        caption = "• " + caption
    index = comboBox.count()
    comboBox.addItem(caption, userData=userData)
    if isCurrent:
        comboBox.setCurrentIndex(index)
    return index


def isDarkTheme(palette: QPalette | None = None):
    if palette is None:
        palette = QApplication.palette()
    themeBG = palette.color(QPalette.ColorRole.Base)  # standard theme background color
    themeFG = palette.color(QPalette.ColorRole.Text)  # standard theme foreground color
    return themeBG.value() < themeFG.value()


def stockIcon(iconId: str | QStyle.StandardPixmap) -> QIcon:
    """
    If SVG icons don't show up, you may need to install the 'qt6-svg' package.
    """

    # Attempt to get cached icon
    if iconId in _stockIconCache:
        return _stockIconCache[iconId]

    def lookUpNamedIcon(name: str) -> QIcon:
        # First attempt to get a matching icon from the assets
        dark = isDarkTheme()
        prefixes = QDir.searchPaths("assets")

        def assetCandidates():
            for ext in ".svg", ".png":
                if dark:  # attempt to get dark mode variant first
                    yield f"{name}@dark{ext}"
                yield f"{name}{ext}"

        for candidate in assetCandidates():
            for prefix in prefixes:
                fullPath = os.path.join(prefix, candidate)
                if os.path.isfile(fullPath):
                    return QIcon(fullPath)

        # Fall back to theme icons
        return QIcon.fromTheme(name)

    if type(iconId) is str:
        icon = lookUpNamedIcon(iconId)
    else:
        icon = QApplication.style().standardIcon(iconId)

    _stockIconCache[iconId] = icon
    return icon


def clearStockIconCache():
    _stockIconCache.clear()


def appendShortcutToToolTip(widget: QWidget, shortcut: QKeySequence | QKeySequence.StandardKey | Qt.Key, singleLine=True):
    if type(shortcut) in [QKeySequence.StandardKey, Qt.Key]:
        shortcut = QKeySequence(shortcut)
    hint = shortcut.toString(QKeySequence.SequenceFormat.NativeText)
    hint = f"<span style='color: palette(mid)'> {hint}</span>"
    toolTip = widget.toolTip()
    prefix = ""
    if singleLine:
        prefix = "<p style='white-space: pre'>"
    widget.setToolTip(f"{prefix}{toolTip} {hint}")


class DisableWidgetContext:
    def __init__(self, objectToBlock: QWidget):
        self.objectToBlock = objectToBlock

    def __enter__(self):
        self.objectToBlock.setEnabled(False)

    def __exit__(self, excType, excValue, excTraceback):
        self.objectToBlock.setEnabled(True)


class MakeNonNativeDialog(QObject):
    """
    Enables the AA_DontUseNativeDialogs attribute, and disables it when the dialog is shown.
    Meant to be used to disable the iOS-like styling of dialog boxes on modern macOS.
    """
    def __init__(self, parent: QDialog):
        super().__init__(parent)
        nonNativeAlready = QCoreApplication.testAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs)
        if nonNativeAlready:
            self.deleteLater()
            return
        QApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, True)
        parent.installEventFilter(self)

    def eventFilter(self, watched, event: QEvent):
        if event.type() == QEvent.Type.Show:
            QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_DontUseNativeDialogs, False)
            watched.removeEventFilter(self)
            self.deleteLater()
        return False


class QScrollBackupContext:
    def __init__(self, *items: QAbstractScrollArea | QScrollBar):
        self.scrollBars = []
        self.values = []

        for o in items:
            if isinstance(o, QAbstractScrollArea):
                self.scrollBars.append(o.horizontalScrollBar())
                self.scrollBars.append(o.verticalScrollBar())
            else:
                assert isinstance(o, QScrollBar)
                self.scrollBars.append(o)

    def __enter__(self):
        self.values = [o.value() for o in self.scrollBars]

    def __exit__(self, exc_type, exc_val, exc_tb):
        for o, v in zip(self.scrollBars, self.values):
            o.setValue(v)


class QTabBarStyleNoRotatedText(QProxyStyle):
    """
    Prevents text from being rotated in a QTabBar's labels with the West or East positions.

    Does not work well with the macOS native theme!

    Adapted from https://forum.qt.io/post/433000
    """

    def sizeFromContents(self, type: QStyle.ContentsType, option: QStyleOption, size: QSize, widget: QWidget) -> QSize:
        s = super().sizeFromContents(type, option, size, widget)
        if type == QStyle.ContentsType.CT_TabBarTab:
            s.transpose()
        return s

    def drawControl(self, element: QStyle.ControlElement, option: QStyleOption, painter: QPainter, widget: QWidget = None):
        if element == QStyle.ControlElement.CE_TabBarTabLabel:
            assert isinstance(option, QStyleOptionTab)
            option: QStyleOptionTab = QStyleOptionTab(option)  # copy
            option.shape = QTabBar.Shape.RoundedNorth  # override shape
        super().drawControl(element, option, painter, widget)


def makeInternalLink(urlAuthority: str, urlPath: str, urlFragment: str = "", **urlQueryItems):
    url = QUrl()
    url.setScheme(APP_URL_SCHEME)
    url.setAuthority(urlAuthority)

    if urlPath:
        if not urlPath.startswith("/"):
            urlPath = "/" + urlPath
        url.setPath(urlPath)

    if urlFragment:
        url.setFragment(urlFragment)

    query = QUrlQuery()
    for k, v in urlQueryItems.items():
        query.addQueryItem(k, v)
    if query:
        url.setQuery(query)

    return url


def reformatQLabel(label: QLabel, *args, **kwargs):
    text = label.text()
    text = text.format(*args, **kwargs)
    label.setText(text)


def makeMultiShortcut(*args) -> MultiShortcut:
    shortcuts = []

    for alt in args:
        if isinstance(alt, str):
            shortcuts.append(QKeySequence(alt))
        elif isinstance(alt, QKeySequence.StandardKey):
            shortcuts.extend(QKeySequence.keyBindings(alt))
        else:
            assert isinstance(alt, QKeySequence)
            shortcuts.append(alt)

    # Ensure no duplicates (stable order since Python 3.7+)
    if PYSIDE2:  # QKeySequence isn't hashable in PySide2
        shortcuts = list(dict((str(s), s) for s in shortcuts).values())
    else:
        shortcuts = list(dict.fromkeys(shortcuts))

    return shortcuts
