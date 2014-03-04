import threading
from openerp import pooler

from openerp.osv import osv, fields

class product_upload_thr(osv.TransientModel):
    _name = 'product.upload.thr'
    _description = 'Interfaces all products with THR'


    _columns = {
        'no_of_processes' : fields.integer('Amount of processes', required=True),
        'load_categories' : fields.boolean('Load categories'),
        'load_properties' : fields.boolean('Load properties'),
        'load_products' : fields.boolean('Load products'),
    }


    _defaults = {
      'no_of_processes': lambda *a: 4,
      'load_categories': lambda *a: True,
      'load_properties': lambda *a: True,
      'load_products':   lambda *a: True,
    }


    def _upload_thr(self, cr, uid, ids, context=None):
        prod_db = self.pool.get('product.product')
        new_cr = pooler.get_db(cr.dbname).cursor()
        (uploader,) = self.browse(new_cr, uid, ids, context=context)
        param = {}
        param['no_of_processes'] = uploader.no_of_processes
        param['load_categories'] = uploader.load_categories
        param['load_properties'] = uploader.load_properties
        param['load_products']   = uploader.load_products
        prod_db.upload_thr(new_cr, uid, param, context=context)
        new_cr.close()
        return {}

    def upload_thr(self, cr, uid, ids, context=None):
        """
        @param self: The object pointer.
        @param cr: A database cursor
        @param uid: ID of the user currently logged in
        @param ids: List of IDs selected
        @param context: A standard dictionary
        """
        threaded_calculation = threading.Thread(target=self._upload_thr, args=(cr, uid, ids, context))
        threaded_calculation.start()
        return {'type': 'ir.actions.act_window_close'}

