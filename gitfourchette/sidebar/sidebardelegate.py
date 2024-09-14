# -----------------------------------------------------------------------------
# Copyright (C) 2024 Iliyas Jorio.
# This file is part of GitFourchette, distributed under the GNU GPL v3.
# For full terms, see the included LICENSE file.
# -----------------------------------------------------------------------------

import enum

from gitfourchette.qt import *
from gitfourchette.sidebar.sidebarmodel import SidebarNode, SidebarModel, EItem, UNINDENT_ITEMS
from gitfourchette.toolbox import stockIcon, drawFittedText

PE_EXPANDED = QStyle.PrimitiveElement.PE_IndicatorArrowDown
PE_COLLAPSED = QStyle.PrimitiveElement.PE_IndicatorArrowRight

# These metrics are a good compromise for Breeze, macOS, and Fusion.
EXPAND_TRIANGLE_WIDTH = 6
PADDING = 4
EYE_WIDTH = 16


class SidebarClickZone(enum.IntEnum):
    Invalid = 0
    Select = 1
    Expand = 2
    Hide = 3


class SidebarDelegate(QStyledItemDelegate):
    """
    Draws custom tree expand/collapse indicator arrows,
    and hide/show icons.
    """

    def __init__(self, parent: QWidget):
        super().__init__(parent)

    @staticmethod
    def unindentRect(item: EItem, rect: QRect, indentation: int):
        if item not in UNINDENT_ITEMS:
            return
        unindentLevels = UNINDENT_ITEMS[item]
        unindentPixels = unindentLevels * indentation
        return rect.adjust(unindentPixels, 0, 0, 0)

    @staticmethod
    def getClickZone(node: SidebarNode, rect: QRect, x: int):
        if node.kind == EItem.Spacer:
            return SidebarClickZone.Invalid
        elif node.mayHaveChildren() and x < rect.left():
            return SidebarClickZone.Expand
        elif node.canBeHidden() and x > rect.right() - EYE_WIDTH - PADDING:
            return SidebarClickZone.Hide
        else:
            return SidebarClickZone.Select

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        node = SidebarNode.fromIndex(index)

        view = option.widget
        sidebarModel: SidebarModel = view.sidebarModel
        style: QStyle = view.style()
        hasFocus = option.state & QStyle.StateFlag.State_HasFocus
        isSelected = option.state & QStyle.StateFlag.State_Selected
        mouseOver = option.state & QStyle.StateFlag.State_Enabled and option.state & QStyle.StateFlag.State_MouseOver
        colorGroup = QPalette.ColorGroup.Normal if hasFocus else QPalette.ColorGroup.Inactive

        isExplicitlyHidden = False
        isImplicitlyHidden = False
        if node.canBeHidden():
            isExplicitlyHidden = sidebarModel.isExplicitlyHidden(node)
            isImplicitlyHidden = isExplicitlyHidden or sidebarModel.isImplicitlyHidden(node)
        makeRoomForEye = isExplicitlyHidden or isImplicitlyHidden or (mouseOver and node.canBeHidden())

        painter.save()

        if node.kind == EItem.Spacer:
            mouseOver = False
            option.state &= ~QStyle.StateFlag.State_MouseOver

            r = QRect(option.rect)
            r.setLeft(0)
            middle = r.top() + int(r.height() / 2)

            tc1 = option.palette.color(colorGroup, QPalette.ColorRole.WindowText)
            tc2 = QColor(tc1)
            tc1.setAlpha(0)
            tc2.setAlpha(33)
            lineGradient = QLinearGradient(r.left() + PADDING, middle, r.right() - PADDING, middle)
            lineGradient.setColorAt(0, tc1)
            lineGradient.setColorAt(.2, tc2)
            lineGradient.setColorAt(1-.2, tc2)
            lineGradient.setColorAt(1, tc1)

            painter.save()
            painter.setPen(QPen(lineGradient, 1))
            painter.drawLine(r.left() + PADDING, middle, r.right() - PADDING, middle)
            painter.restore()

        # Unindent rect
        SidebarDelegate.unindentRect(node.kind, option.rect, view.indentation())

        # Draw expand/collapse triangle.
        if node.mayHaveChildren() and not node.wantForceExpand():
            opt2 = QStyleOptionViewItem(option)
            opt2.rect.adjust(-(EXPAND_TRIANGLE_WIDTH + PADDING), 0, 0, 0)  # args must be integers for pyqt5!
            opt2.rect.setWidth(EXPAND_TRIANGLE_WIDTH)

            # See QTreeView::drawBranches() in qtreeview.cpp for other interesting states
            opt2.state &= ~QStyle.StateFlag.State_MouseOver
            arrowPrimitive = PE_EXPANDED if view.isExpanded(index) else PE_COLLAPSED
            style.drawPrimitive(arrowPrimitive, opt2, painter, view)

        # Draw control background
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)

        # Adjust contents
        option.rect.adjust(PADDING, 0, -PADDING, 0)

        # Set highlighted text color if this item is selected
        iconColorRemapTable = ""
        if isSelected:
            penColor = option.palette.color(colorGroup, QPalette.ColorRole.HighlightedText)
            iconColorRemapTable = f"gray={penColor.name()}"
        elif not node.parent.parent and node.kind != EItem.UncommittedChanges:
            penColor = option.palette.color(colorGroup, QPalette.ColorRole.WindowText)
            penColor.setAlphaF(.66)
        else:
            penColor = option.palette.color(colorGroup, QPalette.ColorRole.WindowText)
        painter.setPen(penColor)

        # Draw decoration icon
        iconWidth = option.decorationSize.width()
        iconKey = index.data(SidebarModel.Role.IconKey)
        if iconKey:
            r = QRect(option.rect)
            r.setWidth(iconWidth)
            icon = stockIcon(iconKey, iconColorRemapTable)
            icon.paint(painter, r, option.decorationAlignment)
            option.rect.adjust(r.width() + PADDING*150//100, 0, 0, 0)

        # Draw text
        textRect = QRect(option.rect)
        if makeRoomForEye:
            textRect.adjust(0, 0, -EYE_WIDTH, 0)
        font: QFont = index.data(Qt.ItemDataRole.FontRole) or option.font
        painter.setFont(font)
        fullText = index.data(Qt.ItemDataRole.DisplayRole)
        isCannedString = node.kind <= EItem.SubmodulesHeader
        if not isCannedString:
            drawFittedText(painter, textRect, option.displayAlignment, fullText, option.textElideMode)
        else:
            text = painter.fontMetrics().elidedText(fullText, Qt.TextElideMode.ElideMiddle, textRect.width())
            painter.drawText(textRect, option.displayAlignment, text)

        # Draw eye
        if makeRoomForEye:
            r = QRect(option.rect)
            r.setLeft(textRect.right())
            r.setWidth(EYE_WIDTH)
            if isExplicitlyHidden:
                eyeIconName = "view-hidden"
            elif isImplicitlyHidden:
                eyeIconName = "view-hidden-indirect"
            else:
                eyeIconName = "view-visible"
            eyeIcon = stockIcon(eyeIconName, iconColorRemapTable)
            eyeIcon.paint(painter, r)

        painter.restore()
