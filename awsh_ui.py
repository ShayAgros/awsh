class awsh_ui:
    """This defines an interface for interacting with the user
    with awsh scripts"""

    def multiline_selection(self, title, choices):
        """Present a multi selection choice to the user and returns either
        the value of the callback registered with it
        
        Keyword Arguments:
        title -- the title for the selection
        choices -- A list of entries. Each entry can be a word or
        a dictionary of the form { entry, color, callback }
        """
        pass


from rofi import Rofi
    
class awsh_rofi (awsh_ui):
    """Implemntation of awsh_ui using Rofi function"""

    def __init__(self):
        self.r = Rofi()


    def multiline_selection(self, title : str, choices):
        """Present a multi selection choice to the user and returns either
        the value of the callback registered with it
        
        Keyword Arguments:
        title -- the title for the selection
        choices -- A list of entries. Each entry can be a word or
        a dictionary of the form { entry, color, callback }
        """
        if type(choices) != list:
            raise Exception("Choices needs to be a list")
            
        if len(choices) == 0:
            raise Exception("list of choices cannot be empty")

        items_desc = list()
        for entry in choices:
            if type(entry) == type(""):
                items_desc.append(entry)
                continue

            # Do some sanity checks
            if type(entry) != dict:
                raise Exception("Entries should be either strings or dictionaries")

            if 'entry' not in entry:
                raise Exception("A dictionary entry has to have 'entry' attribute")

            item_desc = ""
            if 'color' in entry:
                item_desc = r'<span background="{}">    </span>    '.format(entry["color"])

            item_desc = item_desc + entry['entry']
            items_desc.append(item_desc)

        index, key = self.r.select(title, items_desc)

        is_err = key != 0

        return is_err, index


def main():
    """docstring for main"""
    r = awsh_rofi()
    reply = r.multiline_selection("Please choose an item", ["one", "two", { "entry": "three", "color": "#ff00ff" }])
    print(reply)


if __name__ == '__main__':
    main()
