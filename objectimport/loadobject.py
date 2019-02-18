from importlib import import_module
def load_object(path):
    """
    给定一个obj的绝对路径，能够返回一个obj，通常配合着setting使用

    object can be a class, function, variable or an instance.
    path ie: 'scrapy.downloadermiddlewares.redirect.RedirectMiddleware'
    """

    try:
        # 表示出现“.”的最后出现的位置，例如“crawler.test"中"."的位置在7这个地方
        dot = path.rindex('.')
    except ValueError:
        raise ValueError("Error loading object '%s': not a full path" % path)

    module, name = path[:dot], path[dot+1:]
    mod = import_module(module)

    try:
        obj = getattr(mod, name)
    except AttributeError:
        raise NameError("Module '%s' doesn't define any object named '%s'" % (module, name))

    return obj

