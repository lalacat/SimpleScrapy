import weakref
from time import time
from collections import defaultdict
import logging
import six

logger = logging.getLogger(__name__)
NoneType = type(None)

live_refs = defaultdict(weakref.WeakKeyDictionary)

class object_ref(object):
    """继承这个类，能实现对活跃的实例进行记录"""

    __slots__ = ()

    def __new__(cls, *args, **kwargs):
        obj = object.__new__(cls)
        live_refs[cls][obj] = time()
        #print(cls,obj,live_refs[cls][obj])
        return obj

def format_live_refs(ignore=NoneType):
    """Return a tabular representation of tracked objects"""
    s = "Live References\n\n"
    now = time()
    for cls, wdict in sorted(six.iteritems(live_refs),key=lambda x: x[0].__name__):
    #for cls,wdict in live_refs.items():
        print(cls,wdict)
        for i in wdict.values():
            print (i)
        if not wdict:
            continue

        oldest = min(wdict.values())
        print("oldest",oldest)
        s += "%-30s %6d   oldest: %ds ago\n" % (
            cls.__name__, len(wdict), now - oldest
        )
    return s

def print_live_refs(*a, **kw):
    """Print tracked objects"""
    print(format_live_refs(*a, **kw))