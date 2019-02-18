import sys,os, inspect
from pkgutil import iter_modules
from importlib import import_module
# from test.framework.spider import BaseQylSpider
import logging



class Spider(object):
    def __init__(self,projectName,path="spider"):
        self.projectName = projectName
        self.path = path

    def _spider_module_path(self):
        '''
        将爬虫包附加到系统路径中，只有在系统路径中，模块导入才能被识别到
        :param projectName: 项目名称
        '''

        # 获取文件当前路径
        curent_path = os.getcwd()
        try:
            # 找到项目的根目录的绝对地址，并将工作目录切换到根目录下
            root_direction = curent_path.split(self.projectName)[0] + self.projectName
            # 获取根目录下所有的子文件夹
            listdir = os.listdir(root_direction)
            for l in listdir:
                if l == 'test':
                    temp = os.path.join(root_direction, l)
                    os.chdir(temp)

            sys.path.append(os.getcwd())
        except FileNotFoundError as e:
            print("项目名称错误")

        '''
        #先判断是否有爬虫包的存在
        #存在的话就直接导入包
        #不存在的话就创建一个爬虫包
        if not dirlist.__contains__("spider"):
            os.mkdir("spider")

        '''
    def _import_spider(self):

        # 导入爬虫包
        spider = import_module(self.path)

        spiders = list()
        spiders.append(spider)

        if hasattr(spider, "__path__"):
            logging.info(spider.__path__)

            for _, subpath, ispkg in iter_modules(spider.__path__):
                # 取得模块的绝对路径
                fullpath = self.path + "." + subpath

                # 判断是模块包还是模块
                if ispkg:
                    # 是模块包的话重新调用本方法将模块包下的所以模块都导入
                    spiders += self.import_spider(self,fullpath)
                else:
                    # 是模块的话就直接导入到结果中
                    submod = import_module(fullpath)
                    spiders.append(submod)
        else:
            print("路径不对，脚本放在根目录下")
        return spiders

    def _get_spider(self):
        pass
        # self._spider_module_path()
        # spiders = self._import_spider()
        #
        # for c in spiders:
        #     for obj in vars(c).values():
        #         """
        #         vars（）实现返回对象object的属性和属性值的字典对象
        #         要过滤出obj是类的信息，其中类的信息包括，模块导入其他模块的类的信息，模块中的父类，模块中所有定义的类
        #         因此，条件过滤分别是：
        #         1.判断obj的类型为class
        #         2.判断是否继承父类，因此命令包中__init__文件中定义的就是整个包中所需要的父类
        #         3.判断类是否为模块本身定义的类还是导入其他模块的类(感觉第二个条件包含此条件了有些多余)
        #         4.剔除父类
        #         """
        #         if inspect.isclass(obj) and \
        #                 issubclass(obj, BaseQylSpider) and \
        #                 obj.__module__ == c.__name__ and \
        #                 getattr(obj,'name', None) and \
        #                 not obj == BaseQylSpider:
        #             yield obj
