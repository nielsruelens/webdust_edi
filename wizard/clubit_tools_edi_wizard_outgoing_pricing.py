from openerp.osv import osv
from openerp.tools.translate import _


##############################################################################
#
#    clubit.tools.edi.wizard.outgoing.pricing
#
#    Action handler class for products outgoing
#
##############################################################################
class clubit_tools_edi_wizard_outgoing_pricing(osv.TransientModel):
    _inherit = ['clubit.tools.edi.wizard.outgoing']
    _name = 'clubit.tools.edi.wizard.outgoing.pricing'
    _description = 'Send Pricing'