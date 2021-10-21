#!/usr/bin/env python3

from PyQt5 import QtWidgets, QtGui
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QApplication, QMainWindow, QVBoxLayout, QWidget,
                             QGridLayout, QStackedLayout, QStackedWidget)
import sys, os
import logging, coloredlogs

from gui.instances_view import instances_view

from awsh_cache import awsh_cache
from awsh_server import awsh_server_commands
from awsh_req_resp_server import awsh_req_client
from awsh_client import get_current_state

# TODO: remove all these, they are only here for testing
import threading
import asyncore
import time

AWSH_HOME = os.path.dirname(os.path.realpath(__file__))

class aws_gui(QWidget):

    is_alive = True

    def __init__(self, regions):
        super().__init__()

        def loop_server():
            while self.is_alive:
                asyncore.loop(timeout=0.5, count = 1)
            print('no longer alive, broke server loop')

        # setup client to server
        # FIXME: This shouldn't be necessary. For some reason asyncore.loop()
        # stalls a lot and works pretty bad w/o spawning a client near a call to
        # loop. This shouldn't be this way. The loop can run w/o any clients
        # alive, and handle each client's spawn. This might be related to the
        # global map of sockets. Maybe pass a custom socket map to
        # asyncore.loop()
        try:
            regions = get_current_state()

            # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
            # TODO: Is it really needed ? The idea was that the client would have
            # one general socket for all regions through which it can get messages.
            # Nevertheless, you seem to prefer creating a new socket for state query
            # operation. You need to decide how many sockets you need open.
            # 
            # To achieve blocking operation it seems like the easiest way would be
            # to use custom socket map. This makes the looping operation in this
            # thread loop over a different socket map. You should really decide what
            # to do here.
            # !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
            self.req_client = awsh_req_client(fail_if_no_server=True)
            wait_thread = threading.Timer(interval = 1, function = loop_server)
            wait_thread = threading.Thread(target = loop_server)
            wait_thread.start()

            # print("Queried regions")
            # print("new regions are:")
            # print(new_regions)
        except Exception as exc:
            print("AWSH server isn't found")
            self.req_client = None

            cache = awsh_cache()
            if not cache.read_cache():
                print("Failed to read cache")
            regions = cache.get_instances()
            # raise exc

        self.create_instances_views(regions)

        self.setLayout(self.viewStackedLayout)

        self.setWindowIcon(QtGui.QIcon(AWSH_HOME + '/awsh_gui.png'))
        self.setGeometry(50, 200, 900, 900)
        
        window_title = "AWS Helper (" + ("not " if not self.req_client else "") + "connected)"
        self.setWindowTitle(window_title)
        self.show()

    def create_instances_views(self, all_regions):
        region_views = dict()
        viewStackedLayout = QStackedLayout()

        # use a list to affect the order in which regions are added to the
        # stacked layout
        stacked_views = list()

        region_with_online_ix = 0

        for region in all_regions:
            if not len(all_regions[region]['instances']):
                continue

            region_long_name = all_regions[region]['long_name']
            instances = all_regions[region]['instances']
            interfaces = all_regions[region]['interfaces']
            has_running_instances = all_regions[region]['has_running_instances']

            region_views[region] = instances_view(
                    region,
                    region_long_name=region_long_name,
                    instances=instances,
                    interfaces=interfaces,
                    parent=self)

            if has_running_instances:
                stacked_views.insert(0, region_views[region])
            else:
                stacked_views.append(region_views[region])

        for sv in stacked_views:
            viewStackedLayout.addWidget(sv)

        self.region_views = region_views
        self.viewStackedLayout = viewStackedLayout



    def update(self, label):
        label.setText("Updated")

    def retrieve(self, label):
        print(label.text())

        # self.labels[self.chosen_c].setStyleSheet(chosen_backgroud)

    def keyPressEvent(self, e):
        # o_chosen_c = self.labels[self.chosen_c]

        key = e.key()

        if key == Qt.Key_unknown:
            return
        elif key == Qt.Key_Escape or e.text() == 'q':
            self.is_alive = False
            # if it's None then no server side exists
            if self.req_client:
                self.req_client.close()
            
            self.close()
        elif len(e.text()) == 1 and e.text() in 'np':
            letter = e.text()
            views_len = self.viewStackedLayout.count()
            currentView_ix = self.viewStackedLayout.currentIndex()

            if not views_len:
                return

            if letter == 'p':
                currentView_ix -= 1
                if currentView_ix < 0:
                    currentView_ix += views_len
            else:
                currentView_ix += 1
                currentView_ix %= views_len

            self.viewStackedLayout.setCurrentIndex(currentView_ix)
        else:
            # pass the key input to child
            currentView = self.viewStackedLayout.currentWidget()
            keyPressFunc = getattr(currentView, 'keyPressEvent', None)
            if callable(keyPressFunc):
                currentView.keyPressEvent(e)
        # elif len(e.text()) == 1 and e.text() in 'hjkl':
            # letter = e.text()
            # label_len = len(self.labels)
            # row_len = self.row_len

            # if letter == 'l':
                # self.chosen_c = (self.chosen_c + 1) % label_len
            # elif letter == 'h':
                # self.chosen_c = self.chosen_c - 1
            # elif letter == 'j':
                # self.chosen_c = (self.chosen_c + row_len) % label_len
            # elif letter == 'k':
                # self.chosen_c = self.chosen_c - row_len

            # if self.chosen_c < 0:
                # self.chosen_c += label_len

            # n_chosen_c = self.labels[self.chosen_c]

            # o_chosen_c.unmark()
            # n_chosen_c.mark()

if __name__ == '__main__':
    app = QApplication(sys.argv)

    coloredlogs.DEFAULT_LOG_FORMAT = '%(asctime)s %(name)-20s %(levelname)s %(message)s'
    logger = logging.getLogger("awsh_req_client")
    coloredlogs.install(level='DEBUG', logger=logger, stream=sys.stdout)

    cache = awsh_cache()
    # read cached entries from file
    if not cache.read_cache():
        print("Failed to read cache")

    # window = aws_gui(cache.get_instances())
    window = aws_gui(None)

    # window.show()
    sys.exit(app.exec_())
