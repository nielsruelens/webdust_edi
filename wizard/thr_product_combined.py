import threading
from openerp import pooler

from openerp.osv import osv, fields

class thr_product_combined(osv.TransientModel):
    _name = 'thr.product.combined'
    _description = 'Interfaces everything product related from THR at once'


    def _background(self, cr, uid, ids, context=None):
        prod_db = self.pool.get('product.product')
        new_cr = pooler.get_db(cr.dbname).cursor()
        prod_db.upload_thr_product_combined(new_cr, uid, context=context)
        new_cr.close()
        return {}

    def start(self, cr, uid, ids, context=None):
        thread = threading.Thread(target=self._background, args=(cr, uid, ids, context))
        thread.start()
        return {'type': 'ir.actions.act_window_close'}


