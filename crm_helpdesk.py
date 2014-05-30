from openerp.osv import osv
from openerp.tools.translate import _



class crm_helpdesk(osv.Model):
    _name = "crm.helpdesk"
    _inherit = "crm.helpdesk"


    def create_simple_case(self, cr, uid, header, description):
        return self.create(cr, uid, {'user_id': 6, 'name': header, 'description': description, 'categ_id': 2 })
