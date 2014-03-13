from openerp.osv import osv

class pricing_download_spree(osv.TransientModel):
    _name = 'pricing.download.spree'
    _description = 'Interfaces all pricing and availability with Spree'


    def download_spree(self, cr, uid, ids, context=None):
        ''' pricing.download.spree:download_spree()
            ---------------------------------------
            Downloads all pricing and availability or
            whichever products are selected.
            ----------------------------------------- '''
        prod_db = self.pool.get('product.product')

        active_ids = context.get('active_ids')
        if not active_ids:
            active_ids = prod_db.search(cr, uid, [])

        active_ids = prod_db.edi_partner_resolver(cr, uid, active_ids, context)
        prod_db.send_edi_out_pricing(cr, uid, active_ids, context=context)
        return {'type': 'ir.actions.act_window_close'}

