import json
import conf,copy
from importlib import import_module
from settings import default_setting
import logging
logger = logging.getLogger(__name__)
#logging.basicConfig(level=logging.DEBUG,format='%(asctime)s - %(filename)s[line:%(lineno)d] - %(levelname)s: %(message)s')

SETTINGG_PRIORITIES = {
    'default': 0,
    'command': 10,
    'project': 20,
    'spider': 30,
    'cmdline': 40,
}


def get_settings_priority(priority):
    """
    如果priority是字符串，就返回设定的字典中字符串对应的Int值
    或者直接返回它本身
    """

    if isinstance(priority, str):
        if priority in SETTINGG_PRIORITIES:
            return SETTINGG_PRIORITIES[priority]
        else:
            return SETTINGG_PRIORITIES["default"]
    else:
        return priority


class SettingsAttribute(object):
    """
    这个类是给value绑定优先级的，生成一个特定的实例对象,例如：
    <SettingsAttribute value=True priority=40>
    """

    def __init__(self, value=None, priority="default"):
        self.value = value
        if isinstance(self.value, BaseSettings):
            self.priority = max(self.value.maxpriority(), priority)
        else:
            self.priority = priority

    def set(self, value, priority):
        """
        真对已存在的name,对它的value和priority进行更新，
        name对应一个旧的SettingsAttribute对象，因此新传入的value和priority就要
        和旧的值进行比较，只有priority高于或者等于的时候，value才更新
        先判断value是不是已经存在的BaseSettings的实例，如果是的话，就重新实例化，分配一个
        新的优先级
        """
        if priority >= self.priority:
            if isinstance(self.value, BaseSettings):
                value = BaseSettings(value, priority=priority)
            self.value = value
            self.priority = priority

    def __str__(self):
        return "<SettingsAttribute value={self.value!r} " \
               "priority={self.priority}>".format(self=self)

    __repr__ = __str__


class BaseSettings(object):
    """
    这个类是将dict类型的数据赋予一个priorities的优先级
    最终生成：
    {'LOG_ENABLED': <SettingsAttribute value=True priority=40>,
    'LOG_FILE': <SettingsAttribute value='test.txt' priority=40>}
    常用的API:
    get(name, default=None):根据{name:value}获得value值

    """

    # 针对某些参数不可改变，给出的标志位
    def __init__(self, values=None, priority='project'):
        """

        :param values: 参数对应的对象，可能是字符串，可能是数字也可能是bool值
        :param priority: 要设定的优先级

        attributes存放的是{"name":<SettingsAttribute value=' ' priority= >}
        """

        self.frozen = False
        self.attributes = {}
        self.update(values, priority)

    def __iter__(self):

        return iter(self.attributes.items())

    def __getitem__(self, name):
        # 返回值实际返回的是SettingsAttribute对象，value和Priority都是SettingsAttribute的
        # 优先级，根据实际需要返回的是value，形成name:value的对应关系

        if name not in self:
            return None
        else:
            return self.attributes[name].value

    def __contains__(self, item):
        return item in self.attributes

    def __len__(self):
        return len(self.attributes)

    def get(self, name, default=None):
        return self[name] if self[name] is not None else default

    def getbool(self, name, default=False):
        """
        将设定值转化为boolean类型的值：
        1，'1'，True,'true','True'都返回的是True
        0,'0',False,'false','False'都返回的是False


        :param name: the setting name
        :type name: string

        :param default: the value to return if no setting is found
        :type default: any
        """
        got = self.get(name, default)
        try:
            return bool(int(got))
        except ValueError:
            if got in ("True", "true"):
                return True
            if got in ("False", "false"):
                return False
            raise ValueError("仅支持以下的值为boolean类型的值返回 "
                             " 0/1, True/False, '0'/'1', "
                             "'True'/'False' and 'true'/'false'")

    def getint(self,name,default=0):
        return int(self.get(name,default))

    def getfloat(self, name, default=0.0):
        return float(self.get(name, default))

    def update(self, values, priority='project'):
        """
        为value更新一个新的优先级
        如果value是string型数据，即value="{name:value}"则需要先将value进行Json编码，
        变成dict型values={name:value}的数据，
        再对value进行判断，先判断values是不是BaseSetting的实例，如果是的话，就要对values进行拆分和解析出
        {name1:value1}...,
        如果不是实例的话，对已经json化的values进行迭代，


        """
        if isinstance(values, str):
            """
            将类如'{"a":"b"}'的字符串转变为{"a":"b"}字典型
            """
            values = json.loads(values)
            logger.info("update:",values)
        if values is not None:
            # 这个条件判断，是满足，其他的命令的setiing能绑定到当前实例的setting
            # 例如public_command.setting中的name:value都绑定好优先级
            # test_command3需要public_command.setting，可以直接执行：
            # test_command3.setting.set(public_command.setting)
            # 因为此时传入的values是BaseSetting的实例，数据结构是 {name:<SettingsAttribute value=True priority=40>}
            # 是包含name,value,priority,因此set中的priority是根据name来取得的等价于self.attributes[name].priority
            if isinstance(values, BaseSettings):
                for name, value in values.items():
                    self.set(name, value, values.getpriority(name))
            else:
                for name, value in values.items():
                    '''防止空格的存在导致有相同的name'''
                    self.set(name.strip(), value.strip(), priority)

    def set(self, name, value, priority="project"):
        """
        给 key/value 设定一个给定的优先级值



        :param name: 设置名
        :type name: string

        :param value: 要绑定优先级的变量
        :type value: any

        :param priority: 已给定的或者是自己设置的int型数值
        :type: priority: string or int

        """
        priority = get_settings_priority(priority)
        if name not in self:

            # 如果value是SettingsAttribute实例的话，直接存入字典中就行了
            if isinstance(value, SettingsAttribute):

                self.attributes[name] = value
            # value不是SettingsAttribute实例，就要新创建一个实例
            else:
                self.attributes[name] = SettingsAttribute(value, priority)
        else:
            # 针对name存在的情况，只需要对对应的SettingsAttribute实例更新value和priority即可
            self.attributes[name].set(value, priority)

    def setdict(self, values, priority="project"):
        """针对name1=value1,...,类型的的参数values 是list类型"""
        values = conf.arglist_to_dict(values)
        '''
        for k, v in values.items():
            self.set(k.strip(), v, priority)
        '''
        self.update(values,priority)

    def setmodule(self,module,priority='project'):
        '''用于导入默认的设置包或者自定义的设置文件'''
        if isinstance(module,str):
            module = import_module(module)
        for key in dir(module):
            if key.isupper():
                self.set(key,getattr(module,key),priority)

    def delete(self, name, priority='project'):
        self._assert_mutability()
        priority = get_settings_priority(priority)
        if priority >= self.getpriority(name):
            del self.attributes[name]

    def copy(self):
        """对当前设置进行深度复制，为的是根据不同的对象，可能在个别的配置上存在着不同"""
        return copy.deepcopy(self)



class Setting(BaseSettings):
    """导入默认的设置文件"""
    def __init__(self,values=None,priority="project"):
        super(Setting,self).__init__()
        """将默认的配置导入进来"""
        self.setmodule(default_setting, 'default')
        for name,val in self:
            if isinstance(val,dict):
                self.set(name,BaseSettings(values,"default"),'default')
        self.update(values,priority)


def iter_default_settings():
    """导入默认的配置文件dir()返回的list类型的数据"""
    for name in dir(default_setting):
        if name.isupper():
            yield name,getattr(default_setting, name)


def overridden_or_new_settings(settings):
    """返回添加的或者重写的配置"""
    for name,value in settings:
        """检查新写入"""
        if dir(default_setting).__contains__(name):
            """检查重写入"""
            defvalue = getattr(default_setting, name)
            if not isinstance(defvalue, dict) and settings[name] != defvalue:
                yield name, value
        else :
            yield name, value
    '''
        for name, defvalue in iter_default_settings():
        print(name,defvalue)
        value = settings[name]
        if not isinstance(defvalue, dict) and value != defvalue:
            yield name, value
    '''
