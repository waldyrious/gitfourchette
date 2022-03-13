from dataclasses import dataclass
from gitfourchette.util import isZeroId
import io
import pygit2


@dataclass
class DiffLinePos:
    hunkID: int
    hunkLineNum: int


def quotePath(path: bytes):
    surround = False

    safePath = ""

    escapes = {
        ord(' '): ' ',
        ord('"'): '\\"',
        ord('\a'): '\\a',
        ord('\b'): '\\b',
        ord('\t'): '\\t',
        ord('\n'): '\\n',
        ord('\v'): '\\v',
        ord('\f'): '\\f',
        ord('\r'): '\\r',
        ord('\\'): '\\\\',
    }

    for c in path:
        if c in escapes:
            safePath += escapes[c]
            surround = True
        elif c < ord('!') or c > ord('~'):
            safePath += F"\\{c:03o}"
            surround = True
        else:
            safePath += chr(c)

    if surround:
        return F'"{safePath}"'
    else:
        return safePath


def getPatchPreamble(delta: pygit2.DiffDelta, reverse=False):
    if not reverse:
        of = delta.old_file
        nf = delta.new_file
    else:
        of = nf = delta.new_file

    aQuoted = quotePath(b"a/" + of.raw_path)
    bQuoted = quotePath(b"b/" + nf.raw_path)
    preamble = F"diff --git {aQuoted} {bQuoted}\n"

    ofExists = not isZeroId(of.id)
    nfExists = not isZeroId(nf.id)

    if ofExists:
        if of.mode != nf.mode:
            preamble += F"old mode {of.mode:06o}\n"
            preamble += F"new mode {nf.mode:06o}\n"
    else:
        preamble += F"new file mode {nf.mode:06o}\n"

    if ofExists:
        preamble += F"--- a/{of.path}\n"
    else:
        preamble += F"--- /dev/null\n"

    if nfExists:
        preamble += F"+++ b/{nf.path}\n"
    else:
        preamble += F"+++ /dev/null\n"

    return preamble


def extractSubpatch(
        masterPatch: pygit2.Patch,
        startPos: DiffLinePos,  # index of first selected line in master patch
        endPos: DiffLinePos,  # index of last selected line in master patch
        reverse: bool
) -> bytes:
    """
    Creates a patch (in unified diff format) from the range of selected diff lines given as input.
    """

    def originToDelta(origin):
        if origin == '+':
            return 1
        elif origin == '-':
            return -1
        else:
            return 0

    def reverseOrigin(origin):
        if origin == '+':
            return '-'
        elif origin == '-':
            return '+'
        else:
            return origin

    def writeContext(subpatch, lines):
        skipOrigin = '-' if reverse else '+'
        for line in lines:
            if line.origin == skipOrigin:
                continue
            subpatch.write(b" ")
            subpatch.write(line.raw_content)

    patch = io.BytesIO()

    preamble = getPatchPreamble(masterPatch.delta, reverse)
    patch.write(preamble.encode())

    newHunkStartOffset = 0
    subpatchIsEmpty = True

    for hunkID in range(startPos.hunkID, endPos.hunkID + 1):
        assert hunkID >= 0
        hunk = masterPatch.hunks[hunkID]

        # Compute start line boundary for this hunk
        if hunkID == startPos.hunkID:  # First hunk in selection?
            startLineNum = startPos.hunkLineNum
            if startLineNum < 0:  # The hunk header's hunkLineNum is -1
                startLineNum = 0
        else:  # Middle hunk: take all lines in hunk
            startLineNum = 0

        # Compute end line boundary for this hunk
        if hunkID == endPos.hunkID:  # Last hunk in selection?
            endLineNum = endPos.hunkLineNum
            if endLineNum < 0:  # The hunk header's relative line number is -1
                endLineNum = 0
        else:  # Middle hunk: take all lines in hunk
            endLineNum = len(hunk.lines) - 1

        # Compute line count delta in this hunk
        lineCountDelta = sum(originToDelta(hunk.lines[ln].origin) for ln in range(startLineNum, endLineNum + 1))
        if reverse:
            lineCountDelta = -lineCountDelta

        # Skip this hunk if all selected lines are context
        if lineCountDelta == 0 and \
                all(originToDelta(hunk.lines[ln].origin) == 0 for ln in range(startLineNum, endLineNum + 1)):
            continue
        else:
            subpatchIsEmpty = False

        # Get coordinates of old hunk
        if reverse:  # flip old<=>new if reversing
            oldStart = hunk.new_start
            oldLines = hunk.new_lines
        else:
            oldStart = hunk.old_start
            oldLines = hunk.old_lines

        # Compute coordinates of new hunk
        newStart = oldStart + newHunkStartOffset
        newLines = oldLines + lineCountDelta

        # Assemble doctored hunk header
        headerComment = hunk.header[hunk.header.find(" @@") + 3 :]
        assert headerComment.endswith("\n")
        patch.write(F"@@ -{oldStart},{oldLines} +{newStart},{newLines} @@{headerComment}".encode())

        # Account for line count delta in next new hunk's start offset
        newHunkStartOffset += lineCountDelta

        # Write non-selected lines at beginning of hunk as context
        writeContext(patch, (hunk.lines[ln] for ln in range(0, startLineNum)))

        # Write selected lines within the hunk
        for ln in range(startLineNum, endLineNum + 1):
            line = hunk.lines[ln]
            if not reverse:
                origin = line.origin
            else:
                origin = reverseOrigin(line.origin)
            patch.write(origin.encode())
            patch.write(line.raw_content)

        # Write non-selected lines at end of hunk as context
        writeContext(patch, (hunk.lines[ln] for ln in range(endLineNum + 1, len(hunk.lines))))

    if subpatchIsEmpty:
        return b""
    else:
        return patch.getvalue()
