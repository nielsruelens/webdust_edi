from openerp.osv import osv
from openerp.tools.translate import _


class out_purchase_order(osv.TransientModel):
    _inherit = ['clubit.tools.edi.wizard.outgoing']
    _name = 'out.purchase.order'
    _description = 'Send Purchase Orders'