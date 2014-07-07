import threading
from openerp import pooler

from openerp.osv import osv

class webdust_quotations_out(osv.TransientModel):
    _name = 'webdust.quotations.out'
    _description = 'Class to immediately call the quotation push service'


    def _background(self, cr, uid, ids, context=None):
        po_db = self.pool.get('purchase.order')
        new_cr = pooler.get_db(cr.dbname).cursor()
        po_db.push_quotations(new_cr, uid)
        new_cr.close()
        return {}

    def start(self, cr, uid, ids, context=None):
        thread = threading.Thread(target=self._background, args=(cr, uid, ids, context))
        thread.start()
        return {'type': 'ir.actions.act_window_close'}


class webdust_quotations_out_manual(osv.TransientModel):
    _name = 'webdust.quotations.out.manual'
    _description = 'Class to immediately call the quotation push service'

    def start(self, cr, uid, ids, context=None):
        ids = context.get('active_ids', [])
        po_db = self.pool.get('purchase.order')
        po_db.push_quotations_manual(cr, uid, ids)
        return {'type': 'ir.actions.act_window_close'}