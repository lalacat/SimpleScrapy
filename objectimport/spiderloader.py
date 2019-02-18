from importlib import import_module
from pkgutil import iter_modules
import inspect
from spider import Spider
import logging
import traceback
from collections import defaultdict
from core.interface import ISpiderLoader
from zope.interface import implementer

logger = logging.getLogger(__name__)

@implementer(ISpiderLoader)
class SpiderLoader(object):

    def __init__(self):
        self._found = defaultdict(list)
        self._spiders = {}
        self._spider_modules = ["spider"]
        self.warn_only = True
        self._load_all_spiders()




    def import_spider(self,path):

        #导入爬虫包
        spiders = []

        spider = import_module(path)
        spiders.append(spider)

        if hasattr(spider,"__path__"):
            logger.debug(spider.__path__)

            for _, subpath, ispkg in iter_modules(spider.__path__):
                # 取得模块的绝对路径
                fullpath = path + "." + subpath

                # 判断是模块包还是模块
                if ispkg:
                    # 是模块包的话重新调用本方法将模块包下的所以模块都导入
                    spiders += self.import_spider(fullpath)
                else:
                    # 是模块的话就直接导入到结果中
                    submod = import_module(fullpath)
                    spiders.append(submod)
        else:
            logger.error("路径不对，脚本放在根目录下")
        return spiders

    def _load_all_spiders(self):
        # 根据设置的包名中导入爬虫，因为可能用户会针对不同的爬虫对象设置不同的包名
        for name in self._spider_modules:
            try:
                for module in self.import_spider(name):
                    self._load_spiders(module)
            # ImportError 包含ModuleNotFoundError
            except  ImportError as e:
                if self.warn_only:
                    msg = ("\n{tb}Could not load spiders from module '{modname}'. "
                           "See above traceback for details.".format(
                        modname="crawler.commands", tb=traceback.format_exc()))
                    logger.warn(msg, RuntimeWarning)
                else:
                    raise
        self._check_name_duplicates()



    def _load_spiders(self,module):
        for spcls in self._iter_spider_classes(module):
            self._found[spcls.name].append((module.__name__,spcls.__name__))
            self._spiders[spcls.name] =spcls

    def _check_name_duplicates(self):
        dupes = ["\n".join("  {cls} named {name!r} (in {module})".format(
            module=lis[0], cls=lis[1], name=name)
                           for lis in locations)
                 for name, locations in self._found.items()
                 if len(locations) > 1]
        if dupes:
            msg = ("\n有爬虫类的名称定义的相同:\n\n"
                   "{}\n\n这样会导致爬虫运行不成功，导致爬虫失败！！！".format("\n\n".join(dupes)))
            logger.warning(msg)

    def _iter_spider_classes(self,module):
        for obj in vars(module).values():
            """
            vars（）实现返回对象object的属性和属性值的字典对象
            要过滤出obj是类的信息，其中类的信息包括，模块导入其他模块的类的信息，模块中的父类，模块中所有定义的类
            因此，条件过滤分别是：
            1.判断obj的类型为class
            2.判断是否继承父类，因此命令包中__init__文件中定义的就是整个包中所需要的父类
            3.判断类是否为模块本身定义的类还是导入其他模块的类(感觉第二个条件包含此条件了有些多余)
            4.剔除父类
            """
            if inspect.isclass(obj) and \
                    issubclass(obj, Spider) and \
                    obj.__module__ == module.__name__ and \
                    getattr(obj,"name",None):
                yield obj

    def load(self,spider_name):

        try:
            return self._spiders[spider_name]
        except KeyError :
            raise KeyError("没有找到对应的爬虫：{}".format(spider_name))

    @classmethod
    def from_settings(cls,settings=None):
        # 返回一个实例，可以设置条件
        return cls()

    def list(self):
        return list(self._spiders.keys())

    '''
    
    # 要先获取项目的路径，将项目路径添加到系统目录中去
    def spider_module_path(self, projectName,spider_dir="test"):

        将爬虫包附加到系统路径中，只有在系统路径中，模块导入才能被识别到
        :param projectName: 项目名称
        :param spider_dir: 爬虫存放的文件夹


        # 获取文件当前路径
        curent_path = os.getcwd()
        try:
            # 找到项目的根目录的绝对地址，并将工作目录切换到根目录下
            root_direction = curent_path.split(projectName)[0] + projectName
            # 获取根目录下所有的子文件夹
            listdir = os.listdir(root_direction)
            for l in listdir:
                if l == spider_dir:
                    temp = os.path.join(root_direction, l)
                    # logger.error(temp)
                    os.chdir(temp)
            sys.path.append(os.getcwd())
        except FileNotFoundError as e:
            logger.error("项目名称错误")

    def get_spider_dict(self,spiders):
        dict_spider= {}
        for c in self._iter_spider_classes(spiders):
            dict_spider[c.__module__.split(".")[-1]] = c()
        return dict_spider        
    '''



