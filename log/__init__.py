"""
logging配置
"""
import os
import logging.config
import time
import warnings
logger = logging.getLogger(__name__)

class LogFormat(object):
    # log配置字典

    def __init__(self,settings=None):
        # 定义日志输出格式 结束
        '''
        logfile_dir = os.path.dirname(os.path.abspath(__file__))  # log文件的目录

        logfile_name = 'all2.log'  # log文件名

        # 如果不存在定义的日志目录就创建一个
        if not os.path.isdir(logfile_dir):
            os.mkdir(logfile_dir)

        # log文件的全路径
        logfile_path = os.path.join(logfile_dir, logfile_name)
        '''
        self.settings = settings
        self.level = settings['LOG_LEVEL']
        self.file_name = self._get_filename()
        self.file_errorurl = self.file_name+'_error_url'
        self._update_loggingdict()
        self._load_format()

    @classmethod
    def from_crawler(cls,crawler):
        return cls(crawler.settings)

    @classmethod
    def from_settings(cls,settings):
        return cls(settings)

    def crawled(self, module, name, msg, extra=None):
        return self._logformatter_adapter(self._crawled(module, name, msg, extra))

    def error(self, module, name,msg,extra=None):
        return self._logformatter_adapter(self._error(module, name,msg,extra))

    def _crawled(self,module,name,msg,extra=None):
        base_info = {
            'module': module,
            'name': name if name is '' else ':'+str(name),
            'msg': msg,
            'function':'',
            'request':'',
            'time': str(float('%6.4f' % extra.pop('time')))+'s ' if isinstance(extra,dict) and extra.get('time') else ''
        }
        if extra:
            if isinstance(extra,dict):
                if isinstance(extra,dict):
                    if extra.get('time'):
                        extra.pop(time)
                    base_info.update(self._format_dict(extra))
            else:
                base_info['function'] = ' '+str(extra)
        return {
            'msg': self.settings['LOG_CRAWLED_MSG'],
            'args': base_info
        }

    def _error(self,module, name,msg,extra):
        # error_fun = function if function else ''
        base_info = {
            'module': module,
            'name': name if name is '' else ':'+str(name),
            'msg': msg if msg else '',
            'function':'',
            'request':'',
            'reason':'',
            'exception':''
        }
        if extra:
            if isinstance(extra,dict):
                base_info.update(self._format_dict(extra))
            else:
                base_info['function'] = ' '+str(extra)

        return {
            'msg': self.settings['LOG_ERROR_MSG'],
            'args': base_info
        }

    def _update_loggingdict(self):
        for name, logset in self.settings['LOGGING_DIC'].items():
            if name is 'handlers':
                if isinstance(logset, dict):
                    for key,value in logset.items():
                        if key == 'onefile':
                            if value.get('filename'):
                                value['filename'] = self.file_name+'.log'
                        if key == 'ErrorUrl':
                            if value.get('filename'):
                                value['filename'] = self.file_errorurl+'.log'

    def _get_filename(self):
        time_now = time.localtime(time.time())
        time_str = time.strftime('%Y%m%d', time_now)
        root_path = os.getcwd()
        root_num = root_path.index('SimpleScrapy')
        logfile_dir = os.path.join(root_path[:root_num+len('SimpleScrapy')],'log_record')
        if not os.path.isdir(logfile_dir):
            os.makedirs(logfile_dir)
        file_name = os.path.join(logfile_dir,time_str)
        return file_name

    def _logformatter_adapter(self,logkws):
        """
        Helper that takes the dictionary output from the methods in LogFormatter
        and adapts it into a tuple of positional arguments for logger.log calls,
        handling backward compatibility as well.
        """
        if not {'msg', 'args'} <= set(logkws):
            warnings.warn("缺少必要的参数<msg><args>")

        message = logkws.get('msg')

        #  如果logkws含有'args'，则取 logkws['args']，负责直接为logkws本身
        args = logkws if not logkws.get('args') else logkws['args']

        return (message, args)

    def _load_format(self):
        # 导入上面定义的logging配置
        logging.config.dictConfig(self.settings['LOGGING_DIC'])

    def _format_dict(self,extra):
        format_dict = extra
        if isinstance(extra,dict):
            if extra.get('function'):
                extra['function'] = ' '+str(extra['function'])
            if extra.get('request'):
                extra['request'] = ' '+ str(extra['request'])
            if extra.get('reason'):
                extra['reason'] = '{' + str(extra['reason'])+'}'
        return format_dict