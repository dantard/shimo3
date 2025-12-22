import glob
import multiprocessing
import random
import sys
import time
from multiprocessing import Queue
from os import path
import os
from random import shuffle

import yaml
from PyQt5.QtWidgets import QApplication, QGraphicsView, QGraphicsScene, QGraphicsTextItem, QGraphicsPixmapItem
from PyQt5.QtGui import QPixmap, QPainter, QFont, QColor
from PyQt5.QtCore import Qt, QTimer, QRect

from thegoodbot import run_bot

class GrowingView(QGraphicsView):
    CHOOSE = 0
    GROWING = 1
    SHOWING = 2
    FADING = 3
    BRIGHTENING = 4

    def __init__(self, q, config):
        super().__init__()
        self.ts = 0
        self.queue: Queue = q
        self.state = GrowingView.GROWING
        self.scale_factor = 0.1
        self.delta = config.get("scale_delta", 0.01)
        self.images = []
        self.timer = QTimer(self)
        self.timer.setInterval(config.get("rate", 30))
        self.timer.timeout.connect(self.grow)
        self.landscape = True
        self.save_dir = config.get("save_dir", "downloads")
        scene = QGraphicsScene()
        self.pixmap = scene.addPixmap(QPixmap())
        self.fading_speed = config.get("fading_speed", 0.02)
        self.show_remaining = config.get("show_remaining", False)

        # Create text item
        self.text_item = QGraphicsTextItem("")
        self.text_item.setDefaultTextColor(QColor(255, 255, 255))  # White color
        font = QFont("Arial", config.get("font_size", 32), QFont.Bold)
        self.text_item.setFont(font)

        self.clock_item = QGraphicsTextItem("")
        self.clock_item.setDefaultTextColor(QColor(255, 255, 255))  # White color
        self.clock_item.setFont(font)

        self.info_item = QGraphicsTextItem("")
        self.info_item.setDefaultTextColor(QColor(255, 255, 255))  # White color
        self.info_item.setFont(font)

        self.duration = config.get("duration", 1)

        # This flag prevents the text from affecting the scene's bounding rectangle
        self.clock_item.setFlag(QGraphicsTextItem.ItemIgnoresTransformations)
        scene.addItem(self.clock_item)

        self.info_item.setFlag(QGraphicsTextItem.ItemIgnoresTransformations)
        scene.addItem(self.info_item)

        self.text_item.setFlag(QGraphicsTextItem.ItemIgnoresTransformations)
        scene.addItem(self.text_item)

        self.setScene(scene)

        self.setRenderHint(QPainter.SmoothPixmapTransform)
        # set view background color
        self.setBackgroundBrush(Qt.black)
        self.setFrameShape(QGraphicsView.NoFrame)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        QTimer.singleShot(0, self.start_growing)  # start the timer after the view is shown




    def set_new_image(self, filename):
        image = QPixmap(filename)
        self.pixmap.setPixmap(image)
        self.pixmap.setOpacity(0)
        self.pixmap.setOffset(-image.width() / 2, -image.height() / 2)
        vw = self.viewport().width()
        vh = self.viewport().height()
        # show the image filling viewport height or width initially
        if self.pixmap.pixmap().width() < self.pixmap.pixmap().height():
            self.scale_factor = vh / self.pixmap.pixmap().height()
        else:
            self.scale_factor = vw / self.pixmap.pixmap().width()
        self.pixmap.setScale(self.scale_factor)

        # Update text position after viewport is ready
        self.update_text_position()

    def start_growing(self):
        # start after the view has been shown so viewport() has correct size
        if not self.timer.isActive():
            self.state = GrowingView.CHOOSE
            self.timer.start()

    def process_command(self, command):
        if command.startswith("/m "):
            message = command[3:]
            self.info_item.setPlainText(message)
        elif command == "/reset":
            self.info_item.setPlainText("")
        elif command == "/shuffle":
            self.images = []


    def grow(self):
        self.update_clock()

        if self.queue.qsize() > 0:
            command = self.queue.get()
            self.process_command(command)

        if self.state == GrowingView.CHOOSE:
            if len(self.images) == 0:
                self.images = glob.glob(self.save_dir + os.sep + "*.[jp][pn]g")
                if len (self.images) == 0:
                    time.sleep(1)
                    print("No images found, waiting...")
                shuffle(self.images)
            else:
                filename = self.images.pop(0)
                self.set_new_image(filename)
                if "unnamed" in filename or filename is None:
                    text = ""
                else:
                    text = path.basename(filename).split("_")[0]
                if self.show_remaining:
                    text + "\n" + len(self.images).__str__()
                self.text_item.setPlainText(text)
                self.state = GrowingView.BRIGHTENING

        elif self.state == GrowingView.BRIGHTENING:
            if self.pixmap.opacity() >= 1.0 or self.fading_speed == 0:
                self.state = GrowingView.GROWING
            else:
                self.pixmap.setOpacity(self.pixmap.opacity() + self.fading_speed)
        elif self.state == GrowingView.GROWING:
            self.pixmap.setOpacity(1.0)
            next_scale = self.scale_factor + self.delta
            self.pixmap.setScale(next_scale)
            # get real size after scaling
            w = self.pixmap.pixmap().width() * next_scale
            h = self.pixmap.pixmap().height() * next_scale
            vw = self.viewport().width()
            vh = self.viewport().height()
            self.centerOn(self.pixmap)
            self.scale_factor = next_scale

            if (w >= h >= vh) or (h >= w >= vw):
                self.state = GrowingView.SHOWING
                self.ts = time.time()

        elif self.state == GrowingView.SHOWING:
            if time.time() - self.ts > self.duration:
                self.scale_factor = 0.1
                self.state = GrowingView.FADING

        elif self.state == GrowingView.FADING or self.fading_speed == 0:
            if self.pixmap.opacity() <= 0:
                self.state = GrowingView.CHOOSE
            else:
                self.pixmap: QGraphicsPixmapItem
                self.pixmap.setOpacity(self.pixmap.opacity() - self.fading_speed)


        # Keep text in upper left corner
        self.update_text_position()

    def update_text_position(self):
        top_left = self.mapToScene(10, 10)
        self.text_item.setPos(top_left)
        top_right = self.mapToScene(self.viewport().width() - 150, 10)
        self.clock_item.setPos(top_right)
        bottom_left = self.mapToScene(10, self.viewport().height() - 60)
        self.info_item.setPos(bottom_left)

    def update_clock(self):
        current_time = time.strftime("%H:%M")
        self.clock_item.setPlainText(current_time)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_text_position()


if __name__ == "__main__":
    base_dir = os.path.expanduser('~/.config/thegoodone')
    os.makedirs(base_dir, exist_ok=True)

    q = multiprocessing.Queue()

    # load config
    try:
        with open(base_dir + os.sep + "config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        config = {"bot_token": None, "rate": 30, "duration": 1, "scale_delta": 0.01, "font_size": 32, "fading_speed": 0.02, "save_dir": "downloads", "authorized_users": []}
        yaml.safe_dump(config, open(base_dir + os.sep + "config.yaml", "w"))

    if config.get("bot_token", None) is not None:
        bot_process = multiprocessing.Process(target=run_bot, args=(q,config,))
        bot_process.start()
    else:
        print("Please set bot_token in config.yaml")

    app = QApplication(sys.argv)
    view = GrowingView(q, config)
    view.setAlignment(Qt.AlignCenter)
    view.showFullScreen()

    sys.exit(app.exec_())