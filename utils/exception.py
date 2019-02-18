class CloseSpider(Exception):
    """Raise this from callbacks to request the spider to be closed"""

    def __init__(self, reason='cancelled'):
        super(CloseSpider, self).__init__()
        self.reason = reason


class MiddleWareError(Exception):
    def __init__(self, reason='error'):
        super(MiddleWareError, self).__init__()
        self.reason = reason