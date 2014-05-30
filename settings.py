from openerp.osv import osv, fields
from openerp.tools.translate import _

class clubit_tools_settings(osv.Model):

    _name = "clubit.tools.settings"
    _inherit = "clubit.tools.settings"
    _description = "Webdust extensions to settings"

    _columns = {
        'sale_high_tax_id': fields.many2one('account.tax', 'Sale High Tax', required=True),
        'sale_low_tax_id': fields.many2one('account.tax', 'Sale Low Tax', required=True),
        'purchase_high_tax_id': fields.many2one('account.tax', 'Purchase High Tax', required=True),
        'purchase_low_tax_id': fields.many2one('account.tax', 'Purchase Low Tax', required=True),
    }


    def _check_no_of_processes(self, cr, uid, ids, context=None):
        for setting in self.browse(cr, uid, ids, context=context):
            if setting.no_of_processes < 1:
                return False
        return True

    _constraints = [
        (_check_no_of_processes, 'Smallest number allowed for number of processes is 1.', ['no_of_processes']),
    ]











