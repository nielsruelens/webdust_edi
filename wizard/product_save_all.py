import threading
from openerp import pooler
import logging
from openerp.osv import osv, fields

class webdust_product_save_all(osv.TransientModel):
    _name = 'webdust.product.save.all'
    _description = 'Mass save every product in the DB'
    
    _columns = {
        'only_prices' : fields.boolean('Save pricing only'),
    }

    def _background(self, cr, uid, ids, context={}):
        log = logging.getLogger(None)
        log.info('MASS-PRODUCT-SAVE: saving every single product. This is gonna take a while')
        prod_db = self.pool.get('product.product')
        new_cr = pooler.get_db(cr.dbname).cursor()

        context['save_anyway'] = True
        products = prod_db.search(new_cr, uid, [], context=context)
        
        offset = 0
        size = len(products)
        page_size = 1000
        offset = 10000
        size = 50
        page_size = 10
        for i in xrange(offset, size, page_size):
            log.info('MASS-PRODUCT-SAVE: saving products {!s} to {!s} of {!s}.'.format(i,i+page_size, size))
            # make sure product data is up-to-date
            prod_db.write(new_cr, uid, products[i:i+page_size], {}, context=context)
            
        new_cr.commit()
        new_cr.close()
        log.info('MASS-PRODUCT-SAVE: mass save is complete.')
        return {}

    def start(self, cr, uid, ids, context=None):
        thread = threading.Thread(target=self._background, args=(cr, uid, ids, context))
        thread.start()
        return {'type': 'ir.actions.act_window_close'}
