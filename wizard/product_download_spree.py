from openerp.osv import osv
import datetime

class product_download_spree(osv.TransientModel):
    _name = 'product.download.spree'
    _description = 'Interfaces all products with Spree'


    def download_spree(self, cr, uid, ids, context=None):
        ''' product.download.spree:download_spree()
            ---------------------------------------
            Downloads all products that have changed
            in the last 24 hours OR whichever products
            are currently manually selected.
            ------------------------------------------ '''

        prod_db = self.pool.get('product.product')

        active_ids = context.get('active_ids')
        if not active_ids:
            now = datetime.datetime.now()
            active_ids = prod_db.search(cr, uid, [('write_date', '>=', now.strftime("%Y-%m-%d") )])

        active_ids = prod_db.edi_partner_resolver(cr, uid, active_ids, context)
        prod_db.send_edi_out(cr, uid, active_ids, context=context)
        return {'type': 'ir.actions.act_window_close'}
