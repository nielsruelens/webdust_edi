from openerp.osv import osv
from openerp.tools.translate import _


##############################################################################
#
#    clubit.tools.edi.wizard.outgoing.category
#
#    Action handler class for categories outgoing
#
##############################################################################
class clubit_tools_edi_wizard_outgoing_category(osv.TransientModel):
    _inherit = ['clubit.tools.edi.wizard.outgoing']
    _name = 'clubit.tools.edi.wizard.outgoing.category'
    _description = 'Send Categories'