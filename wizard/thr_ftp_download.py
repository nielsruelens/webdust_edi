import threading
from openerp import pooler

from openerp.osv import osv

class webdust_thr_ftp_download(osv.TransientModel):
    _name = 'webdust.thr.ftp.download'
    _description = 'Class to immediately download everything from the THR FTP.'

    def start(self, cr, uid, ids, context=None):
        po_db = self.pool.get('product.product')
        po_db.thr_ftp_download(cr, uid)
        return {'type': 'ir.actions.act_window_close'}