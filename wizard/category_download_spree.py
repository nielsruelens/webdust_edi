from openerp.osv import osv

class category_download_spree(osv.TransientModel):
    _name = 'category.download.spree'
    _description = 'Interfaces all categories with Spree'


    def download_spree(self, cr, uid, ids, context=None):
        ''' category.download.spree:download_spree()
            ----------------------------------------
            Downloads all categories that have a code.
            ------------------------------------------ '''
        cat_db = self.pool.get('product.category')
        items = cat_db.search(cr, uid, [('code', '!=', False)])
        items = cat_db.edi_partner_resolver(cr, uid, items, context)
        cat_db.send_edi_out(cr, uid, items, context=context)
        return {'type': 'ir.actions.act_window_close'}
