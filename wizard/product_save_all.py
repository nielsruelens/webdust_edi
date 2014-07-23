import threading
from openerp import pooler
import logging
from openerp.osv import osv

class webdust_product_save_all(osv.TransientModel):
    _name = 'webdust.product.save.all'
    _description = 'Mass save every product in the DB'

    def _background(self, cr, uid, ids, context=None):
        log = logging.getLogger(None)
        log.info('MASS-PRODUCT-SAVE: saving every single product. This is gonna take a while')
        prod_db = self.pool.get('product.product')
        new_cr = pooler.get_db(cr.dbname).cursor()
        prod_db.write(new_cr, uid, prod_db.search(new_cr, uid, [], context=context), {}, context=context)
        new_cr.commit()
        new_cr.close()
        log.info('MASS-PRODUCT-SAVE: mass save is complete.')
        return {}

    def start(self, cr, uid, ids, context=None):
        thread = threading.Thread(target=self._background, args=(cr, uid, ids, context))
        thread.start()
        return {'type': 'ir.actions.act_window_close'}
