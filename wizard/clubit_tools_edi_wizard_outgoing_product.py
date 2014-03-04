from openerp.osv import osv
from openerp.tools.translate import _


##############################################################################
#
#    clubit.tools.edi.wizard.outgoing.product
#
#    Action handler class for products outgoing
#
##############################################################################
class clubit_tools_edi_wizard_outgoing_product(osv.TransientModel):
    _inherit = ['clubit.tools.edi.wizard.outgoing']
    _name = 'clubit.tools.edi.wizard.outgoing.product'
    _description = 'Send Products'