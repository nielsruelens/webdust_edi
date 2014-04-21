import threading
from openerp import pooler

from openerp.osv import osv, fields

class thr_masterdata(osv.TransientModel):
    _name = 'thr.masterdata'
    _description = 'Interfaces all masterdata coming from THR'


    _columns = {
        'load_categories' : fields.boolean('Load categories'),
        'load_properties' : fields.boolean('Load properties'),
        'load_products' : fields.boolean('Load products'),
    }


    _defaults = {
      'load_categories': lambda *a: True,
      'load_properties': lambda *a: True,
      'load_products':   lambda *a: True,
    }


    def _background(self, cr, uid, ids, context=None):
        prod_db = self.pool.get('product.product')
        new_cr = pooler.get_db(cr.dbname).cursor()
        (uploader,) = self.browse(new_cr, uid, ids, context=context)
        param = {}
        param['load_categories'] = uploader.load_categories
        param['load_properties'] = uploader.load_properties
        param['load_products']   = uploader.load_products
        prod_db.upload_thr_master_from_file(new_cr, uid, param, context=context)
        new_cr.close()
        return {}

    def start(self, cr, uid, ids, context=None):
        thread = threading.Thread(target=self._background, args=(cr, uid, ids, context))
        thread.start()
        return {'type': 'ir.actions.act_window_close'}


