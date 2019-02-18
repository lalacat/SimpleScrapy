import logging


class ErrorFilter(logging.Filter):

    def filter(self, record):
        try:
            level_name = record.levelname
        except AttributeError:
            return False

        if level_name == 'ERROR':
            return False
        else:
            return True