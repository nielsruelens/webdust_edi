from openerp.osv import osv
import datetime

class product_download_spree(osv.TransientModel):
    _name = 'product.download.spree'
    _description = 'Interfaces all products with Spree'


    def download_spree(self, cr, uid, ids, context=None):
        ''' product.download.spree:download_spree()
            ---------------------------------------
            Downloads all products that have changed
            in the last 24 hours.
            ---------------------------------------- '''
        prod_db = self.pool.get('product.product')
        now = datetime.datetime.now()
        products = prod_db.search(cr, uid, [('write_date', '>=', now.strftime("%Y-%m-%d") )])
        products = prod_db.edi_partner_resolver(cr, uid, products, context)
        prod_db.send_edi_out(cr, uid, products, context=context)
        return {'type': 'ir.actions.act_window_close'}
