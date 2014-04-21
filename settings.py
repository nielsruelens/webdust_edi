from openerp.osv import osv, fields
from openerp.tools.translate import _


class webdust_edi_settings_connection(osv.Model):

    _name = "webdust.edi.settings.connection"
    _columns = {
        'setting': fields.many2one('webdust.edi.settings', 'Settings', ondelete='cascade', required=True, select=True),
        'partner': fields.many2one('res.partner', 'Partner', ondelete='cascade', required=True, select=True),
        'name': fields.char('Name', size=50),
        'url': fields.char('Address', size=256, required=True),
        'port': fields.integer('Port', required=True),
        'user': fields.char('User', size=50, required=True),
        'password': fields.char('Password', size=100, required=True, password=True),
    }


class webdust_edi_settings(osv.Model):

    _name = "webdust.edi.settings"
    _description = "Settings model for Webdust EDI"

    _columns = {
        'no_of_processes': fields.integer('Number of processes', required=True),
        'sale_high_tax_id': fields.many2one('account.tax', 'Sale High Tax', required=True),
        'sale_low_tax_id': fields.many2one('account.tax', 'Sale Low Tax', required=True),
        'purchase_high_tax_id': fields.many2one('account.tax', 'Purchase High Tax', required=True),
        'purchase_low_tax_id': fields.many2one('account.tax', 'Purchase Low Tax', required=True),
        'connections': fields.one2many('webdust.edi.settings.connection', 'setting', 'Connections'),
    }


    def _check_no_of_processes(self, cr, uid, ids, context=None):
        for setting in self.browse(cr, uid, ids, context=context):
            if setting.no_of_processes < 1:
                return False
        return True

    _constraints = [
        (_check_no_of_processes, 'Smallest number allowed for number of processes is 1.', ['no_of_processes']),
    ]


    def create(self, cr, uid, vals, context=None):
        if self.search(cr, uid, []):
            raise osv.except_osv(_('Error!'), _("Only 1 settings record allowed."))
        return super(webdust_edi_settings, self).create(cr, uid, vals, context)

    def get_settings(self, cr, uid):
        ids = self.search(cr, uid, [])
        if ids:
            return self.browse(cr, uid, ids[0])
        return False

    def get_connection(self, cr, uid, partner_id, name=False):
        settings = self.get_settings(cr, uid)
        if name:
            return next((x for x in settings.connections if x.partner.id == partner_id and x.name == name),None)
        return next((x for x in settings.connections if x.partner.id == partner_id),None)

















