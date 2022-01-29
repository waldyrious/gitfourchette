from allqt import *
from dataclasses import dataclass
import colors
import os
import patch as patchutils
import pygit2
import settings


class DiffModelError(BaseException):
    def __init__(
            self,
            message: str,
            details: str = "",
            icon=QStyle.SP_MessageBoxInformation,
            preformatted: str = ""
    ):
        super().__init__(message)
        self.message = message
        self.details = details
        self.icon = icon
        self.preformatted = preformatted


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
        self.warningCF1.setFontWeight(QFont.Bold)
        self.warningCF1.setForeground(QColor(200, 30, 0))


def createDocument():
    monoFont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
    if settings.prefs.diff_font:
        monoFont.fromString(settings.prefs.diff_font)

    document = QTextDocument()  # recreating a document is faster than clearing the existing one
    document.setDocumentLayout(QPlainTextDocumentLayout(document))
    document.setDefaultFont(monoFont)
    return document


@dataclass
class DiffModel:
    document: QTextDocument
    lineData: list[patchutils.LineData]
    style: DiffStyle

    @staticmethod
    def fromUntrackedFile(repo: pygit2.Repository, path: str):
        fullPath = os.path.join(repo.workdir, path)

        # Don't load large files.
        fileSize = os.path.getsize(fullPath)
        if fileSize > settings.prefs.diff_largeFileThresholdKB * 1024:
            raise DiffModelError(
                F"This file is too large to be previewed ({fileSize//1024:,} KB).",
                "You can change the size threshold in the Preferences.",
                icon=QStyle.SP_MessageBoxWarning)

        # Load entire file contents.
        with open(fullPath, 'rb') as f:
            binaryContents = f.read()

        # Don't show contents if file appears to be binary.
        if b'\x00' in binaryContents:
            raise DiffModelError("File appears to be binary.")

        # Decode file contents.
        contents = binaryContents.decode('utf-8', errors='replace')

        # Create document with proper styling.
        style = DiffStyle()
        document = createDocument()  # recreating a document is faster than clearing the existing one
        cursor = QTextCursor(document)
        cursor.setBlockFormat(style.plusBF)  # Use style for "+" lines for the entire file.
        cursor.insertText(contents)

        return DiffModel(document=document, lineData=[], style=style)

    @staticmethod
    def fromPatch(repo: pygit2.Repository, patch: pygit2.Patch):
        # Don't show contents if file appears to be binary.
        if patch.delta.is_binary:
            raise DiffModelError("File appears to be binary.")

        if patch.delta.status == pygit2.GIT_DELTA_UNTRACKED:
            return DiffModel.fromUntrackedFile(repo, patch.delta.new_file.path)

        # Don't load large diffs.
        if len(patch.data) > settings.prefs.diff_largeFileThresholdKB * 1024:
            raise DiffModelError(
                F"This patch is too large to be previewed ({len(patch.data)//1024:,} KB).",
                "You can change the size threshold in the Preferences.",
                QStyle.SP_MessageBoxWarning)

        if len(patch.hunks) == 0:
            raise DiffModelError(F"File contents did not change.")

        style = DiffStyle()
        document = createDocument()  # recreating a document is faster than clearing the existing one
        cursor: QTextCursor = QTextCursor(document)

        defaultBF = cursor.blockFormat()
        defaultCF = cursor.charFormat()

        assert document.isEmpty()

        lineData = []

        def insertLineData(ld: patchutils.LineData, bf, cf):
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
                trailer = "<no newline at end of file>"
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

            hunkHeaderLD = patchutils.LineData(
                text=hunk.header,
                cursorStart=cursor.position(),
                diffLine=None,
                hunkPos=patchutils.DiffLinePos(hunkID, -1))
            insertLineData(hunkHeaderLD, style.arobaseBF, style.arobaseCF)

            for hunkLineNum, diffLine in enumerate(hunk.lines):
                if diffLine.origin in "=><":  # GIT_DIFF_LINE_CONTEXT_EOFNL, GIT_DIFF_LINE_ADD_EOFNL, GIT_DIFF_LINE_DEL_EOFNL
                    continue

                ld = patchutils.LineData(
                    text=diffLine.content,
                    cursorStart=cursor.position(),
                    diffLine=diffLine,
                    hunkPos=patchutils.DiffLinePos(hunkID, hunkLineNum))

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
