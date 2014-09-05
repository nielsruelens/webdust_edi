import threading
from openerp import pooler
import logging
from openerp.osv import osv, fields

class webdust_product_save_all(osv.TransientModel):
    _name = 'webdust.product.save.all'
    _description = 'Mass save every product in the DB'

    _columns = {
        'only_prices' : fields.boolean('Save pricing only'),
        'offset' : fields.integer('Offset'),
        'size' : fields.integer('Size'),
        'page_size' : fields.integer('Page size')
    }

    _defaults = {
        'offset' : 0,
        'page_size' : 0,
        'size': lambda self,cr,uid,c: len(self.pool.get('product.product').search(cr, uid, [])),
    }

    def _background(self, cr, uid, ids, context={}):
        log = logging.getLogger(None)
        log.info('MASS-PRODUCT-SAVE: saving every single product. This is gonna take a while')
        prod_db = self.pool.get('product.product')
        new_cr = pooler.get_db(cr.dbname).cursor()
        wizard = self.browse(new_cr, uid, ids[0])

        context['save_anyway'] = True
        products = prod_db.search(new_cr, uid, [], context=context)

        offset = wizard.offset
        size = wizard.size
        page_size = wizard.page_size
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
