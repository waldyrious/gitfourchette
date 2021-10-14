from allgit import *
from dataclasses import dataclass
import enum
import io
import os
import tempfile


@enum.unique
class PatchPurpose(enum.IntEnum):
    STAGE = enum.auto()
    UNSTAGE = enum.auto()
    DISCARD = enum.auto()


@dataclass
class DiffLinePos:
    hunkID: int
    hunkLineNum: int


@dataclass
class LineData:
    # For visual representation
    text: str

    diffLine: DiffLine

    cursorStart: int  # position of the cursor at the start of the line in the DiffView widget

    hunkPos: DiffLinePos


# Error raised by makePatchFromGitDiff when the diffed file appears to be binary.
class LooksLikeBinaryError(Exception):
    pass


def makePatchFromLines(
        oldPath: str,
        newPath: str,
        masterPatch: pygit2.Patch,
        startPos: DiffLinePos,  # index of first selected line in LineData list
        endPos: DiffLinePos,  # index of last selected line in LineData list
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
    patch.write(F"diff --git a/{oldPath} b/{newPath}\n--- a/{oldPath}\n+++ b/{newPath}\n".encode())

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


def applyPatch(repo: Repository, patchData: bytes, purpose: PatchPurpose) -> str:
    if purpose == PatchPurpose.DISCARD:
        location = pygit2.GIT_APPLY_LOCATION_WORKDIR
    else:
        assert purpose in [PatchPurpose.STAGE, PatchPurpose.UNSTAGE]
        location = pygit2.GIT_APPLY_LOCATION_INDEX

    '''
    print("////////\n" + patchData.decode() + "///////////")
    prefix = F"gitfourchette-DEBUG-{os.path.basename(repo.workdir)}-"
    with tempfile.NamedTemporaryFile(mode='wb', suffix=".patch", prefix=prefix, delete=False) as patchFile:
        patchFile.write(patchData)
        print("Wrote", prefix)
    '''

    diff = Diff.parse_diff(patchData)
    print(F"Will apply to {location}? ", repo.applies(diff, location))
    result = repo.apply(diff, location)
    assert not result, "Patch failed to apply"
