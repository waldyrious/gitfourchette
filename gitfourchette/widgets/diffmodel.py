from gitfourchette import colors
from gitfourchette import settings
from gitfourchette.nav import NavLocator
from gitfourchette.subpatch import DiffLinePos
from gitfourchette.qt import *
from gitfourchette.util import isZeroId, isImageFormatSupported
from dataclasses import dataclass
import html
import os
import pygit2


@dataclass
class LineData:
    # For visual representation
    text: str

    diffLine: pygit2.DiffLine | None

    cursorStart: int  # position of the cursor at the start of the line in the DiffView widget

    hunkPos: DiffLinePos


class DiffModelError(Exception):
    def __init__(
            self,
            message: str,
            details: str = "",
            icon=QStyle.StandardPixmap.SP_MessageBoxInformation,
            preformatted: str = "",
            longform: str = "",
    ):
        super().__init__(message)
        self.message = message
        self.details = details
        self.icon = icon
        self.preformatted = preformatted
        self.longform = longform


class ShouldDisplayPatchAsImageDiff(Exception):
    def __init__(self):
        super().__init__("This patch should be viewed as an image diff!")


class DiffImagePair:
    oldImage: QImage
    newImage: QImage

    def __init__(self, repo: pygit2.Repository, delta: pygit2.DiffDelta, locator: NavLocator):
        if not isZeroId(delta.old_file.id):
            imageDataA = repo[delta.old_file.id].peel(pygit2.Blob).data
        else:
            imageDataA = b''

        if isZeroId(delta.new_file.id):
            imageDataB = b''
        elif locator.context.isDirty():
            fullPath = os.path.join(repo.workdir, delta.new_file.path)
            assert os.lstat(fullPath).st_size == delta.new_file.size, "Size mismatch in unstaged image file"
            with open(fullPath, 'rb') as file:
                imageDataB = file.read()
        else:
            imageDataB = repo[delta.new_file.id].peel(pygit2.Blob).data

        self.oldImage = QImage.fromData(imageDataA)
        self.newImage = QImage.fromData(imageDataB)


class DiffConflict:
    ancestor: pygit2.IndexEntry
    ours: pygit2.IndexEntry
    theirs: pygit2.IndexEntry

    def __init__(self, repo: pygit2.Repository, ancestor: pygit2.IndexEntry, ours: pygit2.IndexEntry, theirs: pygit2.IndexEntry):
        self.ancestor = ancestor
        self.ours = ours
        self.theirs = theirs


class DiffStyle:
    def __init__(self):
        if settings.prefs.diff_colorblindFriendlyColors:
            self.minusColor = QColor(colors.orange)
            self.plusColor = QColor(colors.teal)
        else:
            self.minusColor = QColor(0xff5555)   # Lower-saturation alternative for e.g. foreground text: 0x993333
            self.plusColor = QColor(0x55ff55)   # Lower-saturation alternative for e.g. foreground text: 0x339933

        self.minusColor.setAlpha(0x58)
        self.plusColor.setAlpha(0x58)

        self.plusBF = QTextBlockFormat()
        self.plusBF.setBackground(self.plusColor)

        self.minusBF = QTextBlockFormat()
        self.minusBF.setBackground(self.minusColor)

        self.arobaseBF = QTextBlockFormat()
        self.arobaseCF = QTextCharFormat()
        self.arobaseCF.setFontItalic(True)
        self.arobaseCF.setForeground(QColor(0, 80, 240))

        self.warningCF1 = QTextCharFormat()
        self.warningCF1.setFontWeight(QFont.Weight.Bold)
        self.warningCF1.setForeground(QColor(200, 30, 0))


def noChange(delta: pygit2.DiffDelta):
    message = translate("DiffModel", "File contents didn’t change.")
    details = []

    oldFileExists = not isZeroId(delta.old_file.id)
    newFileExists = not isZeroId(delta.new_file.id)

    if not newFileExists:
        message = translate("DiffModel", "Empty file was deleted.")

    if not oldFileExists:
        if delta.status in [pygit2.GIT_DELTA_ADDED, pygit2.GIT_DELTA_UNTRACKED]:
            message = translate("DiffModel", "New empty file.")
        else:
            message = translate("DiffModel", "File is empty.")

    if delta.old_file.path != delta.new_file.path:
        details.append(translate("DiffModel", "Renamed:") + f" “{html.escape(delta.old_file.path)}” &rarr; “{html.escape(delta.new_file.path)}”.")

    if oldFileExists and delta.old_file.mode != delta.new_file.mode:
        details.append(translate("DiffModel", "Mode change:") + f" “{delta.old_file.mode:06o}” &rarr; “{delta.new_file.mode:06o}”.")

    return DiffModelError(message, "\n".join(details))


@dataclass
class DiffModel:
    document: QTextDocument
    lineData: list[LineData]
    style: DiffStyle

    @staticmethod
    def fromPatch(patch: pygit2.Patch):
        if patch.delta.similarity == 100:
            raise noChange(patch.delta)

        locale = QLocale()

        # Don't show contents if file appears to be binary.
        if patch.delta.is_binary:
            of = patch.delta.old_file
            nf = patch.delta.new_file
            if isImageFormatSupported(of.path) and isImageFormatSupported(nf.path):
                largestSize = max(of.size, nf.size)
                threshold = settings.prefs.diff_imageFileThresholdKB * 1024
                if largestSize > threshold:
                    humanSize = locale.formattedDataSize(largestSize)
                    humanThreshold = locale.formattedDataSize(threshold)
                    raise DiffModelError(
                        translate("DiffModel", "This image is too large to be previewed ({0}).").format(humanSize),
                        translate("DiffModel", "You can change the size threshold in the Preferences (current limit: {0}).").format(humanThreshold),
                        QStyle.StandardPixmap.SP_MessageBoxWarning)
                else:
                    raise ShouldDisplayPatchAsImageDiff()
            else:
                oldHumanSize = locale.formattedDataSize(of.size)
                newHumanSize = locale.formattedDataSize(nf.size)
                raise DiffModelError(
                    translate("DiffModel", "File appears to be binary."),
                    f"{oldHumanSize} &rarr; {newHumanSize}")

        # Don't load large diffs.
        threshold = settings.prefs.diff_largeFileThresholdKB * 1024
        if len(patch.data) > threshold:
            humanSize = locale.formattedDataSize(len(patch.data))
            humanThreshold = locale.formattedDataSize(threshold)
            raise DiffModelError(
                translate("DiffModel", "This patch is too large to be previewed ({0}).").format(humanSize),
                translate("DiffModel", "You can change the size threshold in the Preferences (current limit: {0}).").format(humanThreshold),
                QStyle.StandardPixmap.SP_MessageBoxWarning)

        if len(patch.hunks) == 0:
            raise noChange(patch.delta)

        style = DiffStyle()

        document = QTextDocument()  # recreating a document is faster than clearing the existing one
        document.setDocumentLayout(QPlainTextDocumentLayout(document))

        cursor: QTextCursor = QTextCursor(document)

        defaultBF = cursor.blockFormat()
        defaultCF = cursor.charFormat()

        assert document.isEmpty()

        lineData = []

        def insertLineData(ld: LineData, bf, cf):
            lineData.append(ld)

            trailer = None

            if ld.text.endswith('\r\n'):
                trimBack = -2
                if settings.prefs.diff_showStrayCRs:
                    trailer = "<CRLF>"
            elif ld.text.endswith('\r'):
                trimBack = -1
                if settings.prefs.diff_showStrayCRs:
                    trailer = "<CR>"
            elif ld.text.endswith('\n'):
                trimBack = -1
            else:
                trailer = translate("DiffModel", "<no newline at end of file>")
                trimBack = None

            if not document.isEmpty():
                cursor.insertBlock()
                ld.cursorStart = cursor.position()

            cursor.setBlockFormat(bf)
            cursor.setBlockCharFormat(cf)
            cursor.insertText(ld.text[:trimBack])

            if trailer:
                cursor.setCharFormat(style.warningCF1)
                cursor.insertText(trailer)

        # For each line of the diff, create a LineData object.
        for hunkID, hunk in enumerate(patch.hunks):
            oldLine = hunk.old_start
            newLine = hunk.new_start

            hunkHeaderLD = LineData(
                text=hunk.header,
                cursorStart=cursor.position(),
                diffLine=None,
                hunkPos=DiffLinePos(hunkID, -1))
            insertLineData(hunkHeaderLD, style.arobaseBF, style.arobaseCF)

            for hunkLineNum, diffLine in enumerate(hunk.lines):
                if diffLine.origin in "=><":  # GIT_DIFF_LINE_CONTEXT_EOFNL, GIT_DIFF_LINE_ADD_EOFNL, GIT_DIFF_LINE_DEL_EOFNL
                    continue

                ld = LineData(
                    text=diffLine.content,
                    cursorStart=cursor.position(),
                    diffLine=diffLine,
                    hunkPos=DiffLinePos(hunkID, hunkLineNum))

                bf = defaultBF

                assert diffLine.origin in " -+", F"diffline origin: '{diffLine.origin}'"
                if diffLine.origin == '+':
                    bf = style.plusBF
                    assert diffLine.new_lineno == newLine
                    assert diffLine.old_lineno == -1
                    newLine += 1
                elif diffLine.origin == '-':
                    bf = style.minusBF
                    assert diffLine.new_lineno == -1
                    assert diffLine.old_lineno == oldLine
                    oldLine += 1
                else:
                    assert diffLine.new_lineno == newLine
                    assert diffLine.old_lineno == oldLine
                    newLine += 1
                    oldLine += 1

                insertLineData(ld, bf, defaultCF)

        return DiffModel(document=document, lineData=lineData, style=style)
