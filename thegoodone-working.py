import multiprocessing
import sys
import time

from PyQt5.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsTextItem, QGraphicsPixmapItem
from PyQt5.QtGui import QPixmap, QPainter, QFont, QColor
from PyQt5.QtCore import Qt, QTimer, QRect

from thegoodbot import run_bot


class GrowingView(QGraphicsView):
    GROWING = 1
    SHOWING = 2
    FADING = 3

    def __init__(self, q, item, pixmap, delta=0.02, interval=30):
        super().__init__()
        self.ts = 0
        self.queue = q
        self.state = GrowingView.GROWING
        self.item = item
        self.original = pixmap
        self.scale_factor = 0.1
        self.delta = delta
        self.timer = QTimer(self)
        self.timer.setInterval(interval)
        self.timer.timeout.connect(self.grow)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        # set view background color
        self.setBackgroundBrush(Qt.black)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        # Text overlay item
        self.text_item = None

    def start_growing(self):
        # start after the view has been shown so viewport() has correct size
        if not self.timer.isActive():
            self.reset_view()
            self.timer.start()

    def reset_view(self):
        vw = self.viewport().width()
        vh = self.viewport().height()
        # show the image filling viewport height or width initially
        if self.original.width() < self.original.height():
            self.scale_factor = vh / self.original.height()
        else:
            self.scale_factor = vw / self.original.width()

        # Update text position after viewport is ready
        self.update_text_position()

    def grow(self):
        if self.queue.qsize() > 0:
            print("Got new image from queue", self.queue.get())
        if self.state == GrowingView.GROWING:
            self.item.setOpacity(1.0)
            next_scale = self.scale_factor + self.delta
            self.item.setScale(next_scale)
            # get real size after scaling
            w = self.item.pixmap().width() * next_scale
            h = self.item.pixmap().height() * next_scale
            vw = self.viewport().width()
            vh = self.viewport().height()
            self.centerOn(self.item)
            self.scale_factor = next_scale

            if (w > h >= vh) or (h >= w >= vw):
                self.state = GrowingView.SHOWING
                self.ts = time.time()

        elif self.state == GrowingView.SHOWING:
            if time.time() - self.ts > 1:
                self.scale_factor = 0.1
                self.state = GrowingView.FADING

        elif self.state == GrowingView.FADING:
            if self.item.opacity() <= 0:
                self.state = GrowingView.GROWING
            else:
                self.item: QGraphicsPixmapItem
                self.item.setOpacity(self.item.opacity() - 0.02)


        # Keep text in upper left corner
        self.update_text_position()

    def update_text_position(self):
        if self.text_item:
            # Map viewport corner to scene coordinates
            top_left = self.mapToScene(10, 10)
            self.text_item.setPos(top_left)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_text_position()


if __name__ == "__main__":
    q = multiprocessing.Queue()

    bot_process = multiprocessing.Process(target=run_bot, args=(q,))
    bot_process.start()


    app = QApplication(sys.argv)
    scene = QGraphicsScene()
    pixmap = QPixmap("image.jpg")
    item = scene.addPixmap(pixmap)
    item.setPixmap(pixmap)
    item.setOffset(-pixmap.width() / 2, -pixmap.height() / 2)

    # Create text item
    text_item = QGraphicsTextItem("Your Text Here")
    text_item.setDefaultTextColor(QColor(255, 255, 255))  # White color
    font = QFont("Arial", 16, QFont.Bold)
    text_item.setFont(font)

    # This flag prevents the text from affecting the scene's bounding rectangle
    text_item.setFlag(QGraphicsTextItem.ItemIgnoresTransformations)

    scene.addItem(text_item)

    view = GrowingView(q, item, pixmap, delta=0.005, interval=10)
    view.text_item = text_item
    view.setScene(scene)
    view.setAlignment(Qt.AlignCenter)
    view.showFullScreen()
    QTimer.singleShot(0, view.start_growing)  # start the timer after the view is shown

    sys.exit(app.exec_())