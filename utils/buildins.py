
class iter_dict(dict):

    def __iter__(self):
        return iter(self.items())