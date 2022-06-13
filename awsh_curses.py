import curses
import sys
import logging
import coloredlogs
import io
from typing import Any, Tuple, List

from awsh_ui import awsh_ui

KEY_ENTER = 10
KEY_ESC = 27
KEY_BACKSPACE = 8

CHOICES_START_ROW=4

def enter_debug(stdscr):
    import curses
    curses.nocbreak()
    stdscr.keypad(0)
    curses.echo()
    curses.endwin()
    import pdb; pdb.set_trace()

try:
    unicode
    _unicode = True
except NameError:
    _unicode = False


# Needed for language servers. Helps in completion suggestions
if sys.version_info >= (3, 8):
    Window_class = curses.window
else:
    Window_class = Any

def run_curses_command(func):
    """Run a function in curses environment"""

    def decorated(*args, **kargs):
        logger = logging.getLogger()
        prev_handlers = list()
        # Remove all previous handlers and only use the stream one
        for handler in logger.handlers:
            prev_handlers.append(handler)
            logger.removeHandler(handler)

        # Log into a stream
        output_stream = io.StringIO()
        stream_handler = logging.StreamHandler(output_stream)
        stream_handler.setFormatter(prev_handlers[-1].formatter)
        logger.addHandler(stream_handler)

        def curses_env_func(stdscr : Window_class):
            return func(stdscr, output_stream, *args, **kargs)

        try:
            result = curses.wrapper(curses_env_func)
        except:
            print("Got exception")
            # raise the exception outside curses env
            # so that it is printed correctly
            raise

        # restore the logger handlers to their previous state
        logger.removeHandler(stream_handler)
        for handler in prev_handlers:
            logger.addHandler(handler)

        print(output_stream.getvalue())
        return result

    return decorated


def _get_choices_max_depth(choices, current_depth = 0):

    assert(type(choices) == list or type(choices) == type("") or
            type(choices) == tuple)

    if type(choices) == type(""):
        return current_depth

    if type(choices) == tuple:
        return _get_choices_max_depth(choices[1], current_depth)

    max_depth = 0
    for choice in choices:
        max_depth = max(max_depth, _get_choices_max_depth(choice, current_depth + 1))

    return max_depth


class awsh_curses(awsh_ui):
    """This class provides a front-end infrastructure for AWS helper (awsh)
    through the terminal using the curses library (which is native to Linux)"""

    def __init__(self, stdscr : Window_class):
        self.stdscr = stdscr

        # Make curses use the same colors as the terminal
        curses.use_default_colors()

        curses.curs_set(0)

        # set current cursor location
        self.cx = self.cy = 0
        # Don't wait for CR for acknowledgement
        # curses.cbreak()
        # stdscr.keypad(True)

    def put_choices_in_window(self,
                              choices : list,
                              chosen : list,
                              drawn_window : int,
                              selected_window : int,
                              window_length : int):
        row = CHOICES_START_ROW
        stdscr = self.stdscr

        wchosen = chosen[drawn_window]

        for choice in choices:

            entry_str = choice
            if type(choice) == tuple:
                entry_str = choice[0]

            # if it's the currently chosen entry
            if (row - CHOICES_START_ROW) == wchosen and drawn_window <= selected_window:
                stdscr.addstr(row, 2 + (window_length * drawn_window), entry_str, curses.A_UNDERLINE | curses.color_pair(1))
            else:
                stdscr.addstr(row, 2 + (window_length * drawn_window), entry_str)

            stdscr.addstr(row, (window_length * (drawn_window + 1)) - 2, "|")
            row = row + 1

        # anotate current
        if drawn_window <= selected_window:
            stdscr.addstr(CHOICES_START_ROW + wchosen, (window_length * drawn_window), "> ")

        next_list = choices[wchosen]

        if type(next_list) == tuple and len(next_list[1]):
            self.put_choices_in_window(
                next_list[1], chosen, drawn_window + 1, selected_window, window_length)

    def _get_chosen_object(self, choices : list, chosen_arr : list):
        """Get the object in choices multi-dimensional list based on the chosen
        index array"""

        chosen_ix = 0
        for chosen_ix in chosen_arr:

            if type(choices[chosen_ix]) != tuple:
                return choices[chosen_ix]

            choices = choices[chosen_ix][1]

        # Choices is a list
        return choices


    def multiwindow_selection(self, title : str, choices : list,
                              max_choice_depth : int = 0) -> Tuple[bool, List[int]]:
        """Present a multi-window choice, meaning that each choice
        in the first window will present a different set of choices
        in the second window and so on.

        title -- the title for the selection
        choices -- A list of entries. Each entry might in itself be a list
        max_choice_depth -- maximum choices depth from which a user can choose

        returns the
        is_err -- whether something interrupted the search
        indices -- a list of indices of chosen in each window"""

        max_depth = _get_choices_max_depth(choices)
        if max_depth > 2:
            print("Error: Cannot currently deal with items of length more than 2")
            return None, None

        # if the user didn't limit the choices we can make, then set this to
        # the maximum possible
        max_choice_depth = max_choice_depth or max_depth
        if max_choice_depth <= 0:
            print("Error: the user should be able to choose at max_choice_depth of 1")
            return None, None

        max_choice_depth -= 1 # out internal index starts at 0

        stdscr = self.stdscr
        curses.init_pair(1, curses.COLOR_RED, -1) # -1 would use default

        rows, cols = stdscr.getmaxyx()
        # save some space for separators
        window_length = (cols // max_depth) - (5 * (max_depth - 1))

        chosen_ixs = [ 0 for i in range(max_depth) ]
        selected_window = 0
        start_from = 0

        while True:
            stdscr.addstr(0, 1, title + f"    {rows}-{cols}-{max_choice_depth}-{max_depth}-{window_length}")
            self.put_choices_in_window(choices, chosen_ixs, 0, selected_window, window_length)

            # called by getch()
            # stdscr.refresh()

            c = stdscr.getch()
            # Enter/Esc key
            # wchosen = chosen_ixs[
            if c in [ord('q'), KEY_ESC]:
                return True, None
            elif c in [curses.KEY_DOWN, ord('j')]:
                chosen_ixs[selected_window] = (chosen_ixs[selected_window] + 1) % len(choices)
            elif c in [curses.KEY_UP, ord('k')]:
                chosen_ixs[selected_window] = (chosen_ixs[selected_window] - 1) % len(choices)
            elif c in [curses.KEY_RIGHT, ord('l')] and (selected_window + 1) <= max_choice_depth:
                cchosen = chosen_ixs[selected_window]
                current_obj = self._get_chosen_object(
                    choices, chosen_ixs[:selected_window + 1])

                if isinstance(current_obj, list) and len(current_obj):
                    selected_window += 1
            elif c in [curses.KEY_LEFT, ord('h')]:
                if 0 < selected_window:
                    chosen_ixs[selected_window] = 0
                    selected_window -= 1
            elif c in [KEY_ENTER]:
                return False, chosen_ixs[:selected_window + 1]

            stdscr.erase()


    def clean_display(self) -> None:
        self.stdscr.erase()
        self.cx = self.cy = 0


    def print(self, msg : str) -> None:
        self.stdscr.addstr(msg)


    def ask_question(self, question : str) -> str:
        stdscr = self.stdscr
        stdscr.addstr(question)

        cy, cx = stdscr.getyx()

        curses.echo()
        reply = stdscr.getstr(cy, cx + 1)
        curses.noecho()

        return reply


    def display_subnets(self):
        stdscr = self.stdscr

        stdscr.addstr(3, 2, "Current mode: Typing mode\n")
        stdscr.addstr(4, 2, "You can type things you like\n")

        # stdscr.refresh()

        chosen = 0
        choices_nr = 2

        while True:
            stdscr.addstr(chosen + 3, 0, ">")

            c = stdscr.getch()

            # Enter/Esc key
            if c in [KEY_ENTER, ord('q'), KEY_ESC]:
                break
            elif c in [curses.KEY_DOWN, ord('j')]:
                stdscr.addstr(chosen + 3, 0, " ")
                chosen = (chosen + 1) % choices_nr
            elif c in [curses.KEY_UP, ord('k')]:
                stdscr.addstr(chosen + 3, 0, " ")
                chosen = chosen - 1 if chosen > 0 else choices_nr - 1

    # def __del__(self):
        # curses.nocbreak()
        # self.stdscr.keypad(False)
        # curses.endwin()

choices = [
    "1",
    ("2", [
        "2>1",
        "2>2"]),
    "3",
    ("4", [
         "4>1",
         "4>2",
         "4>3"
     ]),
]

def main(stdscr : Window_class):
    ac = awsh_curses(stdscr)

    import sys

    # sys.__stdout__.write(str(dir(curses)))
    # sys.__stdout__.write(str(curses.has_colors()))

    is_err, chosen_values = ac.multiwindow_selection(
        "Please choose a subnet to put interface on",
        choices)

    # sys.__stdout__.write(str(chosen_values))

    return chosen_values if not is_err else None
    # ac.display_subnets()

if __name__ == '__main__':
    try:
        chosen_values = curses.wrapper(main)
    except:
        # raise the exception outside the curses wrapper
        raise

    print(chosen_values)
    # a1 = ["item1", ["item", ["item", ["item"]]], "item"]
    # b1 = ["item1", ["item"]]

    print(_get_choices_max_depth(choices))
    # print(_get_choices_max_depth(b1))

