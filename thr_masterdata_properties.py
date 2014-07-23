from openerp.osv import osv
from openerp.tools.translate import _
import logging

class webdust_property(osv.Model):

    _name = "webdust.property"
    _inherit = 'webdust.property'
    _description = "Property EDI extensions"

    log = logging.getLogger(None)

    def upload_thr(self, cr, uid, content, context):
        """
        This method takes in the header as defined by THR and
        makes sure they exist in OpenERP.
        """

        self.log.info('UPLOAD_THR-PROPERTIES: starting on the properties.')

        # Get all the ids + content for all the codes that already exist.
        # ---------------------------------------------------------------
        self.log.info('UPLOAD_THR-PROPERTIES: reading pre-existing properties.')
        prop_ids = self.search(cr, uid, [('name', 'in', [ x for x in content ])])
        all_existing = self.browse(cr, uid, prop_ids, context=context)

        for column in content:
            self.log.info('UPLOAD_THR-PROPERTIES: processing property {!s}'.format(column))
            existing = next((x for x in all_existing if x.name == column), None) #next() only returns 1st result of enumeration
            if not existing:
                vals = {}
                vals['name'] = column
                self.create(cr, uid, vals, context)

        cr.commit()
        self.log.info('UPLOAD_THR-PROPERTIES: property upload is complete.')
        return True



