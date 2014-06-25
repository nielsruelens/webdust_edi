from openerp.osv import osv

class clubit_tools_edi_document_incoming(osv.Model):
    _name = "clubit.tools.edi.document.incoming"
    _inherit = 'clubit.tools.edi.document.incoming'

    def create_from_web_request(self, cr, uid, partner, flow, reference, content, data_type):
        ''' clubit.tools.edi.document.incoming:create_from_web_request()
        ----------------------------------------------------------------
        This method extends the base web request method to create a helpdesk
        case in something goes wrong.
        -------------------------------------------------------------------- '''
        result = super(clubit_tools_edi_document_incoming, self).create_from_web_request(cr, uid, partner, flow, reference, content, data_type)
        if isinstance(result, basestring):
            description = 'These are the request parameters:\n partner: {!s} \n flow: {!s} \n reference: {!s} \n content: {!s} \n data_type: {!s}'.format(partner, flow, reference, content.eoncode('utf8'), data_type)
            self.pool.get('crm.helpdesk').create_simple_case( cr, uid, 'Something went wrong when accepting an HTTP request', description )
        return result