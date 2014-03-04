from openerp.osv import osv

class pricing_download_spree(osv.TransientModel):
    _name = 'pricing.download.spree'
    _description = 'Interfaces all pricing and availability with Spree'


    def download_spree(self, cr, uid, ids, context=None):
        ''' pricing.download.spree:download_spree()
            ---------------------------------------
            Downloads all pricing and availability.
            --------------------------------------- '''
        prod_db = self.pool.get('product.product')
        products = prod_db.search(cr, uid, [])
        products = prod_db.edi_partner_resolver(cr, uid, products, context)
        prod_db.send_edi_out_pricing(cr, uid, products, context=context)
        return {'type': 'ir.actions.act_window_close'}
