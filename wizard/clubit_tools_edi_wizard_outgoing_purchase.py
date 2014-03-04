from openerp.osv import osv
from openerp.tools.translate import _


##############################################################################
#
#    clubit.tools.edi.wizard.outgoing.purchase
#
#    Action handler class for delivery order outgoing (normal)
#
##############################################################################
class clubit_tools_edi_wizard_outgoing_purchase(osv.TransientModel):
    _inherit = ['clubit.tools.edi.wizard.outgoing']
    _name = 'clubit.tools.edi.wizard.outgoing.purchase'
    _description = 'Send Purchase Orders'