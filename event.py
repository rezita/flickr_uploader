
class FlickrEvent(object):
    """Base class for event handling"""

    def __init__(self):
        """Initialize handlers"""
        self.handlers = []

    def add_handler(self, handler):
        """add new handler method"""
        self.handlers.append(handler)
        return self

    def remove_handler(self, handler):
        self.handlers.remove(handler)
        return self


    def format(self, message):
        pass

    def fire(self, message, *args):
        """Fire an event and call handler functions"""
        for handler in self.handlers:
            handler(message)

flickEvent = FlickrEvent()

