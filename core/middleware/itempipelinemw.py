from core.middleware import MiddlewareManager
from objectimport.bulid_component_list import bulid_component_list


class ItemPipelineManager(MiddlewareManager):

    component_name = 'Item Pipeline'
    middlewares_name = 'ITEM_PIPELINES'

    @classmethod
    def _get_mwlist_from_settings(cls, settings):
        return bulid_component_list(settings[cls.middlewares_name],cls)

    def _add_middleware(self, pipe):
        super(ItemPipelineManager, self)._add_middleware(pipe)
        if hasattr(pipe, 'process_item'):
            self.methods['process_item'].append(pipe.process_item)

    def process_item(self, item, spider):
        #  item的处理是串联式的处理
        return self._process_chain('process_item', item, spider)
